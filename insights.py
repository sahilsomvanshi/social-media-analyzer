"""Insights: simple rule-based insights, plus optional AI insights using the Anthropic API."""
import json
import os

from analyzer import fmt_number


def _pct(x):
    return "n/a" if x is None else f"{x:+.1f}%"


def rule_based_insights(metrics, previous, changes, top, formats, weekdays, has_previous):
    """Works with no API key. Returns summary, insights and recommendations."""
    insights, recs = [], []
    rate_change = changes.get("engagement_rate")

    if has_previous:
        insights.append(f"Engagement is {_pct(changes.get('engagement'))} compared with the previous period. "
                        f"Engagement rate moved from {previous['engagement_rate']:.2f}% to {metrics['engagement_rate']:.2f}%.")
        insights.append(f"Reach changed by {_pct(changes.get('reach'))} and impressions by {_pct(changes.get('impressions'))}.")
    else:
        insights.append(f"Engagement rate for this period is {metrics['engagement_rate']:.2f}% across {metrics['posts']} posts.")

    growth = metrics.get("follower_growth")
    if growth is not None:
        insights.append(f"Followers changed by {growth:+,.0f} in this period.")

    if len(top):
        best = top.iloc[0]
        share = best["engagement"] / metrics["engagement"] * 100 if metrics["engagement"] else 0
        insights.append(f"The best post earned {fmt_number(best['engagement'])} engagements, about {share:.0f}% of the period total.")
        recs.append("Reuse the idea of the best post in a new format, such as a carousel, a short video or a follow-up post.")

    if len(formats) > 1:
        hi, lo = formats.iloc[0], formats.iloc[-1]
        insights.append(f"{hi['group']} posts perform best ({hi['engagement_rate']:.2f}% engagement rate). {lo['group']} posts are the weakest ({lo['engagement_rate']:.2f}%).")
        recs.append(f"Publish more {hi['group']} content and test new ideas for {lo['group']} posts.")
    if len(weekdays) > 1:
        insights.append(f"{weekdays.iloc[0]['group']} is the strongest posting day by engagement rate.")
        recs.append(f"Schedule important posts on {weekdays.iloc[0]['group']}.")

    if rate_change is not None and rate_change < 0:
        recs.append("Engagement rate fell. Rework the first line or first second of each post and end with a clear question.")
    elif rate_change is not None:
        recs.append("Engagement rate improved. Keep the topics and formats that worked and repeat them next period.")
    recs.append("Reply to comments within the first hour of posting to boost early engagement.")

    if has_previous:
        summary = (f"{metrics['posts']} posts this period. Engagement is {_pct(changes.get('engagement'))} "
                   f"and reach is {_pct(changes.get('reach'))} against the previous period.")
    else:
        summary = f"{metrics['posts']} posts in this period. There is no previous period to compare with."
    return {"summary": summary, "insights": insights, "recommendations": recs}


SYSTEM_PROMPT = (
    "You are a social media analyst writing for a client report. Use only the data given. "
    "Return JSON only, with no markdown: "
    '{"summary": string (2 sentences), "insights": [4 strings, each citing a number], '
    '"recommendations": [4 concrete actions]}. Plain, confident language. Do not invent numbers.'
)


def build_payload(client, metrics, previous, changes, top, formats, weekdays):
    """Small summary of the data to send to the AI (no raw rows)."""
    return {
        "client": client,
        "current": metrics,
        "previous": previous,
        "change": changes,
        "top_posts": [{"post": str(r["post"])[:80], "type": r["type"], "reach": int(r["reach"]), "engagement": int(r["engagement"])}
                      for _, r in top.iterrows()],
        "engagement_rate_by_type": formats.to_dict("records"),
        "engagement_rate_by_weekday": weekdays.to_dict("records"),
    }


def parse_ai_response(text):
    """Turn the model's reply into a dict. Raises ValueError if it is not the expected shape."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[4:] if text.lower().startswith("json") else text
    data = json.loads(text.strip())
    for key in ("summary", "insights", "recommendations"):
        if key not in data:
            raise ValueError(f"AI reply is missing '{key}'")
    return {"summary": str(data["summary"]),
            "insights": [str(x) for x in data["insights"]],
            "recommendations": [str(x) for x in data["recommendations"]]}


def ai_insights(payload, api_key, model=None):
    """Ask Claude for client-ready insights. Needs an Anthropic API key."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
    )
    text = "".join(block.text for block in message.content if block.type == "text")
    return parse_ai_response(text)
