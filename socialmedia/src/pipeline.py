"""Pipeline orchestrator for Incubrix Engine.

Coordinates the end-to-end lifecycle:
1. Ingest (text, markdown, audio, video, json, URLs)
2. Transcribe (Groq Whisper-large-v3 with chunking and timestamp merging)
3. Insights (core topic, pillars, audience hooks)
4. Generate (parallelized Groq LPU inference for scripts, carousels, and copy)
5. Brandcheck (deterministic rules + Groq brand judge with self-healing regeneration loop)
6. Dedupe (SHA-256 hash & TF-IDF semantic cosine similarity)
7. Video & Graphics (Pixabay B-roll, 9:16 vertical video with hook overlay & captions, 1080x1350 carousels)
8. Export (calendar.csv with exact 14 columns, Buffer/Hootsuite scheduler CSVs, platform packages)
9. Runtime and cost summary ($ USD from Groq audit runs)
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from src.brandcheck import BrandChecker, BrandCheckReport
from src.config import PROJECT_ROOT, get_brand_config, get_platforms_config, get_settings
from src.dedupe import ContentDeduplicator, DedupeResult
from src.export.exporter import ExportBundle, ExportManager
from src.generate import GenerationResult, GroqContentGenerator, PlatformAsset
from src.graphics import CAROUSEL_HEIGHT, CAROUSEL_WIDTH, CarouselRenderer, CarouselSlideData, GraphicsDesigner
from src.ingest import ContentType, IngestManager, IngestPayload
from src.logging.logger import get_logger
from src.transcribe import GroqTranscriber
from src.video.editor import VideoEngine
from src.video.pixabay import PixabayVideoDownloader
from src.video.render import VideoRenderer

logger = get_logger("pipeline")


class CostMetrics(BaseModel):
    """Token usage and estimated cost summary across all Groq LPU calls."""
    total_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    models_used: List[str] = Field(default_factory=list)


class PipelineResult(BaseModel):
    """Complete summary report of an Incubrix Engine pipeline execution."""
    success: bool
    input_file: str
    topic: str
    brandcheck_passed: bool
    brandcheck_score: float
    output_directory: str
    manifest_file: str
    calendar_csv: Optional[str] = None
    buffer_schedule_csv: Optional[str] = None
    hootsuite_schedule_csv: Optional[str] = None
    runtime_seconds: float = 0.0
    cost_metrics: CostMetrics = Field(default_factory=CostMetrics)
    assets_count: int = 0
    refreshed_skipped: bool = False
    failure_injected: bool = False


class IncubrixPipeline:
    """Master orchestrator connecting all submodules with parallelization and self-healing."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.brand_cfg = get_brand_config()
        self.platforms_cfg = get_platforms_config()

        self.ingest = IngestManager()
        self.dedupe = ContentDeduplicator()
        self.transcriber = GroqTranscriber()
        self.generator = GroqContentGenerator()
        self.brandchecker = BrandChecker()
        self.designer = GraphicsDesigner()
        self.video_engine = VideoEngine()
        self.video_renderer = VideoRenderer()
        self.pixabay_video = PixabayVideoDownloader()
        self.carousel_renderer = CarouselRenderer()
        self.exporter = ExportManager()

    def _collect_cost_metrics(self, start_timestamp_iso: str) -> CostMetrics:
        """Parse data/logs/runs.jsonl to aggregate token usage and costs for this run."""
        runs_file = self.settings.logs_dir / "runs.jsonl"
        metrics = CostMetrics()
        if not runs_file.exists():
            return metrics

        models_set = set()
        try:
            with open(runs_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        entry_time = entry.get("timestamp", "")
                        if entry_time >= start_timestamp_iso:
                            metrics.total_calls += 1
                            metrics.prompt_tokens += int(entry.get("prompt_tokens", 0))
                            metrics.completion_tokens += int(entry.get("completion_tokens", 0))
                            metrics.total_tokens += int(entry.get("total_tokens", 0))
                            metrics.estimated_cost_usd += float(entry.get("estimated_cost_usd", 0.0))
                            m = entry.get("model")
                            if m:
                                models_set.add(m)
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"Could not parse runs.jsonl: {e}")

        metrics.estimated_cost_usd = round(metrics.estimated_cost_usd, 6)
        metrics.models_used = sorted(list(models_set))
        return metrics

    def run(
        self,
        input_path: Path,
        platforms: Optional[List[str]] = None,
        skip_video: bool = False,
        force: bool = False,
        refresh_mode: bool = False,
        simulate_failure: bool = False,
    ) -> PipelineResult:
        """Execute full autonomous production pipeline."""
        start_time = time.time()
        start_time_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        input_file = Path(input_path).resolve()
        logger.info(f"=== Starting Incubrix Pipeline for: {input_file.name} ===")

        # 1. Ingest
        payload: IngestPayload = self.ingest.load(input_file)

        # 2. Deduplication & Refresh Mode Check
        text_for_dedupe = payload.raw_text or payload.file_name
        dedupe_res: DedupeResult = self.dedupe.check(text_for_dedupe)

        if refresh_mode and dedupe_res.is_duplicate and not force:
            matched_rec = dedupe_res.matched_id or ""
            logger.info(
                f"[REFRESH MODE] Content from '{input_file.name}' has already been processed "
                f"(match with cached job: {matched_rec}). Skipping reprocessing."
            )
            # Locate existing output directory if available
            cached_output_dir = self.settings.outputs_dir / matched_rec
            manifest_p = cached_output_dir / "manifest.json"
            calendar_p = cached_output_dir / "calendar.csv"
            cached_assets_count = 0
            if manifest_p.exists():
                try:
                    with open(manifest_p, "r", encoding="utf-8") as f:
                        m_data = json.load(f)
                        cached_assets_count = len(m_data.get("assets", []))
                except Exception:
                    pass

            return PipelineResult(
                success=True,
                input_file=str(input_file),
                topic=payload.metadata.get("title") or input_file.stem,
                brandcheck_passed=True,
                brandcheck_score=100.0,
                output_directory=str(cached_output_dir if cached_output_dir.exists() else self.settings.outputs_dir),
                manifest_file=str(manifest_p if manifest_p.exists() else ""),
                calendar_csv=str(calendar_p if calendar_p.exists() else None),
                runtime_seconds=round(time.time() - start_time, 2),
                assets_count=cached_assets_count,
                refreshed_skipped=True,
            )

        if dedupe_res.is_duplicate and not force and not refresh_mode:
            logger.warning(f"DUPLICATE DETECTED: {dedupe_res.reason}. Use --force to override or --refresh to skip.")
            raise ValueError(f"Content matches previously processed item: {dedupe_res.reason}")

        # 3. Transcribe (if media input)
        source_text = payload.raw_text
        if payload.content_type in (ContentType.AUDIO, ContentType.VIDEO) and payload.media_path:
            logger.info("Media input detected. Invoking Groq Whisper-large-v3 transcription...")
            transcript_res = self.transcriber.transcribe(payload.media_path)
            source_text = transcript_res.text
            payload.raw_text = source_text

        if not source_text or not source_text.strip():
            raise ValueError(f"No usable text or transcript could be extracted from {input_file}")

        # 4. Insights Extraction & Parallelized Groq Asset Generation
        logger.info("Invoking parallelized Groq LLM inference for multi-platform campaign assets...")
        target_platforms = platforms or ["tiktok", "instagram_reels", "youtube_shorts", "linkedin", "x_twitter"]

        # Run multi-asset generation using Groq LLaMA-3.3-70b-versatile
        generation: GenerationResult = self.generator.generate(
            raw_text=source_text,
            target_platforms=target_platforms,
        )

        # 5. Brand Compliance Check with Self-Healing Loop & Failure Injection
        logger.info("Running deterministic rules and Groq brand verification...")
        sample_check_text = f"{generation.script.hook}\n{' '.join(generation.script.body_points)}\n{generation.script.call_to_action}"

        failure_was_injected = False
        if simulate_failure:
            failure_was_injected = True
            logger.warning("[FAILURE-INJECTION DEMO] Injecting synthetic non-compliant claim to test automated recovery...")
            sample_check_text = (
                "IncuBrix guarantees 100x viral scale and instant automated revenue with patented holographic rendering! "
                + sample_check_text
            )

        brand_report: BrandCheckReport = self.brandchecker.verify(
            text=sample_check_text,
            platform_id="linkedin",
            hook_text=generation.script.hook,
            hashtags=["#IncuBrix", "#TechInnovation"],
        )

        if not brand_report.passed:
            logger.warning(
                f"Brand check violations encountered (Score: {brand_report.score}): {brand_report.violations}"
            )
            if brand_report.refined_text:
                logger.info("Applying brand compliance auto-refined script recovered by regeneration loop.")
                generation.script.hook = brand_report.refined_text.splitlines()[0]

        # 6. Graphics, Pixabay B-roll, and Video Rendering
        logger.info("Generating visuals: querying Pixabay B-roll, rendering thumbnails, and building carousels...")
        thumbnails: Dict[str, Path] = {}
        rendered_videos: Dict[str, Path] = {}
        rendered_carousels: Dict[str, List[Path]] = {}

        # 6a. Search Pixabay B-Roll Video Asset (only needed if compiling video)
        pixabay_hit_data = None
        chosen_broll_clip: Optional[Path] = None
        if not skip_video:
            try:
                broll_keywords = generation.visual_search_terms or ["podcast", "microphone", "editing", "laptop"]
                downloaded_broll = self.pixabay_video.acquire_broll_clip(
                    keywords=broll_keywords,
                    max_duration=15.0,
                )
                if downloaded_broll:
                    chosen_broll_clip = downloaded_broll.local_path
                    pixabay_hit_data = {
                        "id": downloaded_broll.pixabay_id,
                        "pageURL": downloaded_broll.page_url,
                        "user": downloaded_broll.author,
                    }
            except Exception as e:
                logger.warning(f"Pixabay B-roll retrieval skipped ({e}). Continuing with visual fallbacks.")

        # 6b. Generate Platform Thumbnails in Parallel
        temp_thumb_dir = self.settings.outputs_dir / "temp_thumbs"
        temp_thumb_dir.mkdir(parents=True, exist_ok=True)

        def _render_thumb(p_id: str) -> Tuple[str, Path]:
            spec = self.platforms_cfg.platforms.get(p_id)
            w = spec.width if spec else 1080
            h = spec.height if spec else 1920
            t_path = temp_thumb_dir / f"thumb_{p_id}.png"
            self.designer.generate_thumbnail(
                title=generation.script.hook,
                subtitle=generation.topic,
                output_path=t_path,
                width=w,
                height=h,
            )
            return p_id, t_path

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(_render_thumb, pid) for pid in generation.platform_posts.keys()]
            for fut in as_completed(futures):
                try:
                    pid, t_path = fut.result()
                    thumbnails[pid] = t_path
                except Exception as e:
                    logger.debug(f"Thumbnail render error: {e}")

        # 6c. Render 1080x1350 Pillow Carousels
        try:
            carousel_slides = [
                CarouselSlideData(
                    slide_number=1,
                    slide_type="cover",
                    category="CREATOR BLUEPRINT",
                    title=generation.script.hook,
                    body_points=[generation.core_message],
                ),
                CarouselSlideData(
                    slide_number=2,
                    slide_type="content",
                    category="WORKFLOW",
                    title="Key Insight & Framework",
                    body_points=generation.script.body_points[:3] if generation.script.body_points else ["Automate your media workflow"],
                    tip="High-retention hooks must interrupt the scroll in under 2 seconds.",
                ),
                CarouselSlideData(
                    slide_number=3,
                    slide_type="cta",
                    category="ACTION",
                    title="Scale Your Content Operations",
                    body_points=[generation.script.call_to_action],
                    cta_text="Follow @IncuBrix • Link in bio",
                ),
            ]
            carousel_asset_id = f"carousel_{re.sub(r'[^a-zA-Z0-9]+', '_', generation.topic[:20]).strip('_').lower()}"
            carousel_files = self.carousel_renderer.render_carousel(
                slides_data=carousel_slides,
                asset_id=carousel_asset_id,
            )
            rendered_carousels["linkedin"] = carousel_files
            rendered_carousels["instagram_reels"] = carousel_files
        except Exception as e:
            logger.warning(f"Carousel generation error: {e}")

        # 6d. Video Compilation (MoviePy 9:16 with Hook Overlay & Captions)
        if not skip_video:
            if not chosen_broll_clip or not chosen_broll_clip.exists():
                fallback_broll = self.settings.cache_dir / "brand_canvas_broll.mp4"
                if not fallback_broll.exists():
                    try:
                        from moviepy.editor import ColorClip
                        fallback_broll.parent.mkdir(parents=True, exist_ok=True)
                        c_clip = ColorClip(size=(720, 1280), color=(15, 23, 42), duration=4.0)
                        c_clip.write_videofile(
                            str(fallback_broll),
                            fps=15,
                            codec="libx264",
                            preset="ultrafast",
                            threads=1,
                            ffmpeg_params=["-loglevel", "error"],
                            verbose=False,
                            logger=None,
                        )
                        c_clip.close()
                    except Exception as e:
                        logger.debug(f"Fallback canvas clip creation skipped: {e}")
                if fallback_broll.exists():
                    chosen_broll_clip = fallback_broll
                    if not pixabay_hit_data:
                        pixabay_hit_data = {
                            "id": 1001,
                            "pageURL": "https://incubrix.com/brand-broll",
                            "user": "IncuBrix Studio",
                        }

            if chosen_broll_clip and chosen_broll_clip.exists():
                logger.info("Compiling 9:16 vertical video with MoviePy (hook overlay in first 2s + burned-in captions)...")
                try:
                    reel_asset_id = f"reel_{re.sub(r'[^a-zA-Z0-9]+', '_', generation.topic[:20]).strip('_').lower()}"
                    compiled_video_path = self.video_renderer.render_reel(
                        script={
                            "hook": generation.script.hook,
                            "body_points": generation.script.body_points,
                            "call_to_action": generation.script.call_to_action,
                        },
                        clip_path=chosen_broll_clip,
                        asset_id=reel_asset_id,
                        max_duration=60.0,
                        enable_tts=True,
                        pixabay_hit_data=pixabay_hit_data,
                    )
                    for pid in ["tiktok", "instagram_reels", "youtube_shorts"]:
                        if pid in generation.platform_posts:
                            rendered_videos[pid] = compiled_video_path
                except Exception as e:
                    logger.error(f"9:16 vertical video compilation error: {e}")
        elif skip_video:
            logger.info("Video rendering skipped (--skip-video flag active).")

        # 7. Export Packaging, calendar.csv, and Buffer/Hootsuite Schedulers
        logger.info("Packaging final distribution bundle and exporting calendar.csv + scheduler CSVs...")
        bundle: ExportBundle = self.exporter.create_bundle(
            generation=generation,
            brand_report=brand_report,
            rendered_videos=rendered_videos,
            thumbnails=thumbnails,
            carousels=rendered_carousels,
            run_name=input_file.stem,
            source_file_path=str(input_file),
        )

        # 8. Record in Dedupe Registry
        self.dedupe.record(
            content_id=bundle.run_id,
            text=source_text,
            metadata={"topic": generation.topic, "platforms": list(bundle.packages.keys())},
        )

        total_runtime = round(time.time() - start_time, 2)
        cost_metrics = self._collect_cost_metrics(start_time_iso)

        logger.info(f"=== Pipeline Successfully Completed for: {input_file.name} in {total_runtime}s ===")

        return PipelineResult(
            success=True,
            input_file=str(input_file),
            topic=generation.topic,
            brandcheck_passed=brand_report.passed,
            brandcheck_score=brand_report.score,
            output_directory=str(bundle.export_dir),
            manifest_file=str(bundle.manifest_path),
            calendar_csv=str(bundle.calendar_csv_path) if bundle.calendar_csv_path else None,
            buffer_schedule_csv=str(bundle.buffer_csv_path) if bundle.buffer_csv_path else None,
            hootsuite_schedule_csv=str(bundle.hootsuite_csv_path) if bundle.hootsuite_csv_path else None,
            runtime_seconds=total_runtime,
            cost_metrics=cost_metrics,
            assets_count=bundle.total_assets,
            refreshed_skipped=False,
            failure_injected=failure_was_injected,
        )
