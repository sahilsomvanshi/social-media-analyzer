"""Streamlit dashboard: upload a CSV, see the numbers, get insights, export a PDF."""
import io
import os
from pathlib import Path

import streamlit as st

from analyzer import (best_posts, calculate_metrics, compare, daily_engagement, fmt_number,
                      group_performance, last_followers, load_csv, split_periods)
from insights import ai_insights, build_payload, rule_based_insights
from report import build_pdf

st.set_page_config(page_title="Social Media Performance Analyzer", page_icon="📊", layout="wide")
SAMPLE = Path(__file__).parent / "sample_data.csv"
PERIODS = {"First half vs second half": None, "Last 7 days vs previous 7": 7,
           "Last 14 days vs previous 14": 14, "Last 30 days vs previous 30": 30}

st.title("Social Media Performance Analyzer")
st.caption("Upload an Instagram or LinkedIn analytics CSV and get a client-ready report.")

with st.sidebar:
    st.header("Report settings")
    client = st.text_input("Client name", "Client")
    uploaded = st.file_uploader("Analytics CSV", type="csv")
    use_sample = st.checkbox("Use sample data")
    period_label = st.selectbox("Compare periods", list(PERIODS))
    api_key = os.getenv("ANTHROPIC_API_KEY") or st.text_input("Anthropic API key (for AI insights)", type="password")

if uploaded is not None:
    source, source_name = io.BytesIO(uploaded.getvalue()), uploaded.name
elif use_sample:
    source, source_name = SAMPLE, "sample"
else:
    st.info("Upload a CSV in the sidebar, or tick **Use sample data** to try it.")
    st.stop()

try:
    df = load_csv(source)
except Exception as error:
    st.error(f"Could not read this file. {error}")
    st.stop()

current, previous = split_periods(df, PERIODS[period_label])
if current.empty:
    st.error("There are no posts in the current period. Try another comparison option.")
    st.stop()
has_previous = not previous.empty

metrics = calculate_metrics(current, last_followers(previous) if has_previous else None)
prev_metrics = calculate_metrics(previous)
changes = compare(metrics, prev_metrics) if has_previous else {k: None for k in metrics}

def span(part):
    return f"{part['date'].min():%d %b %Y} to {part['date'].max():%d %b %Y}"
period_text = f"Current period: {span(current)}." + (f" Previous period: {span(previous)}." if has_previous else " No previous period to compare.")
st.caption(period_text)

# --- Key metrics ---
cards = [("Reach", "reach"), ("Impressions", "impressions"), ("Engagement", "engagement"),
         ("Engagement rate", "engagement_rate"), ("Follower growth", "follower_growth"), ("Posts", "posts")]
for column, (label, key) in zip(st.columns(len(cards)), cards):
    value, change = metrics[key], changes.get(key)
    if value is None:
        column.metric(label, "n/a")
        continue
    shown = f"{value:.2f}%" if key == "engagement_rate" else (f"{value:+,.0f}" if key == "follower_growth" else fmt_number(value))
    delta = None if change is None else (f"{change:+.2f} pts" if key == "engagement_rate" else f"{change:+.1f}%")
    column.metric(label, shown, delta)

# --- Chart ---
daily = daily_engagement(current, previous)
st.subheader("Engagement by day")
chart = daily.pivot_table(index="date", columns="period", values="engagement", aggfunc="sum").fillna(0)
st.bar_chart(chart, color=["#2F5BFF", "#B8C2D6"][: len(chart.columns)] if len(chart.columns) == 2 else None)

# --- Best posts ---
top = best_posts(current)
st.subheader("Best-performing posts")
st.dataframe(top[["date", "post", "type", "reach", "engagement", "engagement_rate"]].rename(columns={"engagement_rate": "rate %"}),
             hide_index=True, use_container_width=True)

# --- Insights ---
formats = group_performance(current, "type")
weekdays = group_performance(current, "weekday")
state_key = (source_name, len(df), period_label)
if st.session_state.get("ai_key") != state_key:
    st.session_state["ai_key"], st.session_state["ai_result"] = state_key, None

st.subheader("Insights and recommendations")
if st.button("Generate AI insights"):
    if not api_key:
        st.warning("Add an Anthropic API key in the sidebar to use AI insights. Rule-based insights are shown below.")
    else:
        try:
            with st.spinner("Writing insights..."):
                payload = build_payload(client, metrics, prev_metrics, changes, top, formats, weekdays)
                st.session_state["ai_result"] = ai_insights(payload, api_key)
        except Exception as error:
            st.error(f"AI insights failed ({type(error).__name__}). Showing rule-based insights instead.")

result = st.session_state.get("ai_result")
source_label = "AI-generated" if result else "Rule-based"
result = result or rule_based_insights(metrics, prev_metrics, changes, top, formats, weekdays, has_previous)
st.caption(source_label)
st.write(result["summary"])
left, right = st.columns(2)
with left:
    st.markdown("**What we found**")
    for item in result["insights"]:
        st.markdown(f"- {item}")
with right:
    st.markdown("**What to do next**")
    for item in result["recommendations"]:
        st.markdown(f"- {item}")

# --- PDF ---
st.divider()
pdf_bytes = build_pdf(client, period_text, metrics, prev_metrics, changes, top, daily, result, has_previous)
st.download_button("Export PDF report", pdf_bytes, file_name=f"{client.strip().replace(' ', '-').lower() or 'client'}-social-report.pdf",
                   mime="application/pdf", type="primary")
