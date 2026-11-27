"""Data layer: load a social media analytics CSV, clean it, and calculate metrics."""
import re
import pandas as pd

# Words we look for in column names, so different exports still work.
# Order matters: "type" is checked before "post" so "Post type" is not read as the post text.
COLUMN_HINTS = {
    "date": r"date|day|published|time",
    "type": r"type|format|media",
    "post": r"post|title|caption|content|text|name|link",
    "reach": r"^reach|accountsreached",
    "impressions": r"impression",
    "likes": r"like|reaction",
    "comments": r"comment",
    "shares": r"share|repost",
    "saves": r"save",
    "clicks": r"click",
    "followers": r"^followers$|followercount|totalfollowers",
    "new_followers": r"newfollower|followergain|followersgained",
}
NUMBER_COLUMNS = ["reach", "impressions", "likes", "comments", "shares", "saves", "clicks"]


def fmt_number(x):
    """Short, readable numbers: 12,345 -> 12.3K."""
    if x is None:
        return "n/a"
    if abs(x) >= 1_000_000:
        return f"{x / 1_000_000:.1f}M"
    if abs(x) >= 10_000:
        return f"{x / 1_000:.1f}K"
    return f"{x:,.0f}"


def load_csv(file):
    """Read the CSV, standardise column names, and add an 'engagement' column."""
    df = pd.read_csv(file)
    if df.empty:
        raise ValueError("The file has no rows.")

    simple = {c: re.sub(r"[^a-z0-9]", "", str(c).lower()) for c in df.columns}
    renamed, used = {}, set()
    for standard, pattern in COLUMN_HINTS.items():
        for original, clean in simple.items():
            if original not in used and re.search(pattern, clean):
                renamed[original] = standard
                used.add(original)
                break
    df = df.rename(columns=renamed)

    if "date" not in df:
        raise ValueError("No date column found. The file needs a column like 'Date' or 'Published'.")
    if "reach" not in df and "impressions" not in df:
        raise ValueError("No reach or impressions column found. Check the column names in your export.")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).copy()
    if df.empty:
        raise ValueError("None of the dates could be read. Use a format like 2026-10-31.")

    for col in NUMBER_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0) if col in df else 0
    for col in ["followers", "new_followers"]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "post" not in df:
        df["post"] = [f"Post {i + 1}" for i in range(len(df))]
    if "type" not in df:
        df["type"] = ""

    # Engagement = every way people interacted with a post.
    df["engagement"] = df[["likes", "comments", "shares", "saves", "clicks"]].sum(axis=1)
    return df.sort_values("date").reset_index(drop=True)


def split_periods(df, days=None):
    """Return (current, previous).
    days=None: split the date range in half. days=N: last N days vs the N days before."""
    first, last = df["date"].min(), df["date"].max()
    if days is None:
        middle = first + (last - first) / 2
        return df[df["date"] > middle], df[df["date"] <= middle]
    cutoff = last - pd.Timedelta(days=days)
    current = df[df["date"] > cutoff]
    previous = df[(df["date"] <= cutoff) & (df["date"] > cutoff - pd.Timedelta(days=days))]
    return current, previous


def calculate_metrics(df, previous_followers=None):
    """Main numbers for one period. Returns plain Python numbers."""
    if df.empty:
        return {"posts": 0, "reach": 0, "impressions": 0, "engagement": 0,
                "engagement_rate": 0.0, "follower_growth": None}
    base = df["impressions"].sum() or df["reach"].sum()
    growth = None
    if "followers" in df and df["followers"].notna().any():
        start = previous_followers if previous_followers is not None else df["followers"].dropna().iloc[0]
        growth = float(df["followers"].dropna().iloc[-1] - start)
    elif "new_followers" in df:
        growth = float(df["new_followers"].sum())
    return {
        "posts": int(len(df)),
        "reach": int(df["reach"].sum()),
        "impressions": int(df["impressions"].sum()),
        "engagement": int(df["engagement"].sum()),
        "engagement_rate": round(float(df["engagement"].sum() / base * 100), 2) if base else 0.0,
        "follower_growth": growth,
    }


def last_followers(df):
    """Last known follower count in a period (or None)."""
    if "followers" in df and df["followers"].notna().any():
        return float(df["followers"].dropna().iloc[-1])
    return None


def compare(current, previous):
    """Change from previous to current.
    Counts: percent change. engagement_rate: change in percentage points."""
    out = {}
    for key, value in current.items():
        old = previous.get(key)
        if value is None or old is None:
            out[key] = None
        elif key == "engagement_rate":
            out[key] = round(value - old, 2)
        elif old == 0:
            out[key] = None
        else:
            out[key] = round((value - old) / abs(old) * 100, 1)
    return out


def best_posts(df, n=5):
    """Top posts by engagement, with their engagement rate."""
    top = df.sort_values("engagement", ascending=False).head(n).copy()
    base = top["impressions"].where(top["impressions"] > 0, top["reach"])
    top["engagement_rate"] = (top["engagement"] / base.replace(0, float("nan")) * 100).round(2)
    return top


def daily_engagement(current, previous):
    """Engagement per day for both periods (for charts)."""
    frames = []
    for label, part in (("Previous", previous), ("Current", current)):
        if not part.empty:
            day = part.groupby(part["date"].dt.date)["engagement"].sum().reset_index()
            day["period"] = label
            frames.append(day)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["date", "engagement", "period"])


def group_performance(df, column):
    """Engagement rate per group (post type or weekday). Groups need at least 2 posts."""
    if column == "weekday":
        keys = df["date"].dt.day_name()
    else:
        keys = df[column].replace("", pd.NA)
    work = df.assign(group=keys).dropna(subset=["group"])
    rows = []
    for name, part in work.groupby("group"):
        if len(part) < 2:
            continue
        base = part["impressions"].sum() or part["reach"].sum()
        if base:
            rows.append({"group": name, "posts": len(part), "engagement_rate": round(part["engagement"].sum() / base * 100, 2)})
    return pd.DataFrame(rows, columns=["group", "posts", "engagement_rate"]).sort_values("engagement_rate", ascending=False).reset_index(drop=True)
