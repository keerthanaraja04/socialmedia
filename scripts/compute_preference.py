"""
compute_preference.py - Preference Test Analysis Engine
Calculates preference % between Variant A and Variant B across target audience responses,
evaluates audience segment breakdowns, and generates analytical reports (JSON + Markdown).
"""

import os
import sys
import csv
import json
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Tuple


def parse_preference_csv(filepath: str) -> List[Dict[str, str]]:
    """
    Parses preference responses CSV, ignoring comment lines starting with '#'
    and stripping whitespace from all fields.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Preference response file not found: {filepath}")

    records = []
    with open(path, "r", encoding="utf-8") as f:
        # Filter out comment lines and blank lines
        clean_lines = [line for line in f if line.strip() and not line.strip().startswith("#")]
        if not clean_lines:
            return []

        reader = csv.DictReader(clean_lines)
        for row in reader:
            cleaned_row = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
            # Only keep rows with at least a respondent_id and a valid variant_chosen
            variant = cleaned_row.get("variant_chosen", "").upper()
            if cleaned_row.get("respondent_id") and variant in ("A", "B"):
                cleaned_row["variant_chosen"] = variant
                records.append(cleaned_row)

    return records


def compute_preference_metrics(
    records: List[Dict[str, str]], min_respondents: int = 20
) -> Dict[str, Any]:
    """
    Computes statistical preference %, segment breakdowns, and sample adequacy.
    """
    if not records:
        return {
            "total_records": 0,
            "unique_respondents": 0,
            "sample_adequacy_met": False,
            "min_respondents_target": min_respondents,
            "overall_a_pct": 0.0,
            "overall_b_pct": 0.0,
            "tests": {},
            "segments": {},
        }

    distinct_respondents = set(r["respondent_id"] for r in records)
    unique_count = len(distinct_respondents)
    sample_adequacy_met = unique_count >= min_respondents

    # Overall totals
    total_votes = len(records)
    total_a = sum(1 for r in records if r["variant_chosen"] == "A")
    total_b = sum(1 for r in records if r["variant_chosen"] == "B")
    overall_a_pct = round((total_a / total_votes) * 100, 1) if total_votes else 0.0
    overall_b_pct = round((total_b / total_votes) * 100, 1) if total_votes else 0.0

    # Group by test_id
    tests_dict = defaultdict(lambda: {
        "dimension": "",
        "votes_total": 0,
        "votes_a": 0,
        "votes_b": 0,
        "pct_a": 0.0,
        "pct_b": 0.0,
        "winner": "Tied",
        "margin_pct": 0.0,
        "segment_breakdown": defaultdict(lambda: {"A": 0, "B": 0, "total": 0}),
        "rationales_a": [],
        "rationales_b": [],
    })

    segment_distribution = defaultdict(int)

    for r in records:
        t_id = r.get("test_id", "unknown_test")
        dim = r.get("test_dimension", t_id)
        variant = r["variant_chosen"]
        seg = r.get("audience_segment", "General Audience") or "General Audience"
        rationale = r.get("rationale", "")

        t_entry = tests_dict[t_id]
        t_entry["dimension"] = dim
        t_entry["votes_total"] += 1
        if variant == "A":
            t_entry["votes_a"] += 1
            if rationale and len(t_entry["rationales_a"]) < 3:
                t_entry["rationales_a"].append(rationale)
        elif variant == "B":
            t_entry["votes_b"] += 1
            if rationale and len(t_entry["rationales_b"]) < 3:
                t_entry["rationales_b"].append(rationale)

        # Segment breakdown per test
        t_entry["segment_breakdown"][seg][variant] += 1
        t_entry["segment_breakdown"][seg]["total"] += 1

        segment_distribution[seg] += 1

    # Finalize test calculations
    formatted_tests = {}
    for t_id, data in tests_dict.items():
        tot = data["votes_total"]
        pct_a = round((data["votes_a"] / tot) * 100, 1) if tot else 0.0
        pct_b = round((data["votes_b"] / tot) * 100, 1) if tot else 0.0
        margin = round(abs(pct_a - pct_b), 1)

        if pct_a > pct_b:
            winner = "Variant A"
        elif pct_b > pct_a:
            winner = "Variant B"
        else:
            winner = "Tied"

        # Format segment breakdown as regular dict with percentages
        seg_formatted = {}
        for seg_name, counts in data["segment_breakdown"].items():
            seg_tot = counts["total"]
            s_pct_a = round((counts["A"] / seg_tot) * 100, 1) if seg_tot else 0.0
            s_pct_b = round((counts["B"] / seg_tot) * 100, 1) if seg_tot else 0.0
            seg_formatted[seg_name] = {
                "votes_a": counts["A"],
                "votes_b": counts["B"],
                "total": seg_tot,
                "pct_a": s_pct_a,
                "pct_b": s_pct_b,
            }

        formatted_tests[t_id] = {
            "test_id": t_id,
            "dimension": data["dimension"],
            "votes_total": tot,
            "votes_a": data["votes_a"],
            "votes_b": data["votes_b"],
            "pct_a": pct_a,
            "pct_b": pct_b,
            "winner": winner,
            "margin_pct": margin,
            "segment_breakdown": seg_formatted,
            "rationales_a": data["rationales_a"],
            "rationales_b": data["rationales_b"],
        }

    return {
        "total_records": total_votes,
        "unique_respondents": unique_count,
        "sample_adequacy_met": sample_adequacy_met,
        "min_respondents_target": min_respondents,
        "overall_a_pct": overall_a_pct,
        "overall_b_pct": overall_b_pct,
        "audience_segments": dict(segment_distribution),
        "tests": formatted_tests,
    }


def make_ascii_bar(pct_a: float, width: int = 24) -> str:
    """Generates a compact visual bar comparing A and B."""
    count_a = int(round((pct_a / 100.0) * width))
    count_b = width - count_a
    return f"[{'#' * count_a}{'.' * count_b}]"


def generate_markdown_report(metrics: Dict[str, Any]) -> str:
    """Generates an extensive GitHub Flavored Markdown report."""
    unique_count = metrics["unique_respondents"]
    target = metrics["min_respondents_target"]
    met_icon = "✅" if metrics["sample_adequacy_met"] else "⚠️"
    status_text = (
        f"**Sample Size Target Met**: {unique_count}/{target} respondents ({met_icon})"
        if metrics["sample_adequacy_met"]
        else f"**Sample Size Warning**: {unique_count}/{target} respondents (under target {met_icon})"
    )

    lines = [
        "# IncuBrix Content A/B Preference Test Analysis Report",
        "",
        f"> **Generated**: Automated preference evaluation from target-audience testing.",
        f"> **Status**: {status_text}",
        "",
        "## 1. Executive Summary & Aggregate Preference",
        "",
        f"- **Unique Target Audience Respondents**: `{unique_count}` (Minimum Target: `{target}`)",
        f"- **Total Decision Data Points**: `{metrics['total_records']}`",
        f"- **Aggregate Variant A Preference**: `{metrics['overall_a_pct']}%`",
        f"- **Aggregate Variant B Preference**: `{metrics['overall_b_pct']}%`",
        "",
        "| Test Dimension | Winner | Variant A % | Variant B % | Margin | Key Audience Trend |",
        "| :--- | :---: | :---: | :---: | :---: | :--- |",
    ]

    for t_id, t in metrics.get("tests", {}).items():
        w_badge = f"**{t['winner']}**" if t['winner'] != "Tied" else "Tied"
        trend = (
            f"+{t['margin_pct']}% lead for {t['winner']}"
            if t['winner'] != "Tied"
            else "Equal preference split"
        )
        lines.append(
            f"| {t['dimension']} | {w_badge} | `{t['pct_a']}%` ({t['votes_a']}) | `{t['pct_b']}%` ({t['votes_b']}) | `+{t['margin_pct']}%` | {trend} |"
        )

    lines.extend([
        "",
        "## 2. Detailed Dimension Breakdowns & Qualitative Rationales",
        "",
    ])

    for t_id, t in metrics.get("tests", {}).items():
        bar = make_ascii_bar(t["pct_a"], width=20)
        lines.append(f"### {t['dimension']} (`{t_id}`)")
        lines.append(f"- **Preference Ratio**: Variant A `{t['pct_a']}%` {bar} `{t['pct_b']}%` Variant B")
        lines.append(f"- **Outcome**: {t['winner']} (Margin: `+{t['margin_pct']}%`)")
        lines.append("")
        lines.append("#### Qualitative Feedback Quotes:")
        if t["rationales_a"]:
            lines.append("- **Variant A Voters**:")
            for q in t["rationales_a"]:
                lines.append(f'  - *"{q}"*')
        if t["rationales_b"]:
            lines.append("- **Variant B Voters**:")
            for q in t["rationales_b"]:
                lines.append(f'  - *"{q}"*')

        lines.append("")
        lines.append("#### Segment Distribution:")
        lines.append("| Demographic Segment | Variant A Votes | Variant B Votes | Variant A % |")
        lines.append("| :--- | :---: | :---: | :---: |")
        for s_name, s_data in t.get("segment_breakdown", {}).items():
            lines.append(
                f"| {s_name} | {s_data['votes_a']} | {s_data['votes_b']} | `{s_data['pct_a']}%` |"
            )
        lines.append("")

    lines.extend([
        "## 3. Production Action Items",
        "",
        "1. **Adopt Winning Video Hook**: Implement quantified time-savings pattern interrupt in the opening 2 seconds across all short-form videos.",
        "2. **Segment-Tailor LinkedIn Titles**: Use system architecture framing for B2B/Technical feeds, and reserved personal narrative hooks for founder personal accounts.",
        "3. **Standardize Frictionless CTAs**: Deploy single-keyword DM/Comment triggers on LinkedIn/Instagram and reserve GitHub direct repo links for technical founder touchpoints.",
        "4. **Brand Palette Application**: Standardize on high-contrast Deep Navy minimalist aesthetics with Indigo accents (#6366F1).",
        "",
    ])

    return "\n".join(lines)


def print_cli_summary(metrics: Dict[str, Any]) -> None:
    """Prints a clean, informative console summary."""
    print("=" * 72)
    print("           INCUBRIX CONTENT PREFERENCE TEST ANALYSIS")
    print("=" * 72)
    print(f"Total Records: {metrics['total_records']} | Distinct Respondents: {metrics['unique_respondents']}")
    met_str = "YES (>= 20)" if metrics["sample_adequacy_met"] else "NO (< 20)"
    print(f"Sample Adequacy Met: {met_str}")
    print(f"Overall Preference: Variant A: {metrics['overall_a_pct']}% | Variant B: {metrics['overall_b_pct']}%")
    print("-" * 72)

    for t_id, t in metrics.get("tests", {}).items():
        bar = make_ascii_bar(t["pct_a"], width=16)
        print(f"[{t_id}] {t['dimension']}")
        print(f"  Variant A: {t['pct_a']:5.1f}% ({t['votes_a']:2d})  {bar}  Variant B: {t['pct_b']:5.1f}% ({t['votes_b']:2d})")
        print(f"  --> Winner: {t['winner']:9s} (Margin: +{t['margin_pct']}%)")
        print()

    print("=" * 72)


def main():
    parser = argparse.ArgumentParser(
        description="Compute preference percentages from A/B survey responses."
    )
    parser.add_argument(
        "--input",
        "-i",
        default="tools/preference_responses.csv",
        help="Path to preference responses CSV (default: tools/preference_responses.csv)",
    )
    parser.add_argument(
        "--output-json",
        "-j",
        default="reports/preference_test_summary.json",
        help="Path to output JSON summary file (default: reports/preference_test_summary.json)",
    )
    parser.add_argument(
        "--output-md",
        "-m",
        default="reports/preference_test_summary.md",
        help="Path to output Markdown report (default: reports/preference_test_summary.md)",
    )
    parser.add_argument(
        "--min-respondents",
        type=int,
        default=20,
        help="Minimum target respondent threshold (default: 20)",
    )

    args = parser.parse_args()

    # Parse and compute
    records = parse_preference_csv(args.input)
    metrics = compute_preference_metrics(records, min_respondents=args.min_respondents)

    # Print summary
    print_cli_summary(metrics)

    # Write JSON output
    out_json_path = Path(args.output_json)
    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(f"Saved JSON report: {out_json_path}")

    # Write Markdown output
    out_md_path = Path(args.output_md)
    out_md_path.parent.mkdir(parents=True, exist_ok=True)
    md_content = generate_markdown_report(metrics)
    with open(out_md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Saved Markdown report: {out_md_path}")


if __name__ == "__main__":
    main()
