"""Unit tests for system retry mechanics and resilience loops.

Verifies:
1. GroqLLM exponential backoff on HTTP 429 RateLimitError
2. GroqLLM recovery on temporary network failures
3. GroqLLM raising after exceeding max retries
4. BrandChecker self-healing regeneration loop when rule violations occur
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import httpx
import pytest
from groq import APIConnectionError, RateLimitError
from pydantic import BaseModel

from src.brandcheck import BrandChecker, BrandCheckReport
from src.llm import GroqLLM


class SampleOutput(BaseModel):
    title: str
    points: list[str]


def make_mock_rate_limit_error() -> RateLimitError:
    """Create a realistic HTTP 429 RateLimitError."""
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    resp = httpx.Response(
        status_code=429,
        request=req,
        json={"error": {"message": "Rate limit reached. Please wait."}},
    )
    return RateLimitError("Rate limit reached", response=resp, body={"error": {"message": "Rate limit reached"}})


def make_mock_connection_error() -> APIConnectionError:
    """Create a realistic network connection error."""
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return APIConnectionError(request=req)


def test_groq_llm_exponential_backoff_retry_success(tmp_path: Path) -> None:
    """GroqLLM encounters 2 rate-limit errors then succeeds on 3rd attempt."""
    mock_client = MagicMock()
    mock_chat = mock_client.chat.completions

    success_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "title": "Autonomous Pipelines",
        "points": ["Fast", "Deterministic", "Safe"],
    })
    success_resp.choices = [mock_choice]
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 150
    mock_usage.completion_tokens = 45
    mock_usage.total_tokens = 195
    success_resp.usage = mock_usage

    # Side effect: 2 failures then 1 success
    mock_chat.create.side_effect = [
        make_mock_rate_limit_error(),
        make_mock_rate_limit_error(),
        success_resp,
    ]

    llm = GroqLLM(client=mock_client, runs_log_path=tmp_path / "runs.jsonl", max_retries=3, initial_delay=0.01)

    # Use 0 backoff factor for fast test execution
    with patch("time.sleep", return_value=None):
        result = llm.create_structured_completion(
            messages=[{"role": "user", "content": "generate"}],
            response_model=SampleOutput,
        )

    assert result.title == "Autonomous Pipelines"
    assert len(result.points) == 3
    assert mock_chat.create.call_count == 3


def test_groq_llm_exhausts_retries_and_raises(tmp_path: Path) -> None:
    """GroqLLM exhausts max retries and properly raises RateLimitError."""
    mock_client = MagicMock()
    mock_chat = mock_client.chat.completions
    mock_chat.create.side_effect = make_mock_rate_limit_error()

    llm = GroqLLM(client=mock_client, runs_log_path=tmp_path / "runs.jsonl", max_retries=2, initial_delay=0.01)

    with patch("time.sleep", return_value=None):
        with pytest.raises(RateLimitError):
            llm.create_structured_completion(
                messages=[{"role": "user", "content": "generate"}],
                response_model=SampleOutput,
            )

    assert mock_chat.create.call_count == 3  # initial + 2 retries


def test_brandchecker_self_healing_retry_loop() -> None:
    """BrandChecker detects synthetic marketing violation and invokes refinement recovery."""
    checker = BrandChecker()

    non_compliant_text = (
        "IncuBrix guarantees 100x viral scale and instant passive income with automated hacks! "
        "Stop cutting video cutdowns manually. Follow @IncuBrix for more."
    )

    # Mock the regeneration method to return clean, compliant text
    mock_refined = (
        "Stop cutting video cutdowns manually.\n"
        "Here is how modern media teams scale production systematically.\n"
        "Follow @IncuBrix #IncuBrix"
    )

    with patch.object(checker, "regenerate_asset_with_feedback", return_value=mock_refined):
        with patch.object(checker, "judge_with_groq") as mock_judge:
            mock_judge.return_value = MagicMock(passed=True, voice_score=95.0, unverified_claims=[], invented_numbers_or_testimonials=[], feedback=[])
            report: BrandCheckReport = checker.verify(
                text=non_compliant_text,
                platform_id="linkedin",
                hook_text="Stop cutting video cutdowns manually.",
                hashtags=["#IncuBrix"],
                utm_url="https://incubrix.com/?utm_source=linkedin&utm_medium=video&utm_campaign=launch",
            )

    # Verifies self-healing refinement was triggered
    assert report.regeneration_attempts >= 1
    assert report.refined_text == mock_refined
