"""Content and semantic deduplication engine for IncuBrix.

Features:
- Exact hash matching (SHA-256).
- Embedding-free similarity via TF-IDF cosine similarity (scikit-learn).
- Scans all previously exported assets in data/outputs (post_content.txt, metadata.json, manifest.json)
  so reruns never repeat existing content.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Prioritize project root in sys.path
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
_src_dir = str(Path(__file__).resolve().parent)
while _src_dir in sys.path:
    sys.path.remove(_src_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.config import get_settings
from src.logging.logger import get_logger

logger = get_logger("dedupe")


class DedupeResult(BaseModel):
    """Result of duplicate detection check."""

    is_duplicate: bool
    similarity_score: float = Field(ge=0.0, le=1.0)
    matched_id: Optional[str] = None
    matched_file: Optional[str] = None
    reason: str = "Unique content"


class DedupeRecord(BaseModel):
    content_id: str
    content_hash: str
    timestamp: float
    snippet: str
    tokens: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ContentDeduplicator:
    """Detects duplicate and near-duplicate content using hashes and TF-IDF cosine similarity."""

    def __init__(
        self,
        cache_file: Optional[Path] = None,
        outputs_dir: Optional[Path] = None,
    ) -> None:
        self.settings = get_settings()
        self.cache_file = cache_file or (self.settings.data_dir / "dedupe_cache.json")
        self.outputs_dir = outputs_dir or self.settings.outputs_dir

        self.records: Dict[str, DedupeRecord] = {}
        self.exported_corpus: List[Tuple[str, str, str]] = []  # [(doc_id, text, source_file_path)]

        self._load_cache()
        self.refresh_exported_assets()

    def _load_cache(self) -> None:
        """Load persistent records from json file."""
        if not self.cache_file.exists():
            return
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("records", []):
                rec = DedupeRecord.model_validate(item)
                self.records[rec.content_id] = rec
            logger.debug(f"Loaded {len(self.records)} dedupe records from cache.")
        except Exception as e:
            logger.warning(f"Failed to load dedupe cache: {e}")

    def _save_cache(self) -> None:
        """Persist records to disk."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": "2.0",
                "updated_at": time.time(),
                "records": [rec.model_dump() for rec in self.records.values()],
            }
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save dedupe cache: {e}")

    def refresh_exported_assets(self) -> None:
        """Scan all previous output folders under data/outputs/ and index their texts."""
        self.exported_corpus.clear()

        # 1. Add records from cache
        for rec_id, rec in self.records.items():
            if rec.snippet:
                self.exported_corpus.append((rec_id, rec.snippet, str(self.cache_file)))

        # 2. Traverse data/outputs for exported copy
        if not self.outputs_dir.exists():
            return

        for text_path in self.outputs_dir.rglob("post_content.txt"):
            try:
                content = text_path.read_text(encoding="utf-8", errors="replace").strip()
                if content:
                    doc_id = f"export_{text_path.parent.name}_{text_path.name}"
                    self.exported_corpus.append((doc_id, content, str(text_path)))
            except Exception as e:
                logger.debug(f"Could not read exported text at {text_path}: {e}")

        # Also check manifest.json for topic and core_message
        for manifest_path in self.outputs_dir.rglob("manifest.json"):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8", errors="replace"))
                topic = data.get("topic", "")
                core = data.get("core_message", "")
                text = f"{topic} {core}".strip()
                if text:
                    self.exported_corpus.append((f"manifest_{manifest_path.parent.name}", text, str(manifest_path)))
            except Exception:
                pass

        logger.debug(f"Indexed {len(self.exported_corpus)} previously exported assets for deduplication.")

    @staticmethod
    def compute_hash(text: str) -> str:
        """Normalized SHA-256 hash of text."""
        normalized = " ".join(text.strip().lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def check_hash_duplicates(self, text: str) -> Optional[DedupeResult]:
        """Check for exact hash collision against cache or exported files."""
        candidate_hash = self.compute_hash(text)

        # Check in-memory records
        for rec in self.records.values():
            if rec.content_hash == candidate_hash:
                return DedupeResult(
                    is_duplicate=True,
                    similarity_score=1.0,
                    matched_id=rec.content_id,
                    reason=f"Exact SHA-256 match with cached job {rec.content_id}",
                )

        # Check exported corpus
        for doc_id, doc_text, file_path in self.exported_corpus:
            if self.compute_hash(doc_text) == candidate_hash:
                return DedupeResult(
                    is_duplicate=True,
                    similarity_score=1.0,
                    matched_id=doc_id,
                    matched_file=file_path,
                    reason=f"Exact SHA-256 match with exported asset: {Path(file_path).name}",
                )

        return None

    def compute_tfidf_similarity(
        self,
        candidate_text: str,
    ) -> Tuple[float, Optional[str], Optional[str]]:
        """Compute TF-IDF cosine similarity using scikit-learn against the exported corpus."""
        if not self.exported_corpus or not candidate_text.strip():
            return 0.0, None, None

        corpus_texts = [item[1] for item in self.exported_corpus]
        all_documents = [candidate_text] + corpus_texts

        try:
            vectorizer = TfidfVectorizer(
                stop_words="english",
                ngram_range=(1, 1),
                lowercase=True,
                sublinear_tf=True,
            )
            tfidf_matrix = vectorizer.fit_transform(all_documents)
            # Row 0 is candidate; Rows 1..N are corpus
            sim_scores = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()

            max_idx = int(sim_scores.argmax())
            max_sim = float(sim_scores[max_idx])

            matched_id, _, matched_path = self.exported_corpus[max_idx]
            return round(max_sim, 3), matched_id, matched_path
        except Exception as e:
            logger.warning(f"TF-IDF similarity calculation notice: {e}")
            return 0.0, None, None

    def check(self, text: str, threshold: float = 0.80) -> DedupeResult:
        """Check if candidate text duplicates any previous output via Hash or TF-IDF Cosine."""
        cleaned = text.strip()
        if not cleaned:
            return DedupeResult(is_duplicate=False, similarity_score=0.0)

        # 1. Exact hash check
        exact_res = self.check_hash_duplicates(cleaned)
        if exact_res:
            logger.warning(f"Exact duplicate detected: {exact_res.reason}")
            return exact_res

        # 2. Embedding-free TF-IDF Cosine similarity check (scikit-learn)
        max_sim, matched_id, matched_file = self.compute_tfidf_similarity(cleaned)

        if max_sim >= threshold:
            reason = (
                f"TF-IDF cosine similarity ({int(max_sim * 100)}% >= {int(threshold * 100)}%) "
                f"with previously exported asset {matched_id}"
            )
            logger.warning(f"Near-duplicate detected: {reason}")
            return DedupeResult(
                is_duplicate=True,
                similarity_score=max_sim,
                matched_id=matched_id,
                matched_file=matched_file,
                reason=reason,
            )

        return DedupeResult(
            is_duplicate=False,
            similarity_score=max_sim,
            matched_id=matched_id if max_sim > 0.3 else None,
            matched_file=matched_file if max_sim > 0.3 else None,
            reason="Unique content (passes hash and TF-IDF checks)",
        )

    def record(
        self,
        content_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register newly generated content in the dedupe registry and exported corpus."""
        sha = self.compute_hash(text)
        rec = DedupeRecord(
            content_id=content_id,
            content_hash=sha,
            timestamp=time.time(),
            snippet=text[:500],
            tokens=[],
            metadata=metadata or {},
        )
        self.records[content_id] = rec
        self.exported_corpus.append((content_id, text, str(self.cache_file)))
        self._save_cache()
        logger.info(f"Registered content record '{content_id}' into dedupe registry.")


# Backward compatibility aliasing for legacy imports
sys.modules["src.dedupe.deduplicator"] = sys.modules[__name__]
