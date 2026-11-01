"""CLI Entry point for Incubrix Engine.

Runs the full autonomous production pipeline:
ingest -> transcribe -> insights -> generate -> brandcheck -> dedupe -> video/graphics -> export.

Usage:
    python -m src.main --input data/inputs/sample_input.txt
    python -m src.main --input content/sources/sample_ai_agent_post.txt --refresh
    python -m src.main --input data/inputs/sample_input.txt --simulate-failure
    python -m src.main --input content/sources/sample_ai_agent_post.txt --skip-video
"""

from __future__ import annotations

import argparse
from datetime import timedelta
from pathlib import Path
import sys

from src import __version__
from src.logging.logger import get_logger, setup_logging
from src.pipeline import IncubrixPipeline, PipelineResult

logger = get_logger("main")


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser with refresh, failure-injection, and platform flags."""
    parser = argparse.ArgumentParser(
        prog="incubrix-engine",
        description="Incubrix Autonomous Social Media Production Engine powered by Groq",
    )
    parser.add_argument(
        "--input",
        "-i",
        dest="input_path",
        required=True,
        type=str,
        help="Path to input text, markdown, audio, or video file",
    )
    parser.add_argument(
        "--platform",
        "-p",
        dest="platforms",
        nargs="+",
        default=None,
        help="Target platform(s): tiktok, instagram_reels, youtube_shorts, linkedin, x_twitter",
    )
    parser.add_argument(
        "--skip-video",
        action="store_true",
        default=False,
        help="Skip MoviePy video rendering (generates scripts, thumbnails, carousels, and copy only)",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        default=False,
        help="Bypass deduplication check and force reprocessing",
    )
    parser.add_argument(
        "--refresh",
        "-r",
        action="store_true",
        default=False,
        help="Refresh mode: process only new or modified input; skip already cached items",
    )
    parser.add_argument(
        "--simulate-failure",
        "--inject-failure",
        "--fail-brandcheck",
        dest="simulate_failure",
        action="store_true",
        default=False,
        help="Demo mode: injects a synthetic brand check violation to showcase self-healing automated regeneration",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def format_runtime(seconds: float) -> str:
    """Format seconds into readable human string."""
    if seconds < 60:
        return f"{seconds:.2f}s"
    m, s = divmod(seconds, 60)
    return f"{int(m)}m {s:.1f}s ({seconds:.2f}s total)"


def print_summary_report(result: PipelineResult) -> None:
    """Print an executive-ready runtime, cost, and asset summary table."""
    c = result.cost_metrics
    cost_str = f"${c.estimated_cost_usd:.6f}" if c.estimated_cost_usd > 0 else "$0.000000 (Mock/Cached)"
    runtime_str = format_runtime(result.runtime_seconds)

    print("\n" + "=" * 80)
    print("                     INCUBRIX ENGINE RUN SUMMARY & AUDIT                     ")
    print("=" * 80)
    print(f"Input Source:          {result.input_file}")
    print(f"Topic / Theme:         {result.topic}")
    print(f"Total Runtime:         {runtime_str}")

    if result.refreshed_skipped:
        print("Execution Status:      SKIPPED (Refresh mode: Input is already processed & up-to-date)")
    elif result.failure_injected:
        print("Execution Status:      SUCCESS (Self-healing active: Recovered from injected failure!)")
    else:
        print("Execution Status:      SUCCESS")

    print("\n" + "-" * 80)
    print("                   GROQ LPU INFERENCE & COMPUTE COST BREAKDOWN                 ")
    print("-" * 80)
    print(f"Total Groq API Calls:  {c.total_calls}")
    print(f"Prompt Tokens:         {c.prompt_tokens:,}")
    print(f"Completion Tokens:     {c.completion_tokens:,}")
    print(f"Total Tokens:          {c.total_tokens:,}")
    print(f"Total Estimated Cost:  {cost_str} USD")
    if c.models_used:
        print(f"Models Engaged:        {', '.join(c.models_used)}")

    print("\n" + "-" * 80)
    print("                    CONTENT ASSETS & DISTRIBUTION EXPORTS                      ")
    print("-" * 80)
    print(f"Total Assets Created:  {result.assets_count}")
    print(f"Brand Compliance:      {'PASSED' if result.brandcheck_passed else 'FLAGGED'} ({result.brandcheck_score}/100)")
    if result.calendar_csv:
        print(f"Calendar Schedule CSV: {result.calendar_csv}")
    if result.buffer_schedule_csv:
        print(f"Buffer Scheduler CSV:  {result.buffer_schedule_csv}")
    if result.hootsuite_schedule_csv:
        print(f"Hootsuite CSV:         {result.hootsuite_schedule_csv}")
    print(f"Master Manifest:       {result.manifest_file}")
    print(f"Distribution Bundle:   {result.output_directory}")
    print("=" * 80 + "\n")


def main() -> int:
    """Execute Incubrix Engine CLI."""
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()

    input_path = Path(args.input_path)
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        print(f"Error: Inbound file does not exist: {input_path}", file=sys.stderr)
        return 1

    try:
        pipeline = IncubrixPipeline()
        result = pipeline.run(
            input_path=input_path,
            platforms=args.platforms,
            skip_video=args.skip_video,
            force=args.force,
            refresh_mode=args.refresh,
            simulate_failure=args.simulate_failure,
        )

        print_summary_report(result)
        return 0

    except Exception as e:
        logger.error(f"Execution failed: {e}", exc_info=True)
        print(f"\nExecution failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
