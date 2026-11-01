"""Production Groq LLM client wrapper with retry, exponential backoff, and metrics logging.

Features:
- Automated retry and exponential backoff on rate limits (HTTP 429 / RateLimitError).
- JSON-mode structured completions validated by Pydantic models.
- Per-call audit logging (model, tokens, latency, estimated cost) appended to data/logs/runs.jsonl.
- Configurable model name loaded from config/settings or runtime parameter.
"""

from __future__ import annotations

import json
from pathlib import Path
import random
import time
from typing import Any, Dict, List, Optional, Type, TypeVar
from groq import APIConnectionError, APIStatusError, Groq, InternalServerError, RateLimitError
from pydantic import BaseModel

from src.config import get_settings
from src.logging.logger import get_logger

logger = get_logger("llm.groq")

T = TypeVar("T", bound=BaseModel)

# Pricing table: (price_per_1m_prompt_tokens, price_per_1m_completion_tokens) in USD
GROQ_MODEL_PRICING: Dict[str, tuple[float, float]] = {
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
    "llama3-70b-8192": (0.59, 0.79),
    "llama3-8b-8192": (0.05, 0.08),
    "mixtral-8x7b-32768": (0.24, 0.24),
    "gemma2-9b-it": (0.20, 0.20),
    "qwen/qwen3.8-27b": (0.20, 0.20),
}
DEFAULT_PRICING: tuple[float, float] = (0.59, 0.79)


class RunMetrics(BaseModel):
    """Detailed audit metrics recorded for every LLM invocation."""

    timestamp: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    latency_seconds: float
    estimated_cost_usd: float
    retries_count: int
    status: str = "success"
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}


class GroqLLM:
    """Enterprise-ready wrapper around the official Groq SDK."""

    def __init__(
        self,
        client: Optional[Groq] = None,
        model: Optional[str] = None,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        jitter: bool = True,
        runs_log_path: Optional[Path] = None,
    ) -> None:
        self.settings = get_settings()
        self._client = client
        self.model = model or self.settings.groq_llm_model
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter

        self.runs_log_path = runs_log_path or (self.settings.logs_dir / "runs.jsonl")
        self.runs_log_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def client(self) -> Groq:
        """Lazy-initialize official Groq client with key from .env only."""
        if self._client is None:
            api_key = self.settings.validate_groq_key()
            self._client = Groq(api_key=api_key)
        return self._client

    @staticmethod
    def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate estimated USD cost based on Groq token pricing."""
        p_cost, c_cost = GROQ_MODEL_PRICING.get(model, DEFAULT_PRICING)
        cost = (prompt_tokens / 1_000_000.0 * p_cost) + (completion_tokens / 1_000_000.0 * c_cost)
        return round(cost, 7)

    def log_run(self, metrics: RunMetrics) -> None:
        """Append invocation audit record to data/logs/runs.jsonl."""
        try:
            with open(self.runs_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(metrics.model_dump()) + "\n")
        except Exception as e:
            logger.error(f"Failed to write run audit metrics to {self.runs_log_path}: {e}")

    def is_rate_limit_error(self, exc: Exception) -> bool:
        """Determine if an exception represents a rate limit or transient error."""
        if isinstance(exc, RateLimitError):
            return True
        if isinstance(exc, (APIConnectionError, InternalServerError)):
            return True
        if isinstance(exc, APIStatusError) and getattr(exc, "status_code", None) in (429, 500, 502, 503, 504):
            return True
        status_code = getattr(exc, "status_code", None)
        if status_code == 429:
            return True
        err_msg = str(exc).lower()
        if "rate limit" in err_msg or "too many requests" in err_msg or "429" in err_msg:
            return True
        return False

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> tuple[str, RunMetrics]:
        """Execute chat completion with exponential backoff on rate limits."""
        target_model = model or self.model
        attempt = 0
        last_exception: Optional[Exception] = None

        start_time = time.perf_counter()

        while attempt <= self.max_retries:
            try:
                call_kwargs: Dict[str, Any] = {
                    "model": target_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    **kwargs,
                }
                if response_format:
                    call_kwargs["response_format"] = response_format

                logger.debug(
                    f"Executing Groq chat completion (attempt {attempt + 1}/{self.max_retries + 1}, model={target_model})"
                )

                response = self.client.chat.completions.create(**call_kwargs)

                elapsed_seconds = time.perf_counter() - start_time
                elapsed_ms = elapsed_seconds * 1000.0

                # Extract response text content safely
                choice_msg = getattr(response.choices[0], "message", None) if getattr(response, "choices", None) else None
                choice_content = getattr(choice_msg, "content", None)
                if isinstance(choice_content, str):
                    content = choice_content
                elif hasattr(response, "message") and isinstance(getattr(response.message, "content", None), str):
                    content = response.message.content
                else:
                    content = str(choice_content or "")

                # Extract token usage
                usage = getattr(response, "usage", None)
                prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
                completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
                total_tokens = getattr(usage, "total_tokens", prompt_tokens + completion_tokens) if usage else 0

                estimated_cost = self.calculate_cost(target_model, prompt_tokens, completion_tokens)

                metrics = RunMetrics(
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    model=target_model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    latency_ms=round(elapsed_ms, 2),
                    latency_seconds=round(elapsed_seconds, 4),
                    estimated_cost_usd=estimated_cost,
                    retries_count=attempt,
                    status="success",
                    metadata=metadata or {},
                )

                self.log_run(metrics)
                logger.info(
                    f"Groq call succeeded ({target_model}): {total_tokens} tokens, {metrics.latency_ms:.1f}ms, ${metrics.estimated_cost_usd:.6f}"
                )
                return content, metrics

            except Exception as e:
                last_exception = e
                # Check for model not found / permission error and fallback to available model
                if ("model_not_found" in str(e) or "does not exist" in str(e)) and target_model != "qwen/qwen3.8-27b":
                    logger.warning(
                        f"Model '{target_model}' not accessible on account: {e}. Automatically switching to available Groq model: 'qwen/qwen3.8-27b'..."
                    )
                    target_model = "qwen/qwen3.8-27b"
                    continue

                if self.is_rate_limit_error(e) and attempt < self.max_retries:
                    # Exponential backoff: base * (factor ^ attempt) + jitter
                    base_delay = self.initial_delay * (self.backoff_factor ** attempt)
                    delay = base_delay + (random.uniform(0.1, 0.5) if self.jitter else 0.0)
                    logger.warning(
                        f"Rate limit / transient error on attempt {attempt + 1}/{self.max_retries + 1}: {e}. Retrying in {delay:.2f}s..."
                    )
                    time.sleep(delay)
                    attempt += 1
                else:
                    elapsed_seconds = time.perf_counter() - start_time
                    metrics = RunMetrics(
                        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        model=target_model,
                        prompt_tokens=0,
                        completion_tokens=0,
                        total_tokens=0,
                        latency_ms=round(elapsed_seconds * 1000.0, 2),
                        latency_seconds=round(elapsed_seconds, 4),
                        estimated_cost_usd=0.0,
                        retries_count=attempt,
                        status="failed",
                        error=str(e),
                        metadata=metadata or {},
                    )
                    self.log_run(metrics)
                    logger.error(f"Groq call failed permanently after {attempt} retries: {e}")
                    raise e

        # If loop finishes without returning
        if last_exception:
            raise last_exception
        raise RuntimeError("Failed to complete Groq request.")

    def create_structured_completion(
        self,
        messages: List[Dict[str, str]],
        response_model: Type[T],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> T:
        """Call Groq with JSON mode and return strongly-typed Pydantic model."""
        content, _ = self.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            metadata=metadata,
            **kwargs,
        )

        try:
            # Parse and validate with Pydantic
            validated = response_model.model_validate_json(content)
            return validated
        except Exception as err:
            logger.error(f"Failed to validate response into {response_model.__name__}: {err}\nRaw content: {content}")
            # Try parsing dict first if model_validate_json failed on whitespace
            try:
                raw_dict = json.loads(content)
                return response_model.model_validate(raw_dict)
            except Exception:
                raise ValueError(
                    f"Output from Groq could not be parsed into {response_model.__name__}: {err}"
                ) from err
