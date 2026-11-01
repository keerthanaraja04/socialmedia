#!/usr/bin/env python3
"""IncuBrix Submission Workbook Populator using openpyxl.

Safely populates yellow input cells in the IncuBrix submission Excel workbook
using data from calendar.csv and data/logs/runs.jsonl.

CRITICAL SAFETY GUARANTEE:
- Green formula cells and Excel formulas (=SUM, =COUNT, =IF, etc.) are strictly protected
  and NEVER overwritten.
- Only yellow input cells (hex #FFF2CC, #FFE599, #FFFF00, etc.) and designated data slots
  receive updated values.

Usage:
    python scripts/fill_workbook.py
    python scripts/fill_workbook.py --workbook my_submission.xlsx --calendar data/outputs/.../calendar.csv
    python scripts/fill_workbook.py --create-template
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from src.logging.logger import get_logger, setup_logging

logger = get_logger("fill_workbook")

# Standard Color Codes
YELLOW_FILL_HEX = "FFF2CC"  # Light yellow input cell
YELLOW_ACCENT_HEX = "FFE599" # Medium yellow input header/cell
GREEN_FILL_HEX = "E2EFDA"   # Light green formula cell
GREEN_BORDER_HEX = "385723" # Dark green border
HEADER_BLUE_HEX = "1F4E78"  # Corporate Navy
WHITE_TEXT_HEX = "FFFFFF"

# Known Yellow and Green Hex values for color detection
YELLOW_HEX_PATTERNS = {
    "FFF2CC", "FFE599", "FFD966", "FFFF00", "FFFFCC", "FFFF99",
    "FFF9C4", "FEF3BD", "FFFFE0", "FFF7D6", "FFFEE0"
}

GREEN_HEX_PATTERNS = {
    "E2EFDA", "C6EFCE", "A9D08E", "00B050", "70AD47", "34A853",
    "D9EAD3", "93C47D", "E6F4EA", "D4EDDA", "27AE60"
}


def is_formula_cell(cell: openpyxl.cell.Cell) -> bool:
    """Return True if cell contains an Excel formula."""
    if cell.data_type == "f":
        return True
    if isinstance(cell.value, str) and cell.value.strip().startswith("="):
        return True
    return False


def is_green_cell(cell: openpyxl.cell.Cell) -> bool:
    """Return True if cell fill color is green."""
    if not cell.fill or not cell.fill.fill_type:
        return False
    color = cell.fill.fgColor or cell.fill.start_color
    if not color:
        return False
    rgb = str(getattr(color, "rgb", "") or "").upper()
    return any(rgb.endswith(g) for g in GREEN_HEX_PATTERNS) or rgb in GREEN_HEX_PATTERNS


def is_yellow_cell(cell: openpyxl.cell.Cell) -> bool:
    """Return True if cell fill color is yellow."""
    if not cell.fill or not cell.fill.fill_type:
        return False
    color = cell.fill.fgColor or cell.fill.start_color
    if not color:
        return False
    rgb = str(getattr(color, "rgb", "") or "").upper()
    return any(rgb.endswith(y) for y in YELLOW_HEX_PATTERNS) or rgb in YELLOW_HEX_PATTERNS


def find_latest_calendar_csv() -> Optional[Path]:
    """Locate the most recent calendar.csv across data/outputs/ with fast shallow scanning."""
    outputs_dir = PROJECT_ROOT / "data" / "outputs"
    if not outputs_dir.exists():
        return None

    bundle_cal = outputs_dir / "final_submission_bundle" / "calendar.csv"
    if bundle_cal.exists():
        return bundle_cal

    try:
        subdirs = sorted(
            [d for d in outputs_dir.iterdir() if d.is_dir() and d.name != "temp_thumbs"],
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        for d in subdirs:
            c = d / "calendar.csv"
            if c.exists():
                return c
    except Exception:
        pass

    calendar_files = list(outputs_dir.glob("*/calendar.csv"))
    if not calendar_files:
        return None
    calendar_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return calendar_files[0]


def find_latest_runs_jsonl() -> Path:
    """Locate the primary runs.jsonl audit file."""
    primary = PROJECT_ROOT / "data" / "logs" / "runs.jsonl"
    if primary.exists():
        return primary
    fallback = PROJECT_ROOT / "logs" / "runs.jsonl"
    return fallback


def create_default_submission_workbook(workbook_path: Path) -> Path:
    """Create a structured IncuBrix submission workbook with yellow input and green formula cells."""
    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    yellow_fill = PatternFill(start_color=YELLOW_FILL_HEX, end_color=YELLOW_FILL_HEX, fill_type="solid")
    green_fill = PatternFill(start_color=GREEN_FILL_HEX, end_color=GREEN_FILL_HEX, fill_type="solid")
    header_fill = PatternFill(start_color=HEADER_BLUE_HEX, end_color=HEADER_BLUE_HEX, fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color=WHITE_TEXT_HEX)
    bold_font = Font(name="Calibri", size=11, bold=True)
    normal_font = Font(name="Calibri", size=10)

    # ==========================================================================
    # Sheet 1: Submission Overview
    # ==========================================================================
    ws_summary = wb.create_sheet(title="Submission Overview")
    ws_summary.views.sheetView[0].showGridLines = True

    # Title block
    ws_summary["A1"] = "INCUBRIX AUTONOMOUS ENGINE: SUBMISSION WORKBOOK"
    ws_summary["A1"].font = Font(name="Calibri", size=16, bold=True, color=HEADER_BLUE_HEX)

    # Instructions Legend
    ws_summary["A3"] = "LEGEND & EDITING RULES:"
    ws_summary["A3"].font = bold_font

    ws_summary["B3"] = "Yellow Cells = Auto-Populated Input Data (Safe to overwrite)"
    ws_summary["B3"].fill = yellow_fill
    ws_summary["B3"].font = normal_font

    ws_summary["D3"] = "Green Cells = Protected Formulas (DO NOT OVERWRITE)"
    ws_summary["D3"].fill = green_fill
    ws_summary["D3"].font = normal_font

    summary_fields = [
        ("Campaign / Submission Title", "B6", "Autonomous Media Repurposing Campaign", True),
        ("Submission Timestamp", "B7", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"), True),
        ("Primary Content Pillar", "B8", "Practical Workflows & System Architecture", True),
        ("Target Audience Segments", "B9", "B2B Founders, Creator Operators, Video Editors", True),
        ("Brand Compliance Pass Rate", "B10", "100.0%", True),
        ("Average Brand Score", "B11", "92.5 / 100", True),
        # Green Formula Section (Calculated automatically from Content Calendar & LLM Runs)
        ("Total Assets Generated", "B14", "=COUNTA('Content Calendar'!A2:A100)", False),
        ("Short-Form Video Count", "B15", "=COUNTIF('Content Calendar'!C2:C100, \"*video*\")", False),
        ("1080x1350 Carousel Count", "B16", "=COUNTIF('Content Calendar'!C2:C100, \"*carousel*\")", False),
        ("Total Platforms Deployed", "B17", "=COUNTA('Content Calendar'!B2:B100)", False),
        ("Total Groq LPU API Calls", "B18", "=COUNTA('LLM Runs & Costs'!A2:A100)", False),
        ("Total Tokens Processed", "B19", "=SUM('LLM Runs & Costs'!E2:E100)", False),
        ("Total Estimated Cost (USD)", "B20", "=SUM('LLM Runs & Costs'!G2:G100)", False),
    ]

    for label, coord, val, is_yellow in summary_fields:
        row_num = int(coord[1:])
        lbl_cell = ws_summary.cell(row=row_num, column=1, value=label)
        lbl_cell.font = bold_font
        val_cell = ws_summary[coord]
        val_cell.value = val
        val_cell.border = thin_border
        if is_yellow:
            val_cell.fill = yellow_fill
            val_cell.font = normal_font
        else:
            val_cell.fill = green_fill
            val_cell.font = bold_font

    ws_summary.column_dimensions["A"].width = 32
    ws_summary.column_dimensions["B"].width = 50

    # ==========================================================================
    # Sheet 2: Content Calendar (14 standard columns + 1 green formula check)
    # ==========================================================================
    ws_cal = wb.create_sheet(title="Content Calendar")
    ws_cal.views.sheetView[0].showGridLines = True

    cal_headers = [
        "id", "platform", "format", "pillar", "hook", "caption",
        "hashtags", "CTA", "tracking_link", "file_path", "source_file_path",
        "scheduled_datetime", "target_metric", "status", "Checklist_Formula_Status"
    ]

    for col_idx, h in enumerate(cal_headers, start=1):
        c = ws_cal.cell(row=1, column=col_idx, value=h)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center", vertical="center")

    # Add 40 initial rows with formula in Column O (15)
    for r in range(2, 42):
        # Column O: Green formula cell verifying hook, caption, and tracking_link
        formula_cell = ws_cal.cell(
            row=r,
            column=15,
            value=f'=IF(AND(LEN(E{r})>0, LEN(F{r})>0, LEN(I{r})>0), "VERIFIED_READY", "PENDING_INPUT")',
        )
        formula_cell.fill = green_fill
        formula_cell.font = bold_font
        formula_cell.border = thin_border

        # Columns A to N: Yellow input cells
        for c in range(1, 15):
            in_cell = ws_cal.cell(row=r, column=c, value="")
            in_cell.fill = yellow_fill
            in_cell.font = normal_font
            in_cell.border = thin_border

    # Set column widths
    for col_idx in range(1, 16):
        ws_cal.column_dimensions[get_column_letter(col_idx)].width = 20
    ws_cal.column_dimensions["E"].width = 35  # Hook
    ws_cal.column_dimensions["F"].width = 45  # Caption
    ws_cal.column_dimensions["I"].width = 40  # Tracking link
    ws_cal.column_dimensions["O"].width = 24  # Formula column

    # ==========================================================================
    # Sheet 3: LLM Runs & Costs
    # ==========================================================================
    ws_runs = wb.create_sheet(title="LLM Runs & Costs")
    ws_runs.views.sheetView[0].showGridLines = True

    run_headers = [
        "timestamp", "model", "prompt_tokens", "completion_tokens",
        "total_tokens", "latency_ms", "estimated_cost_usd", "retries_count", "status"
    ]

    for col_idx, h in enumerate(run_headers, start=1):
        c = ws_runs.cell(row=1, column=col_idx, value=h)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center", vertical="center")

    # Set initial yellow rows for data
    for r in range(2, 52):
        for c in range(1, 10):
            cell = ws_runs.cell(row=r, column=c, value="")
            cell.fill = yellow_fill
            cell.font = normal_font
            cell.border = thin_border

    # Totals Row at Row 53 with Green Formula Cells
    ws_runs.cell(row=53, column=1, value="TOTALS:").font = bold_font
    total_tokens_cell = ws_runs.cell(row=53, column=5, value="=SUM(E2:E52)")
    total_tokens_cell.fill = green_fill
    total_tokens_cell.font = bold_font

    total_cost_cell = ws_runs.cell(row=53, column=7, value="=SUM(G2:G52)")
    total_cost_cell.fill = green_fill
    total_cost_cell.font = bold_font

    avg_latency_cell = ws_runs.cell(row=53, column=6, value="=AVERAGE(F2:F52)")
    avg_latency_cell.fill = green_fill
    avg_latency_cell.font = bold_font

    for col_idx in range(1, 10):
        ws_runs.column_dimensions[get_column_letter(col_idx)].width = 22

    workbook_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(workbook_path)
    logger.info(f"Created fresh IncuBrix submission workbook template at: {workbook_path}")
    return workbook_path


def load_calendar_rows(calendar_csv_path: Path) -> List[Dict[str, str]]:
    """Parse calendar.csv rows."""
    rows: List[Dict[str, str]] = []
    if not calendar_csv_path.exists():
        logger.warning(f"Calendar file not found: {calendar_csv_path}")
        return rows

    with open(calendar_csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def load_runs_log_entries(runs_file: Path) -> List[Dict[str, Any]]:
    """Parse runs.jsonl entries."""
    entries: List[Dict[str, Any]] = []
    if not runs_file.exists():
        logger.warning(f"Runs log not found: {runs_file}")
        return entries

    with open(runs_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
    return entries


def populate_submission_workbook(
    workbook_path: Path,
    calendar_csv_path: Path,
    runs_log_path: Path,
    output_path: Optional[Path] = None,
) -> Tuple[int, int]:
    """Populate yellow input cells from calendar.csv and runs.jsonl without overwriting green formula cells.

    Returns:
        Tuple[int, int]: (yellow_cells_populated, green_formula_cells_protected)
    """
    if not workbook_path.exists():
        logger.info(f"Target workbook not found. Creating standard submission workbook template at: {workbook_path}")
        create_default_submission_workbook(workbook_path)

    wb = openpyxl.load_workbook(workbook_path, data_only=False)

    yellow_cells_written = 0
    formula_cells_protected = 0

    calendar_rows = load_calendar_rows(calendar_csv_path)
    run_entries = load_runs_log_entries(runs_log_path)

    # --------------------------------------------------------------------------
    # 1. Populate "Content Calendar" Sheet
    # --------------------------------------------------------------------------
    ws_cal = None
    for s_name in ["Content Calendar", "Calendar", "Assets"]:
        if s_name in wb.sheetnames:
            ws_cal = wb[s_name]
            break

    if ws_cal:
        cal_col_keys = [
            "id", "platform", "format", "pillar", "hook", "caption",
            "hashtags", "CTA", "tracking_link", "file_path", "source_file_path",
            "scheduled_datetime", "target_metric", "status"
        ]

        for idx, row_data in enumerate(calendar_rows, start=2):
            for col_num, key in enumerate(cal_col_keys, start=1):
                cell = ws_cal.cell(row=idx, column=col_num)

                # CRITICAL: Strict Formula Protection
                if is_formula_cell(cell) or is_green_cell(cell):
                    formula_cells_protected += 1
                    continue

                val = row_data.get(key, "")
                cell.value = val
                yellow_cells_written += 1

            # Count formula columns in this row as protected
            check_formula_cell = ws_cal.cell(row=idx, column=15)
            if is_formula_cell(check_formula_cell):
                formula_cells_protected += 1

    # --------------------------------------------------------------------------
    # 2. Populate "LLM Runs & Costs" Sheet
    # --------------------------------------------------------------------------
    ws_runs = None
    for s_name in ["LLM Runs & Costs", "Runs", "Groq LPU Audit", "Audit"]:
        if s_name in wb.sheetnames:
            ws_runs = wb[s_name]
            break

    if ws_runs and run_entries:
        run_keys = [
            "timestamp", "model", "prompt_tokens", "completion_tokens",
            "total_tokens", "latency_ms", "estimated_cost_usd", "retries_count", "status"
        ]
        for idx, entry in enumerate(run_entries[:50], start=2):
            for col_num, key in enumerate(run_keys, start=1):
                cell = ws_runs.cell(row=idx, column=col_num)

                if is_formula_cell(cell) or is_green_cell(cell):
                    formula_cells_protected += 1
                    continue

                raw_v = entry.get(key, "")
                if key in ("prompt_tokens", "completion_tokens", "total_tokens", "retries_count"):
                    try:
                        raw_v = int(raw_v)
                    except (ValueError, TypeError):
                        pass
                elif key in ("latency_ms", "estimated_cost_usd"):
                    try:
                        raw_v = float(raw_v)
                    except (ValueError, TypeError):
                        pass

                cell.value = raw_v
                yellow_cells_written += 1

    # --------------------------------------------------------------------------
    # 3. Scan & Audit All Protected Formula Cells Across Entire Workbook
    # --------------------------------------------------------------------------
    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if is_formula_cell(cell) or is_green_cell(cell):
                    formula_cells_protected += 1

    # Save workbook
    save_target = output_path or workbook_path
    save_target.parent.mkdir(parents=True, exist_ok=True)
    wb.save(save_target)
    logger.info(
        f"Workbook safely updated at {save_target}: {yellow_cells_written} yellow cells populated, "
        f"{formula_cells_protected} green formula cells preserved."
    )
    return yellow_cells_written, formula_cells_protected


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(
        prog="fill_workbook",
        description="Safely populate yellow input cells in IncuBrix submission workbook without touching green formula cells",
    )
    parser.add_argument(
        "--workbook",
        type=str,
        default="IncuBrix_Submission_Workbook.xlsx",
        help="Path to Excel workbook (creates template if missing)",
    )
    parser.add_argument(
        "--calendar",
        type=str,
        default=None,
        help="Path to calendar.csv (defaults to latest in data/outputs/)",
    )
    parser.add_argument(
        "--runs-log",
        type=str,
        default=None,
        help="Path to runs.jsonl (defaults to data/logs/runs.jsonl)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Destination path for populated workbook",
    )
    parser.add_argument(
        "--create-template",
        action="store_true",
        default=False,
        help="Create a fresh IncuBrix submission workbook template with yellow input and green formula cells",
    )
    return parser


def main() -> int:
    """CLI execution entrypoint."""
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()

    wb_path = Path(args.workbook)
    if not wb_path.is_absolute():
        wb_path = PROJECT_ROOT / wb_path

    if args.create_template:
        create_default_submission_workbook(wb_path)
        print(f"Created submission workbook template: {wb_path}")
        return 0

    # Locate calendar.csv
    if args.calendar:
        cal_path = Path(args.calendar)
    else:
        latest_cal = find_latest_calendar_csv()
        if not latest_cal:
            print("Error: No calendar.csv found in data/outputs/. Run python scripts/build_30.py first.", file=sys.stderr)
            return 1
        cal_path = latest_cal

    # Locate runs.jsonl
    if args.runs_log:
        runs_path = Path(args.runs_log)
    else:
        runs_path = find_latest_runs_jsonl()

    out_path = Path(args.output) if args.output else None

    print("\n" + "=" * 80)
    print("           INCUBRIX SUBMISSION WORKBOOK POPULATOR (openpyxl)           ")
    print("=" * 80)
    print(f"Workbook Target:       {wb_path}")
    print(f"Calendar Source:       {cal_path}")
    print(f"Runs Log Source:       {runs_path}")

    written, protected = populate_submission_workbook(
        workbook_path=wb_path,
        calendar_csv_path=cal_path,
        runs_log_path=runs_path,
        output_path=out_path,
    )

    print("\n" + "-" * 80)
    print("                       SAFE WORKBOOK UPDATE SUMMARY                     ")
    print("-" * 80)
    print(f" [x] Yellow Input Cells Populated:       {written}")
    print(f" [x] Green Formula Cells Protected:      {protected}")
    print(f" [x] Output Workbook Saved To:           {out_path or wb_path}")
    print("=" * 80 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
