"""Unit tests for src/llm.py Groq client wrapper, retry mechanism, and runs.jsonl logging."""

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from groq import RateLimitError
from pydantic import BaseModel
import httpx

from src.llm import GroqLLM


class DemoOutput(BaseModel):
    """Pydantic model for structured completion demo."""

    summary: str
    confidence_score: int
    tags: list[str]


def create_mock_rate_limit_error() -> RateLimitError:
    """Helper to construct a realistic Groq RateLimitError (HTTP 429)."""
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(
        status_code=429,
        request=request,
        json={"error": {"message": "Rate limit exceeded. Please wait 1s before retrying."}},
    )
    return RateLimitError(
        message="Rate limit exceeded",
        response=response,
        body={"error": {"message": "Rate limit exceeded"}},
    )


def test_groq_llm_recovery_from_failure_demo(tmp_path: Path) -> None:
    """Demonstrate recovery from failure: 1 rate-limit failure followed by success on retry.

    Validates:
    - First call raises RateLimitError (HTTP 429)
    - GroqLLM catches it, applies exponential backoff, and retries
    - Second call succeeds with JSON-mode structured output
    - Pydantic validates the response into DemoOutput
    - Call metrics (model, tokens, latency, cost, retries=1) are logged to runs.jsonl
    """
    mock_client = MagicMock()
    mock_chat = mock_client.chat.completions

    # Prepare Mock Success Response
    mock_success_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(
        {
            "summary": "Agentic AI pipeline automated successfully.",
            "confidence_score": 98,
            "tags": ["agents", "resilience", "recovery"],
        }
    )
    mock_success_response.choices = [mock_choice]

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 150
    mock_usage.completion_tokens = 50
    mock_usage.total_tokens = 200
    mock_success_response.usage = mock_usage

    # Simulate 1 RateLimit failure, then Success
    mock_chat.create.side_effect = [
        create_mock_rate_limit_error(),
        mock_success_response,
    ]

    runs_log_file = tmp_path / "runs.jsonl"

    llm = GroqLLM(
        client=mock_client,
        model="llama-3.3-70b-versatile",
        max_retries=3,
        initial_delay=0.01,  # Fast backoff for tests
        backoff_factor=1.0,
        jitter=False,
        runs_log_path=runs_log_file,
    )

    # Execute structured completion
    result: DemoOutput = llm.create_structured_completion(
        messages=[{"role": "user", "content": "Generate resilience report"}],
        response_model=DemoOutput,
    )

    # 1. Assert call count was 2 (1 failure + 1 retry = recovered!)
    assert mock_chat.create.call_count == 2

    # 2. Assert structured output validated by Pydantic
    assert isinstance(result, DemoOutput)
    assert result.summary == "Agentic AI pipeline automated successfully."
    assert result.confidence_score == 98
    assert "recovery" in result.tags

    # 3. Assert runs.jsonl audit log was generated
    assert runs_log_file.exists()
    lines = runs_log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    audit_entry = json.loads(lines[0])
    assert audit_entry["model"] == "llama-3.3-70b-versatile"
    assert audit_entry["prompt_tokens"] == 150
    assert audit_entry["completion_tokens"] == 50
    assert audit_entry["total_tokens"] == 200
    assert audit_entry["retries_count"] == 1  # Verified recovery from 1 failure!
    assert audit_entry["status"] == "success"
    assert audit_entry["latency_ms"] >= 0.0
    assert audit_entry["latency_seconds"] >= 0.0
    assert audit_entry["estimated_cost_usd"] > 0.0


def test_groq_llm_configurable_model(tmp_path: Path) -> None:
    """Validate configurable model name in GroqLLM and per-call override."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="Hello!"))]
    mock_resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    mock_client.chat.completions.create.return_value = mock_resp

    runs_log_file = tmp_path / "runs.jsonl"

    llm = GroqLLM(
        client=mock_client,
        model="mixtral-8x7b-32768",
        runs_log_path=runs_log_file,
    )

    # Test default model configured
    _, metrics = llm.chat_completion(messages=[{"role": "user", "content": "hi"}])
    assert metrics.model == "mixtral-8x7b-32768"

    # Test per-call model override
    _, metrics2 = llm.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="llama-3.1-8b-instant",
    )
    assert metrics2.model == "llama-3.1-8b-instant"


def test_groq_llm_exhausted_retries_logs_failure(tmp_path: Path) -> None:
    """Validate that when retries are exhausted, an error is raised and failure is logged."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = create_mock_rate_limit_error()

    runs_log_file = tmp_path / "runs.jsonl"
    llm = GroqLLM(
        client=mock_client,
        max_retries=1,
        initial_delay=0.01,
        jitter=False,
        runs_log_path=runs_log_file,
    )

    with pytest.raises(RateLimitError):
        llm.chat_completion(messages=[{"role": "user", "content": "hi"}])

    assert mock_client.chat.completions.create.call_count == 2
    assert runs_log_file.exists()
    audit_entry = json.loads(runs_log_file.read_text(encoding="utf-8").strip())
    assert audit_entry["status"] == "failed"
    assert "Rate limit exceeded" in audit_entry["error"]
