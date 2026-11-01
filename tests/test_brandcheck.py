"""Unit tests for src/brandcheck.py rule-based checks, Groq judge, and regeneration loop."""

import json
from unittest.mock import MagicMock
import pytest

from src.brandcheck import BrandChecker, BrandCheckReport, GroqJudgeResult, RuleCheckResult


def test_rule_based_checks_banned_phrases_and_length() -> None:
    checker = BrandChecker(client=None)

    # 1. Test banned phrase & missing UTM
    bad_text = "This new tool is an absolute game-changer! Replace your editor today."
    res = checker.check_deterministic_rules(bad_text, platform_id="linkedin")

    assert not res.passed
    assert len(res.banned_phrases_found) >= 2
    assert "game-changer" in res.banned_phrases_found
    assert "replace your editor" in res.banned_phrases_found
    assert res.utm_missing is True

    # 2. Test length limit violation for Instagram (max 2200 chars)
    long_caption = "A" * 2500
    res_len = checker.check_deterministic_rules(long_caption, platform_id="instagram")
    assert not res_len.passed
    assert any("exceeds Instagram limit" in v for v in res_len.violations)


def test_rule_based_checks_clean_asset_passes() -> None:
    checker = BrandChecker(client=None)
    clean_text = (
        "Stop losing viewers in the first 2 seconds.\n\n"
        "Here is the exact 3-step repurposing pipeline modern media teams use:\n"
        "1. Extract the high-voltage hook.\n"
        "2. Align captions inside safe zones.\n"
        "3. Batch export for 4 platforms.\n\n"
        "Full workflow breakdown: https://incubrix.com/?utm_source=linkedin&utm_medium=video&utm_campaign=launch&utm_content=hook\n"
        "#IncuBrix #CreatorEconomy"
    )

    res = checker.check_deterministic_rules(
        text=clean_text,
        platform_id="linkedin",
        utm_url="https://incubrix.com/?utm_source=linkedin&utm_medium=video&utm_campaign=launch&utm_content=hook",
        hook_text="Stop losing viewers in the first 2 seconds.",
        hashtags=["#IncuBrix", "#CreatorEconomy"],
    )

    assert res.passed is True
    assert len(res.banned_phrases_found) == 0
    assert res.hook_missing is False
    assert res.utm_missing is False
    assert res.rule_score >= 85.0


def test_groq_judge_flags_unverified_claims_and_invented_metrics() -> None:
    mock_groq = MagicMock()
    mock_choice = MagicMock()

    # Mock Groq response flagging unverified feature and fake numbers
    mock_judge_output = {
        "voice_score": 60.0,
        "unverified_claims": ["IncuBrix renders 8K video in 0.5 seconds (not in VERIFIED_FEATURES)"],
        "invented_numbers_or_testimonials": ["Claiming 500,000 creators use IncuBrix", "Quote from fake customer Sarah"],
        "feedback": ["Remove 8K rendering claim", "Remove fake 500,000 creator metric"],
        "suggested_revision": "Learn how IncuBrix streamlines short-form video repurposing.",
    }
    mock_choice.message.content = json.dumps(mock_judge_output)
    mock_groq.chat.completions.create.return_value.choices = [mock_choice]

    checker = BrandChecker(client=mock_groq)
    judge_res = checker.judge_with_groq("IncuBrix renders 8K video in 0.5s for 500,000 creators worldwide!")

    assert judge_res.passed is False
    assert len(judge_res.unverified_claims) >= 1
    assert any("8K video" in c for c in judge_res.unverified_claims)
    assert len(judge_res.invented_numbers_or_testimonials) >= 1


def test_automated_regeneration_loop_recovers_asset() -> None:
    """Validate that failing assets are regenerated with feedback and pass on retry."""
    mock_groq = MagicMock()

    # Step 1: Initial Groq judge flags unverified claim
    mock_judge_fail = MagicMock()
    mock_choice_fail = MagicMock()
    mock_choice_fail.message.content = json.dumps({
        "voice_score": 65.0,
        "unverified_claims": ["Automatic holographic rendering (not in VERIFIED_FEATURES)"],
        "invented_numbers_or_testimonials": [],
        "feedback": ["Remove holographic claim"],
        "suggested_revision": "Clean version",
    })
    mock_judge_fail.choices = [mock_choice_fail]

    # Step 2: Groq regenerates asset cleanly
    mock_regen = MagicMock()
    mock_choice_regen = MagicMock()
    clean_rewritten = (
        "Stop wasting ten hours editing cutdowns.\n\n"
        "Here is the proven 3-step repurposing pipeline for creators.\n\n"
        "Guide: https://incubrix.com/?utm_source=linkedin&utm_medium=video&utm_campaign=launch&utm_content=hook\n"
        "#IncuBrix #CreatorEconomy"
    )
    mock_choice_regen.message.content = json.dumps({"regenerated_text": clean_rewritten})
    mock_regen.choices = [mock_choice_regen]

    # Step 3: Second Groq judge call passes
    mock_judge_pass = MagicMock()
    mock_choice_pass = MagicMock()
    mock_choice_pass.message.content = json.dumps({
        "voice_score": 95.0,
        "unverified_claims": [],
        "invented_numbers_or_testimonials": [],
        "feedback": [],
        "suggested_revision": clean_rewritten,
    })
    mock_judge_pass.choices = [mock_choice_pass]

    mock_groq.chat.completions.create.side_effect = [
        mock_judge_fail,  # 1. initial judge
        mock_regen,       # 2. rewrite
        mock_judge_pass,  # 3. retry judge
    ]

    checker = BrandChecker(client=mock_groq, max_regeneration_attempts=2)
    report = checker.verify(
        text="IncuBrix has automatic holographic rendering that guarantees viral reach!",
        platform_id="linkedin",
        utm_url="https://incubrix.com/?utm_source=linkedin&utm_medium=video&utm_campaign=launch&utm_content=hook",
        hook_text="Stop wasting hours.",
        hashtags=["#IncuBrix"],
    )

    assert report.regeneration_attempts == 1
    assert report.status == "regenerated_and_passed"
    assert report.passed is True
    assert "Stop wasting ten hours" in report.refined_text


def test_regeneration_loop_exceeds_max_retries_and_flags() -> None:
    """Validate that persistent failures are flagged after 2 attempts."""
    mock_groq = MagicMock()
    # Continuous failure response
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "voice_score": 50.0,
        "unverified_claims": ["Persistent unverified claim"],
        "invented_numbers_or_testimonials": [],
        "feedback": ["Persistent failure"],
        "suggested_revision": "Still bad",
    })
    mock_groq.chat.completions.create.return_value.choices = [mock_choice]

    checker = BrandChecker(client=mock_groq, max_regeneration_attempts=2)
    report = checker.verify(
        text="This tool is a game-changer with guaranteed returns and unverified 8K magic!",
        platform_id="linkedin",
    )

    assert report.regeneration_attempts == 2
    assert report.status == "flagged_failed"
    assert report.passed is False
    assert len(report.violations) >= 1
