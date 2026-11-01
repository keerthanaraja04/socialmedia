"""Unit tests for src/dedupe.py hash comparison and scikit-learn TF-IDF cosine similarity."""

from pathlib import Path
import pytest
from src.dedupe import ContentDeduplicator, DedupeResult


def test_dedupe_exact_hash_match(tmp_path: Path) -> None:
    cache_file = tmp_path / "test_dedupe.json"
    outputs_dir = tmp_path / "outputs"
    deduper = ContentDeduplicator(cache_file=cache_file, outputs_dir=outputs_dir)

    sample_text = "The biggest bottleneck for podcast creators is manually cutting 15 vertical clips."
    res1 = deduper.check(sample_text)
    assert not res1.is_duplicate

    deduper.record("job_001", sample_text)

    # Check exact match
    res2 = deduper.check(sample_text)
    assert res2.is_duplicate
    assert res2.similarity_score == 1.0
    assert res2.matched_id == "job_001"
    assert "SHA-256" in res2.reason


def test_dedupe_tfidf_cosine_similarity(tmp_path: Path) -> None:
    """Validate embedding-free TF-IDF cosine similarity detects near-duplicates."""
    cache_file = tmp_path / "test_dedupe.json"
    outputs_dir = tmp_path / "outputs"
    deduper = ContentDeduplicator(cache_file=cache_file, outputs_dir=outputs_dir)

    text_original = (
        "Creators are burning out trying to cut 15 videos manually every week. "
        "Here is the exact 3-step repurposing pipeline to automate the tedious cutdowns."
    )
    deduper.record("campaign_original", text_original)

    # Near-duplicate text with synonymous words and minor rephrasing
    text_variant = (
        "Creators are burning out trying to edit 15 videos manually each week. "
        "Here is the proven 3-step repurposing pipeline to automate tedious cutdowns."
    )

    res = deduper.check(text_variant, threshold=0.75)
    assert res.is_duplicate is True
    assert res.similarity_score >= 0.75
    assert "TF-IDF cosine" in res.reason
    assert res.matched_id == "campaign_original"


def test_dedupe_scans_previously_exported_assets_in_outputs(tmp_path: Path) -> None:
    """Ensure reruns never repeat content found in previously exported data/outputs/ directories."""
    outputs_dir = tmp_path / "data" / "outputs"
    prev_run_dir = outputs_dir / "20261020_120000_hook_mechanics" / "tiktok"
    prev_run_dir.mkdir(parents=True, exist_ok=True)

    exported_text = (
        "Why your hook fails in the first 2 seconds on TikTok.\n\n"
        "If you do not stop the scroll immediately, your retention drops 70%.\n"
        "Follow for weekly creator breakdowns."
    )
    (prev_run_dir / "post_content.txt").write_text(exported_text, encoding="utf-8")

    cache_file = tmp_path / "cache.json"

    # Initialize deduper pointing to the outputs dir
    deduper = ContentDeduplicator(cache_file=cache_file, outputs_dir=outputs_dir)

    # Re-run candidate with identical content
    res_exact = deduper.check(exported_text)
    assert res_exact.is_duplicate is True
    assert "post_content.txt" in str(res_exact.matched_file)

    # Re-run candidate with high TF-IDF similarity
    near_dup = (
        "Why your video hook fails in the first 2 seconds on TikTok.\n\n"
        "If you fail to stop the scroll immediately, retention drops 70%.\n"
        "Follow for more creator breakdowns."
    )
    res_near = deduper.check(near_dup, threshold=0.75)
    assert res_near.is_duplicate is True
    assert res_near.similarity_score >= 0.75
    assert "TF-IDF cosine" in res_near.reason


def test_dedupe_distinct_content_passes(tmp_path: Path) -> None:
    cache_file = tmp_path / "test_dedupe.json"
    outputs_dir = tmp_path / "outputs"
    deduper = ContentDeduplicator(cache_file=cache_file, outputs_dir=outputs_dir)

    deduper.record("doc_a", "Deep dive into podcast audio noise reduction and microphone acoustic foam treatment.")
    res = deduper.check("How to structure high-converting B2B LinkedIn carousel slide decks.")

    assert res.is_duplicate is False
    assert res.similarity_score < 0.25


def test_dedupe_empty_and_whitespace_handling(tmp_path: Path) -> None:
    cache_file = tmp_path / "test_dedupe.json"
    outputs_dir = tmp_path / "outputs"
    deduper = ContentDeduplicator(cache_file=cache_file, outputs_dir=outputs_dir)

    res = deduper.check("   ")
    assert res.is_duplicate is False
    assert res.similarity_score == 0.0

