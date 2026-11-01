"""Unit tests for scripts/fill_workbook.py using openpyxl.

Verifies:
1. Yellow input cells are populated with calendar.csv and runs.jsonl data
2. Green formula cells are strictly protected and never overwritten
3. Formulas remain valid and intact
"""

import csv
import json
from pathlib import Path
import pytest
import openpyxl

from scripts.fill_workbook import (
    create_default_submission_workbook,
    is_formula_cell,
    is_green_cell,
    is_yellow_cell,
    populate_submission_workbook,
)


def test_create_and_detect_cell_types(tmp_path: Path) -> None:
    wb_file = tmp_path / "test_workbook.xlsx"
    create_default_submission_workbook(wb_file)
    assert wb_file.exists()

    wb = openpyxl.load_workbook(wb_file, data_only=False)

    # Verify sheets exist
    assert "Submission Overview" in wb.sheetnames
    assert "Content Calendar" in wb.sheetnames
    assert "LLM Runs & Costs" in wb.sheetnames

    ws_cal = wb["Content Calendar"]
    # Column A row 2 is a yellow input cell
    in_cell = ws_cal["A2"]
    assert is_yellow_cell(in_cell) is True
    assert is_formula_cell(in_cell) is False

    # Column O row 2 is a green formula cell
    form_cell = ws_cal["O2"]
    assert is_formula_cell(form_cell) is True
    assert is_green_cell(form_cell) is True


def test_populate_workbook_preserves_green_formula_cells(tmp_path: Path) -> None:
    wb_file = tmp_path / "test_workbook.xlsx"
    create_default_submission_workbook(wb_file)

    # Create dummy calendar.csv
    cal_file = tmp_path / "calendar.csv"
    with open(cal_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id", "platform", "format", "pillar", "hook", "caption",
            "hashtags", "CTA", "tracking_link", "file_path", "source_file_path",
            "scheduled_datetime", "target_metric", "status"
        ])
        writer.writerow([
            "asset_01", "tiktok", "9:16 vertical video", "Workflows",
            "Stop manual editing.", "Here is the exact workflow.",
            "#IncuBrix", "Follow @IncuBrix", "https://incubrix.com/?utm_source=tiktok",
            "data/video.mp4", "content/source.txt", "2026-10-24 09:00:00",
            "shares", "scheduled"
        ])

    # Create dummy runs.jsonl
    runs_file = tmp_path / "runs.jsonl"
    with open(runs_file, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "timestamp": "2026-10-23T20:00:00Z",
            "model": "llama-3.3-70b-versatile",
            "prompt_tokens": 1200,
            "completion_tokens": 400,
            "total_tokens": 1600,
            "latency_ms": 850.5,
            "estimated_cost_usd": 0.001024,
            "retries_count": 0,
            "status": "success",
        }) + "\n")

    # Run population
    yellow_written, formula_protected = populate_submission_workbook(
        workbook_path=wb_file,
        calendar_csv_path=cal_file,
        runs_log_path=runs_file,
    )

    assert yellow_written > 0
    assert formula_protected > 0

    # Inspect modified workbook
    wb_reloaded = openpyxl.load_workbook(wb_file, data_only=False)

    # 1. Verify Calendar row was populated
    ws_cal = wb_reloaded["Content Calendar"]
    assert ws_cal["A2"].value == "asset_01"
    assert ws_cal["B2"].value == "tiktok"
    assert ws_cal["E2"].value == "Stop manual editing."

    # 2. CRITICAL: Verify formula cell was NOT overwritten and still contains formula
    col_o_cell = ws_cal["O2"]
    assert col_o_cell.data_type == "f" or str(col_o_cell.value).startswith("=")
    assert "IF(" in str(col_o_cell.value)

    # 3. Verify Runs row was populated
    ws_runs = wb_reloaded["LLM Runs & Costs"]
    assert ws_runs["A2"].value == "2026-10-23T20:00:00Z"
    assert ws_runs["B2"].value == "llama-3.3-70b-versatile"
    assert ws_runs["E2"].value == 1600

    # 4. Verify Totals formula cell in row 53 is preserved
    sum_cell = ws_runs["E53"]
    assert sum_cell.data_type == "f" or str(sum_cell.value).startswith("=")
    assert "SUM(" in str(sum_cell.value)
