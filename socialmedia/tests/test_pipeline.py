"""End-to-end integration test for the Incubrix pipeline with mocked external services."""

from pathlib import Path
from unittest.mock import MagicMock
from src.brandcheck.models import BrandCheckReport
from src.generate.models import GenerationResult, PlatformPost, ScriptBeat
from src.pipeline import IncubrixPipeline


def test_pipeline_dry_run_with_mocks(tmp_path: Path) -> None:
    # 1. Create a temporary source text
    input_file = tmp_path / "test_pitch.txt"
    input_file.write_text(
        "Incubrix is innovating autonomous agent pipelines for modern engineering scale.",
        encoding="utf-8",
    )

    pipeline = IncubrixPipeline()

    # 2. Mock Groq LLM generation
    mock_generation = GenerationResult(
        topic="Autonomous Agents",
        core_message="Accelerating scale through autonomous workflows",
        script=ScriptBeat(
            hook="Stop writing repetitive code.",
            body_points=["Build faster", "Scale seamlessly"],
            call_to_action="Follow Incubrix for more.",
            estimated_duration_sec=20,
        ),
        platform_posts={
            "tiktok": PlatformPost(
                platform_id="tiktok",
                caption="Autonomous software engineering is here! #Incubrix #TechInnovation",
                hashtags=["#Incubrix", "#TechInnovation"],
                visual_search_term="technology",
            )
        },
        visual_search_terms=["code", "technology"],
    )
    pipeline.generator.generate = MagicMock(return_value=mock_generation)  # type: ignore

    # 3. Mock BrandChecker
    mock_brand_report = BrandCheckReport(
        passed=True,
        score=96.0,
        rule_score=95.0,
        llm_tone_score=97.0,
        violations=[],
    )
    pipeline.brandchecker.verify = MagicMock(return_value=mock_brand_report)  # type: ignore

    # 4. Mock Pixabay retrieval to avoid outbound HTTP in unit test
    pipeline.designer.search_pixabay_assets = MagicMock(return_value=[])  # type: ignore

    # 5. Run pipeline with skip_video=True
    result = pipeline.run(
        input_path=input_file,
        platforms=["tiktok"],
        skip_video=True,
        force=True,
    )

    assert result.success is True
    assert result.topic == "Autonomous Agents"
    assert result.brandcheck_passed is True
    assert result.brandcheck_score == 96.0
    assert Path(result.output_directory).exists()
    assert Path(result.manifest_file).exists()
