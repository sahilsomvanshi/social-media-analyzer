"""PDF report builder (fpdf2 + matplotlib)."""
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from fpdf import FPDF

from analyzer import fmt_number

BLUE, GREY = "#2F5BFF", "#B8C2D6"


def _t(text):
    """Keep text safe for the built-in PDF fonts."""
    text = str(text).replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return text.encode("latin-1", "replace").decode("latin-1")


def _chart(daily):
    fig, ax = plt.subplots(figsize=(7, 2.4), dpi=150)
    for label, color in (("Previous", GREY), ("Current", BLUE)):
        part = daily[daily["period"] == label]
        ax.bar(part["date"], part["engagement"], color=color, label=label, width=0.8)
    ax.legend(frameon=False, fontsize=8)
    ax.tick_params(labelsize=7)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.autofmt_xdate()
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png")
    plt.close(fig)
    buffer.seek(0)
    return buffer


def _change(key, value):
    if value is None:
        return "-"
    return f"{value:+.2f} pts" if key == "engagement_rate" else f"{value:+.1f}%"


def build_pdf(client, period_text, metrics, previous, changes, top, daily, insights, has_previous):
    """Return the finished report as PDF bytes."""
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    nl = {"new_x": "LMARGIN", "new_y": "NEXT"}

    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 10, _t(f"{client} - Social media performance report"), **nl)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(90, 100, 120)
    pdf.multi_cell(0, 5, _t(period_text), **nl)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Key metrics", **nl)
    rows = [("Reach", "reach"), ("Impressions", "impressions"), ("Engagement", "engagement"),
            ("Engagement rate", "engagement_rate"), ("Follower growth", "follower_growth"), ("Posts", "posts")]
    widths = (60, 35, 35, 40)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(238, 241, 246)
    for head, w in zip(("Metric", "Current", "Previous", "Change"), widths):
        pdf.cell(w, 8, head, border="B", fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    for label, key in rows:
        cur, prev = metrics.get(key), previous.get(key)
        show = (lambda v: "n/a" if v is None else (f"{v:.2f}%" if key == "engagement_rate" else fmt_number(v)))
        pdf.cell(widths[0], 8, label, border="B")
        pdf.cell(widths[1], 8, show(cur), border="B")
        pdf.cell(widths[2], 8, show(prev) if has_previous else "-", border="B")
        pdf.cell(widths[3], 8, _change(key, changes.get(key)) if has_previous else "-", border="B")
        pdf.ln()
    pdf.ln(4)

    if len(daily):
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, "Engagement by day", **nl)
        pdf.image(_chart(daily), w=180)
        pdf.ln(2)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Best-performing posts", **nl)
    pdf.set_font("Helvetica", "", 10)
    for i, (_, r) in enumerate(top.iterrows(), 1):
        rate = "" if r.get("engagement_rate") != r.get("engagement_rate") else f", {r['engagement_rate']:.2f}% rate"
        pdf.multi_cell(0, 6, _t(f"{i}. {str(r['post'])[:80]} - {fmt_number(r['engagement'])} engagements, {fmt_number(r['reach'])} reach{rate}"), **nl)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Summary", **nl)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, _t(insights["summary"]), **nl)
    pdf.ln(3)
    for title, items in (("Insights", insights["insights"]), ("Recommendations", insights["recommendations"])):
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, title, **nl)
        pdf.set_font("Helvetica", "", 10)
        for item in items:
            pdf.multi_cell(0, 6, _t("- " + item), **nl)
        pdf.ln(3)

    return bytes(pdf.output())
