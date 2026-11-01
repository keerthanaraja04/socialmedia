"""Unit tests for src/main.py CLI parser, refresh mode, failure injection, and runtime/cost summary."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.main import build_parser, format_runtime, main, print_summary_report
from src.pipeline import CostMetrics, PipelineResult


def test_cli_parser_flags() -> None:
    parser = build_parser()

    # 1. Normal run
    args = parser.parse_args(["--input", "content/sources/sample.txt"])
    assert args.input_path == "content/sources/sample.txt"
    assert args.refresh is False
    assert args.simulate_failure is False
    assert args.skip_video is False
    assert args.force is False

    # 2. Refresh mode
    args_refresh = parser.parse_args(["--input", "doc.txt", "--refresh"])
    assert args_refresh.refresh is True

    # 3. Failure injection flag
    args_fail = parser.parse_args(["--input", "doc.txt", "--simulate-failure"])
    assert args_fail.simulate_failure is True

    # Alternative alias
    args_fail2 = parser.parse_args(["--input", "doc.txt", "--fail-brandcheck"])
    assert args_fail2.simulate_failure is True


def test_format_runtime() -> None:
    assert format_runtime(14.25) == "14.25s"
    assert "1m 30.0s" in format_runtime(90.0)


def test_print_summary_report_runs_cleanly(capsys: pytest.CaptureFixture) -> None:
    result = PipelineResult(
        success=True,
        input_file="sample.txt",
        topic="Autonomous Media",
        brandcheck_passed=True,
        brandcheck_score=96.0,
        output_directory="data/outputs/sample_run",
        manifest_file="data/outputs/sample_run/manifest.json",
        calendar_csv="data/outputs/sample_run/calendar.csv",
        buffer_schedule_csv="data/outputs/sample_run/buffer_schedule.csv",
        hootsuite_schedule_csv="data/outputs/sample_run/hootsuite_schedule.csv",
        runtime_seconds=12.4,
        cost_metrics=CostMetrics(
            total_calls=4,
            prompt_tokens=2500,
            completion_tokens=850,
            total_tokens=3350,
            estimated_cost_usd=0.002145,
            models_used=["llama-3.3-70b-versatile"],
        ),
        assets_count=10,
        refreshed_skipped=False,
        failure_injected=True,
    )

    print_summary_report(result)
    captured = capsys.readouterr()

    assert "INCUBRIX ENGINE RUN SUMMARY" in captured.out
    assert "12.40s" in captured.out
    assert "$0.002145 USD" in captured.out
    assert "Recovered from injected failure" in captured.out
    assert "calendar.csv" in captured.out
    assert "buffer_schedule.csv" in captured.out


@patch("src.main.IncubrixPipeline")
def test_main_cli_execution_success(mock_pipeline_cls: MagicMock, tmp_path: Path) -> None:
    input_file = tmp_path / "pitch.txt"
    input_file.write_text("Autonomous AI repurposing pipeline.", encoding="utf-8")

    mock_inst = MagicMock()
    mock_inst.run.return_value = PipelineResult(
        success=True,
        input_file=str(input_file),
        topic="Autonomous AI",
        brandcheck_passed=True,
        brandcheck_score=95.0,
        output_directory=str(tmp_path / "out"),
        manifest_file=str(tmp_path / "out" / "manifest.json"),
        calendar_csv=str(tmp_path / "out" / "calendar.csv"),
        runtime_seconds=8.5,
        cost_metrics=CostMetrics(total_calls=2, total_tokens=1200, estimated_cost_usd=0.0008),
        assets_count=5,
    )
    mock_pipeline_cls.return_value = mock_inst

    with patch("sys.argv", ["main.py", "--input", str(input_file), "--refresh", "--simulate-failure"]):
        ret = main()
        assert ret == 0

    # Assert pipeline called with flags
    mock_inst.run.assert_called_once_with(
        input_path=input_file,
        platforms=None,
        skip_video=False,
        force=False,
        refresh_mode=True,
        simulate_failure=True,
    )
