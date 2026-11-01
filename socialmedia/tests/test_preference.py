"""
Unit tests for scripts/compute_preference.py
"""

import pytest
from pathlib import Path
from scripts.compute_preference import (
    parse_preference_csv,
    compute_preference_metrics,
    generate_markdown_report,
    make_ascii_bar,
)


def test_parse_preference_csv(tmp_path):
    csv_file = tmp_path / "test_responses.csv"
    csv_file.write_text(
        """# Sample comment
respondent_id,audience_segment,test_id,test_dimension,variant_chosen,confidence_rating,rationale,timestamp
resp_01,Creator,test_01,Video Hook,A,5,"Great hook",2026-10-23T10:00:00Z
resp_01,Creator,test_02,Title Slide,B,4,"Clear title",2026-10-23T10:01:00Z
# Another comment
resp_02,Editor,test_01,Video Hook,b,4,"Too fast",2026-10-23T10:05:00Z
invalid_resp,Editor,test_01,Video Hook,INVALID,1,"bad",2026-10-23T10:06:00Z
"""
    )

    records = parse_preference_csv(str(csv_file))
    # Should parse 3 valid records, skipping comment lines and invalid variant
    assert len(records) == 3
    assert records[0]["respondent_id"] == "resp_01"
    assert records[0]["variant_chosen"] == "A"
    assert records[1]["variant_chosen"] == "B"
    assert records[2]["respondent_id"] == "resp_02"
    assert records[2]["variant_chosen"] == "B"  # Normalized to uppercase


def test_sample_adequacy_target():
    # Test below 20 respondents
    records_under = [
        {"respondent_id": f"resp_{i}", "test_id": "t1", "test_dimension": "Hook", "variant_chosen": "A", "audience_segment": "Founder"}
        for i in range(1, 15)
    ]
    m_under = compute_preference_metrics(records_under, min_respondents=20)
    assert m_under["unique_respondents"] == 14
    assert m_under["sample_adequacy_met"] is False

    # Test with 20+ respondents
    records_met = [
        {"respondent_id": f"resp_{i}", "test_id": "t1", "test_dimension": "Hook", "variant_chosen": "A", "audience_segment": "Founder"}
        for i in range(1, 25)
    ]
    m_met = compute_preference_metrics(records_met, min_respondents=20)
    assert m_met["unique_respondents"] == 24
    assert m_met["sample_adequacy_met"] is True


def test_preference_percentage_and_winner():
    records = [
        {"respondent_id": "r1", "test_id": "t1", "test_dimension": "Hook", "variant_chosen": "A", "audience_segment": "Creator", "rationale": "Fast"},
        {"respondent_id": "r2", "test_id": "t1", "test_dimension": "Hook", "variant_chosen": "A", "audience_segment": "Creator", "rationale": "Direct"},
        {"respondent_id": "r3", "test_id": "t1", "test_dimension": "Hook", "variant_chosen": "A", "audience_segment": "Editor", "rationale": "Clear"},
        {"respondent_id": "r4", "test_id": "t1", "test_dimension": "Hook", "variant_chosen": "B", "audience_segment": "Editor", "rationale": "Curious"},
    ]

    metrics = compute_preference_metrics(records, min_respondents=4)
    assert metrics["total_records"] == 4
    assert metrics["unique_respondents"] == 4

    t1 = metrics["tests"]["t1"]
    assert t1["votes_total"] == 4
    assert t1["votes_a"] == 3
    assert t1["votes_b"] == 1
    assert t1["pct_a"] == 75.0
    assert t1["pct_b"] == 25.0
    assert t1["winner"] == "Variant A"
    assert t1["margin_pct"] == 50.0

    # Segment breakdown
    assert t1["segment_breakdown"]["Creator"]["pct_a"] == 100.0
    assert t1["segment_breakdown"]["Editor"]["pct_a"] == 50.0
    assert t1["segment_breakdown"]["Editor"]["pct_b"] == 50.0


def test_tie_handling():
    records = [
        {"respondent_id": "r1", "test_id": "t_tie", "test_dimension": "Tie Dimension", "variant_chosen": "A"},
        {"respondent_id": "r2", "test_id": "t_tie", "test_dimension": "Tie Dimension", "variant_chosen": "B"},
    ]
    metrics = compute_preference_metrics(records, min_respondents=2)
    t = metrics["tests"]["t_tie"]
    assert t["pct_a"] == 50.0
    assert t["pct_b"] == 50.0
    assert t["winner"] == "Tied"
    assert t["margin_pct"] == 0.0


def test_markdown_report_generation():
    records = [
        {"respondent_id": f"r{i}", "test_id": "t1", "test_dimension": "Video Hook", "variant_chosen": "A" if i % 3 != 0 else "B", "audience_segment": "Creator", "rationale": f"Reason {i}"}
        for i in range(1, 22)
    ]
    metrics = compute_preference_metrics(records, min_respondents=20)
    md = generate_markdown_report(metrics)

    assert "# IncuBrix Content A/B Preference Test Analysis Report" in md
    assert "Sample Size Target Met" in md
    assert "Video Hook" in md
    assert "Qualitative Feedback Quotes:" in md
    assert "Segment Distribution:" in md


def test_ascii_bar():
    bar100 = make_ascii_bar(100.0, width=10)
    assert bar100 == "[##########]"
    bar0 = make_ascii_bar(0.0, width=10)
    assert bar0 == "[..........]"
    bar50 = make_ascii_bar(50.0, width=10)
    assert bar50 == "[#####.....]"
