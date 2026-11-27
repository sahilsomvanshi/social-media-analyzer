import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from analyzer import best_posts, calculate_metrics, compare, group_performance, load_csv, split_periods
from insights import parse_ai_response, rule_based_insights
from report import build_pdf
from analyzer import daily_engagement

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data.csv"


@pytest.fixture
def parts():
    df = load_csv(SAMPLE)
    cur, prev = split_periods(df)
    return df, cur, prev


def test_engagement_is_sum_of_interactions(parts):
    df, _, _ = parts
    row = df.iloc[0]
    assert row["engagement"] == row[["likes", "comments", "shares", "saves", "clicks"]].sum()


def test_periods_do_not_overlap(parts):
    df, cur, prev = parts
    assert len(cur) + len(prev) == len(df)
    assert prev["date"].max() < cur["date"].min()


def test_compare_percent_and_points():
    out = compare({"reach": 120, "engagement_rate": 5.5}, {"reach": 100, "engagement_rate": 5.0})
    assert out["reach"] == 20.0 and out["engagement_rate"] == 0.5


def test_missing_date_column_gives_clear_error(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("post,reach\na,10\n")
    with pytest.raises(ValueError, match="date"):
        load_csv(f)


def test_ai_reply_parsing():
    reply = '```json\n{"summary":"s","insights":["a"],"recommendations":["b"]}\n```'
    assert parse_ai_response(reply)["insights"] == ["a"]
    with pytest.raises(ValueError):
        parse_ai_response('{"summary":"s"}')


def test_pdf_is_created(parts):
    _, cur, prev = parts
    m, p = calculate_metrics(cur), calculate_metrics(prev)
    ch = compare(m, p)
    top = best_posts(cur)
    ins = rule_based_insights(m, p, ch, top, group_performance(cur, "type"), group_performance(cur, "weekday"), True)
    pdf = build_pdf("Test Client", "period", m, p, ch, top, daily_engagement(cur, prev), ins, True)
    assert pdf[:4] == b"%PDF"
