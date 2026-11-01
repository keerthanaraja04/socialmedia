"""Pixabay Videos API integration for autonomous B-roll asset retrieval.

Searches the Pixabay Videos API (https://pixabay.com/api/videos/) using script keywords
(e.g., podcast, microphone, editing, laptop), chooses a vertical-friendly clip under 15s,
downloads ONLY the single selected clip (never bulk downloads), and logs license
provenance to content/licenses.csv with manual review flags for face/brand safety.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field
import requests

from src.config import PROJECT_ROOT, get_settings
from src.logging.logger import get_logger

logger = get_logger("video.pixabay")

# Pixabay Videos API Endpoint
PIXABAY_VIDEOS_API_URL = "https://pixabay.com/api/videos/"

# Cache configuration
CACHE_TTL_SECONDS = 86400  # 24 hours
DEFAULT_CACHE_FILE = PROJECT_ROOT / "data" / "cache" / "pixabay_video_cache.json"
DEFAULT_LICENSES_CSV = PROJECT_ROOT / "content" / "licenses.csv"
DEFAULT_BROLL_DIR = PROJECT_ROOT / "content" / "assets" / "broll"

# Safety filters: tags that indicate potential human faces or commercial logos
FACE_KEYWORDS: Set[str] = {
    "face", "faces", "portrait", "woman", "women", "man", "men",
    "person", "people", "girl", "boy", "model", "selfie", "human",
    "crowd", "eyes", "smile", "talking", "interviewee", "actor", "actress",
    "look", "looking", "headshot"
}

BRAND_KEYWORDS: Set[str] = {
    "logo", "brand", "trademark", "branding", "apple", "nike", "coca cola",
    "samsung", "iphone", "macbook", "android", "windows", "microsoft",
    "google", "meta", "intel", "dell", "hp"
}

# High-intent creator and editing B-roll keywords
DEFAULT_CREATOR_KEYWORDS: List[str] = [
    "podcast", "microphone", "editing", "laptop", "studio", "headphones",
    "audio", "sound wave", "keyboard", "desk", "computer", "screen"
]


class PixabayVideoSize(BaseModel):
    """Specification of a video resolution tier from Pixabay."""
    url: str
    width: int
    height: int
    size: int = 0
    thumbnail: Optional[str] = None


class PixabayVideoHit(BaseModel):
    """Represents a single video result from Pixabay Videos API."""
    id: int
    page_url: str = Field(alias="pageURL")
    tags: str = ""
    duration: int = 0
    videos: Dict[str, PixabayVideoSize]
    views: int = 0
    downloads: int = 0
    likes: int = 0
    comments: int = 0
    user: str = "Unknown"
    user_id: Optional[int] = None

    model_config = {
        "populate_by_name": True,
    }


class ClipCandidate(BaseModel):
    """Evaluated video clip candidate with vertical scoring and safety audit."""
    hit: PixabayVideoHit
    selected_size_key: str
    video_size: PixabayVideoSize
    is_vertical: bool
    aspect_ratio: float
    score: float
    manual_review_needed: bool
    manual_review_reason: str
    matched_face_tags: List[str] = Field(default_factory=list)
    matched_brand_tags: List[str] = Field(default_factory=list)


class DownloadedClip(BaseModel):
    """Metadata for a successfully downloaded single B-roll clip."""
    asset_id: str
    pixabay_id: int
    page_url: str
    author: str
    download_date: str
    local_path: Path
    duration: int
    width: int
    height: int
    manual_review: bool
    manual_review_reason: str
    license_file: Path


class PixabayVideoCache:
    """Manages 24-hour disk caching of Pixabay Videos API search responses."""

    def __init__(self, cache_file: Optional[Path] = None, ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
        self.cache_file = cache_file or DEFAULT_CACHE_FILE
        self.ttl_seconds = ttl_seconds
        self._ensure_cache_file()

    def _ensure_cache_file(self) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.cache_file.exists():
            self._write_raw({})

    def _read_raw(self) -> Dict[str, Any]:
        try:
            if not self.cache_file.exists():
                return {}
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error reading video cache {self.cache_file}: {e}. Resetting cache.")
            return {}

    def _write_raw(self, data: Dict[str, Any]) -> None:
        try:
            temp_path = self.cache_file.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_path.replace(self.cache_file)
        except Exception as e:
            logger.warning(f"Failed to persist video cache: {e}")

    def _make_key(self, query: str, **kwargs: Any) -> str:
        norm_query = query.strip().lower()
        key_dict = {"q": norm_query, **{k: str(v).lower() for k, v in sorted(kwargs.items())}}
        serialized = json.dumps(key_dict, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, query: str, **kwargs: Any) -> Optional[List[Dict[str, Any]]]:
        """Retrieve cached search hits if within 24-hour TTL."""
        cache_data = self._read_raw()
        key = self._make_key(query, **kwargs)
        entry = cache_data.get(key)
        if not entry:
            return None

        expires_at = entry.get("expires_at", 0)
        now = time.time()
        if now > expires_at:
            logger.debug(f"Cache expired for query '{query}' (expired at {expires_at}, now {now}).")
            return None

        logger.info(f"Video cache HIT for query '{query}' (expires in {int(expires_at - now)}s)")
        return entry.get("hits", [])

    def set(self, query: str, hits: List[Dict[str, Any]], **kwargs: Any) -> None:
        """Cache search hits with a 24-hour expiration."""
        cache_data = self._read_raw()
        key = self._make_key(query, **kwargs)
        now = time.time()
        cache_data[key] = {
            "query": query.strip().lower(),
            "timestamp": now,
            "expires_at": now + self.ttl_seconds,
            "hits_count": len(hits),
            "hits": hits,
        }
        self._write_raw(cache_data)
        logger.debug(f"Cached {len(hits)} hits for query '{query}' (TTL: {self.ttl_seconds}s)")


class LicenseRegistry:
    """Appends downloaded clip provenance and manual review flags to licenses.csv."""

    HEADERS = [
        "pixabay_id",
        "page_url",
        "author",
        "download_date",
        "asset_id",
        "manual_review",
        "manual_review_reason",
    ]

    def __init__(self, csv_path: Optional[Path] = None) -> None:
        self.csv_path = csv_path or DEFAULT_LICENSES_CSV
        self._ensure_csv()

    def _ensure_csv(self) -> None:
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.csv_path.exists() or self.csv_path.stat().st_size == 0:
            with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(self.HEADERS)
            logger.info(f"Initialized licenses registry at: {self.csv_path}")

    def is_recorded(self, pixabay_id: int) -> bool:
        """Check whether a Pixabay asset ID has already been recorded."""
        if not self.csv_path.exists():
            return False
        try:
            with open(self.csv_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    val = row.get("pixabay_id") or row.get("id")
                    if val and str(val).strip() == str(pixabay_id).strip():
                        return True
        except Exception as e:
            logger.warning(f"Error checking existing licenses in {self.csv_path}: {e}")
        return False

    def append_license(
        self,
        pixabay_id: int,
        page_url: str,
        author: str,
        download_date: str,
        asset_id: str,
        manual_review: bool,
        manual_review_reason: str,
    ) -> None:
        """Append a license entry with audit and manual review status."""
        self._ensure_csv()
        row = [
            str(pixabay_id),
            page_url,
            author,
            download_date,
            asset_id,
            "TRUE" if manual_review else "FALSE",
            manual_review_reason,
        ]
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(row)
        logger.info(
            f"Logged license for asset {asset_id} (Pixabay ID: {pixabay_id}, Manual Review: {manual_review}) in {self.csv_path.name}"
        )


class PixabayVideoDownloader:
    """Autonomous Pixabay video search, scoring, single-clip download, and license auditor."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_file: Optional[Path] = None,
        licenses_csv: Optional[Path] = None,
        min_request_interval_seconds: float = 0.65,
    ) -> None:
        self.settings = get_settings()
        self.api_key = api_key or self.settings.pixabay_api_key
        self.cache = PixabayVideoCache(cache_file=cache_file)
        self.registry = LicenseRegistry(csv_path=licenses_csv)
        self.min_request_interval = min_request_interval_seconds
        self._last_request_time: float = 0.0

    def _respect_rate_limit(self) -> None:
        """Enforce spacing between outbound API calls (Pixabay limit: 100 req/min)."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.min_request_interval:
            sleep_time = self.min_request_interval - elapsed
            logger.debug(f"Rate limit spacing: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def search_videos(
        self,
        query: str,
        per_page: int = 20,
        max_retries: int = 3,
    ) -> List[PixabayVideoHit]:
        """Search the Pixabay Videos API, respecting 24h cache and rate limits."""
        if not self.api_key or self.api_key.startswith("your_"):
            logger.warning("PIXABAY_API_KEY is not set or using placeholder; skipping video search.")
            return []

        clean_query = query.strip()
        if not clean_query:
            return []

        # 1. Check 24-hour cache
        cached_hits = self.cache.get(clean_query, per_page=per_page)
        if cached_hits is not None:
            return self._parse_hits(cached_hits)

        # 2. Query Pixabay Videos API
        params = {
            "key": self.api_key,
            "q": clean_query,
            "video_type": "all",
            "per_page": per_page,
            "safesearch": "true",
        }

        hits_data: List[Dict[str, Any]] = []
        for attempt in range(max_retries):
            try:
                self._respect_rate_limit()
                logger.info(f"Querying Pixabay Videos API for: '{clean_query}' (attempt {attempt + 1}/{max_retries})")
                resp = requests.get(PIXABAY_VIDEOS_API_URL, params=params, timeout=12)

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                    logger.warning(f"Pixabay rate limit hit (HTTP 429). Waiting {retry_after}s before retry...")
                    time.sleep(retry_after)
                    continue

                resp.raise_for_status()
                data = resp.json()
                hits_data = data.get("hits", [])
                break

            except requests.exceptions.RequestException as e:
                logger.warning(f"Pixabay video request failed on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"Pixabay video search exhausted all retries for '{clean_query}'.")
                    return []
                time.sleep(1.0 * (attempt + 1))

        # 3. Store raw hits in 24h cache
        self.cache.set(clean_query, hits_data, per_page=per_page)

        return self._parse_hits(hits_data)

    def _parse_hits(self, raw_hits: List[Dict[str, Any]]) -> List[PixabayVideoHit]:
        parsed: List[PixabayVideoHit] = []
        for h in raw_hits:
            try:
                videos_dict: Dict[str, PixabayVideoSize] = {}
                raw_videos = h.get("videos", {})
                for size_name, size_data in raw_videos.items():
                    if isinstance(size_data, dict) and "url" in size_data:
                        videos_dict[size_name] = PixabayVideoSize(
                            url=size_data["url"],
                            width=int(size_data.get("width", 0)),
                            height=int(size_data.get("height", 0)),
                            size=int(size_data.get("size", 0)),
                            thumbnail=size_data.get("thumbnail"),
                        )

                parsed.append(
                    PixabayVideoHit(
                        id=int(h["id"]),
                        pageURL=h.get("pageURL", f"https://pixabay.com/videos/id-{h['id']}/"),
                        tags=h.get("tags", ""),
                        duration=int(h.get("duration", 0)),
                        videos=videos_dict,
                        views=int(h.get("views", 0)),
                        downloads=int(h.get("downloads", 0)),
                        likes=int(h.get("likes", 0)),
                        comments=int(h.get("comments", 0)),
                        user=h.get("user", "Unknown"),
                        user_id=h.get("user_id"),
                    )
                )
            except Exception as e:
                logger.debug(f"Skipping malformed Pixabay video hit: {e}")
        return parsed

    # --------------------------------------------------------------------------
    # Scoring & Selection: Vertical-friendly, duration < 15s, face & brand safety
    # --------------------------------------------------------------------------
    def evaluate_candidate(
        self,
        hit: PixabayVideoHit,
        max_duration: float = 15.0,
    ) -> Optional[ClipCandidate]:
        """Evaluate and score a clip candidate. Returns None if duration exceeds limit."""
        # Duration constraint: must be strictly <= max_duration (under 15s) and > 0
        if hit.duration <= 0 or hit.duration > max_duration:
            return None

        # Choose best video stream size (prefer large or medium for 1080p vertical shorts)
        chosen_key = ""
        chosen_size: Optional[PixabayVideoSize] = None
        for key in ["large", "medium", "small", "tiny"]:
            if key in hit.videos and hit.videos[key].url:
                chosen_key = key
                chosen_size = hit.videos[key]
                break

        if not chosen_size or not chosen_size.url:
            return None

        width = chosen_size.width or 1
        height = chosen_size.height or 1
        aspect_ratio = height / width
        is_vertical = height > width

        # Base score starts at 50
        score = 50.0

        # 1. Orientation Scoring (favor vertical 9:16 or high-resolution crop friendly)
        if is_vertical:
            # Native vertical video (e.g., 9:16 portrait) gets highest boost
            score += 50.0
        elif height == width:
            # Square (1:1) is easily adaptable
            score += 25.0
        else:
            # Horizontal (16:9) - verify sufficient height for center crop to 9:16
            if height >= 1080:
                score += 15.0  # Full HD/4K crops nicely
            elif height >= 720:
                score += 5.0
            else:
                score -= 15.0  # Low vertical resolution

        # 2. Duration Sweet-Spot: 4s to 12s is optimal for vertical short-form B-roll cutaways
        if 4 <= hit.duration <= 12:
            score += 15.0
        elif hit.duration <= 15:
            score += 5.0

        # 3. Face & Brand Safety Evaluation via tags
        tag_tokens = set(re.findall(r"\w+", hit.tags.lower()))
        matched_face = sorted(list(tag_tokens.intersection(FACE_KEYWORDS)))
        matched_brand = sorted(list(tag_tokens.intersection(BRAND_KEYWORDS)))

        manual_review_needed = False
        reasons: List[str] = []

        if matched_face:
            manual_review_needed = True
            reasons.append(f"Potential recognizable faces/people in tags: {matched_face}")
            score -= 35.0  # Heavily penalize face-containing clips
        else:
            score += 25.0  # Bonus for face-free clip

        if matched_brand:
            manual_review_needed = True
            reasons.append(f"Potential commercial brand logo in tags: {matched_brand}")
            score -= 40.0  # Heavily penalize brand logos
        else:
            score += 15.0  # Bonus for logo-free clip

        # Bonus for creator/tech B-roll tags
        matched_creator = tag_tokens.intersection(set(DEFAULT_CREATOR_KEYWORDS))
        score += min(len(matched_creator) * 5.0, 20.0)

        # Engagement / quality metrics normalized
        engagement_bonus = min((hit.downloads / 500.0) + (hit.likes / 50.0), 10.0)
        score += engagement_bonus

        review_reason = "; ".join(reasons) if reasons else "Clean b-roll asset (no recognizable faces or brand logos detected)"

        return ClipCandidate(
            hit=hit,
            selected_size_key=chosen_key,
            video_size=chosen_size,
            is_vertical=is_vertical,
            aspect_ratio=round(aspect_ratio, 3),
            score=round(score, 2),
            manual_review_needed=manual_review_needed,
            manual_review_reason=review_reason,
            matched_face_tags=matched_face,
            matched_brand_tags=matched_brand,
        )

    def select_best_clip(
        self,
        hits: List[PixabayVideoHit],
        max_duration: float = 15.0,
    ) -> Optional[ClipCandidate]:
        """Rank and choose the single highest-scoring vertical-friendly clip under 15s."""
        candidates: List[ClipCandidate] = []
        for hit in hits:
            candidate = self.evaluate_candidate(hit, max_duration=max_duration)
            if candidate:
                candidates.append(candidate)

        if not candidates:
            return None

        # Sort strictly descending by score
        candidates.sort(key=lambda c: c.score, reverse=True)
        winner = candidates[0]
        logger.info(
            f"Selected best clip ID {winner.hit.id} (score={winner.score}, duration={winner.hit.duration}s, vertical={winner.is_vertical}, manual_review={winner.manual_review_needed})"
        )
        return winner

    # --------------------------------------------------------------------------
    # Single-Clip Download (NEVER bulk download)
    # --------------------------------------------------------------------------
    def download_selected_clip(
        self,
        candidate: ClipCandidate,
        destination_dir: Optional[Path] = None,
        custom_asset_id: Optional[str] = None,
    ) -> DownloadedClip:
        """Download ONLY the single selected video clip and log its license.
        
        Strictly enforces single-asset download to prevent bulk scraping.
        """
        dest_dir = destination_dir or DEFAULT_BROLL_DIR
        dest_dir.mkdir(parents=True, exist_ok=True)

        hit = candidate.hit
        size = candidate.video_size
        video_url = size.url

        # Generate unique asset identifier and filename
        clean_tag = re.sub(r"[^a-zA-Z0-9]+", "_", hit.tags.split(",")[0] if hit.tags else "broll").strip("_").lower()
        asset_id = custom_asset_id or f"broll_pixabay_{hit.id}_{clean_tag}"
        target_filename = f"{asset_id}.mp4"
        local_file = dest_dir / target_filename

        logger.info(f"Downloading single selected video clip: {local_file.name} from {video_url} ({size.width}x{size.height}, {hit.duration}s)")

        # Stream download the single file in 64KB chunks
        self._respect_rate_limit()
        resp = requests.get(video_url, stream=True, timeout=30)
        resp.raise_for_status()

        bytes_written = 0
        with open(local_file, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    bytes_written += len(chunk)

        if bytes_written == 0 or not local_file.exists():
            raise IOError(f"Downloaded video file {local_file} is empty or failed to write.")

        logger.info(f"Successfully downloaded {local_file.name} ({bytes_written / 1024:.1f} KB)")

        # Record license in content/licenses.csv
        download_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.registry.append_license(
            pixabay_id=hit.id,
            page_url=hit.page_url,
            author=hit.user,
            download_date=download_date,
            asset_id=asset_id,
            manual_review=candidate.manual_review_needed,
            manual_review_reason=candidate.manual_review_reason,
        )

        return DownloadedClip(
            asset_id=asset_id,
            pixabay_id=hit.id,
            page_url=hit.page_url,
            author=hit.user,
            download_date=download_date,
            local_path=local_file,
            duration=hit.duration,
            width=size.width,
            height=size.height,
            manual_review=candidate.manual_review_needed,
            manual_review_reason=candidate.manual_review_reason,
            license_file=self.registry.csv_path,
        )

    # --------------------------------------------------------------------------
    # Master Workflow: Search keywords, choose best clip, download single file
    # --------------------------------------------------------------------------
    def acquire_broll_clip(
        self,
        keywords: List[str] | str,
        destination_dir: Optional[Path] = None,
        max_duration: float = 15.0,
        asset_id: Optional[str] = None,
    ) -> Optional[DownloadedClip]:
        """Execute end-to-end B-roll retrieval:
        1. Formulate search query from keywords.
        2. Query API / check 24h cache.
        3. Rank vertical-friendly clips under 15s with safety checks.
        4. Download ONLY the winning clip.
        5. Append license and manual review flag to content/licenses.csv.
        """
        if isinstance(keywords, str):
            kw_list = [k.strip() for k in re.split(r"[,;|\s]+", keywords) if k.strip()]
        else:
            kw_list = [k.strip() for k in keywords if k.strip()]

        if not kw_list:
            kw_list = DEFAULT_CREATOR_KEYWORDS[:4]

        # Try individual queries or composite query
        hits: List[PixabayVideoHit] = []
        # First attempt: search primary keyword
        primary_query = kw_list[0]
        hits = self.search_videos(primary_query)

        # If no hits, fallback to subsequent keywords
        if not hits and len(kw_list) > 1:
            for kw in kw_list[1:]:
                logger.info(f"No hits for '{primary_query}'; trying fallback keyword '{kw}'")
                hits = self.search_videos(kw)
                if hits:
                    break

        if not hits:
            logger.warning(f"No Pixabay video hits found for keywords: {kw_list}")
            return None

        # Select single best clip under 15s
        winner = self.select_best_clip(hits, max_duration=max_duration)
        if not winner:
            logger.warning(f"No suitable vertical-friendly clips under {max_duration}s found among {len(hits)} hits.")
            return None

        # Download ONLY the selected single clip
        return self.download_selected_clip(
            candidate=winner,
            destination_dir=destination_dir,
            custom_asset_id=asset_id,
        )


def extract_keywords_from_script(script_text: str, max_keywords: int = 4) -> List[str]:
    """Extract relevant video B-roll search keywords from a script or text draft."""
    text_lower = script_text.lower()
    found: List[str] = []

    for kw in DEFAULT_CREATOR_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
            found.append(kw)
            if len(found) >= max_keywords:
                break

    # If few or none found, supply default tech/creator keywords
    if len(found) < 2:
        for fallback in ["podcast", "microphone", "editing", "laptop"]:
            if fallback not in found:
                found.append(fallback)
            if len(found) >= max_keywords:
                break

    return found
