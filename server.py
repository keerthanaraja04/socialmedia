#!/usr/bin/env python3
"""IncuBrix Engine Local Web Server & Interactive API.

Serves the IncuBrix Web Command Center, Asset Studio, Preference Test Form,
and REST endpoints for pipeline triggers and audit inspection.

Usage:
    python server.py
    python server.py --port 8000
"""

from __future__ import annotations

import argparse
import csv
import http.server
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent

# Global running task state
_pipeline_lock = threading.Lock()
_pipeline_status = {
    "running": False,
    "last_run": None,
    "current_task": None,
    "log_output": [],
    "exit_code": 0,
}
_current_proc: Optional[subprocess.Popen] = None


def _run_pipeline_background(cmd: List[str], task_name: str) -> None:
    """Execute a CLI pipeline command in a separate background thread with live log streaming."""
    global _pipeline_status, _current_proc
    with _pipeline_lock:
        _pipeline_status["running"] = True
        _pipeline_status["current_task"] = task_name
        _pipeline_status["log_output"] = [f"[{time.strftime('%H:%M:%S')}] Started: {' '.join(cmd)}"]
        _pipeline_status["exit_code"] = None

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        with _pipeline_lock:
            _current_proc = proc

        for line in iter(proc.stdout.readline, ""):
            if line:
                clean_line = line.strip()
                with _pipeline_lock:
                    _pipeline_status["log_output"].append(clean_line)
                    # Keep last 500 lines
                    if len(_pipeline_status["log_output"]) > 500:
                        _pipeline_status["log_output"].pop(0)

        proc.stdout.close()
        ret = proc.wait()

        with _pipeline_lock:
            _pipeline_status["running"] = False
            _pipeline_status["exit_code"] = ret
            _pipeline_status["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
            status_msg = "SUCCESS" if ret == 0 else f"FAILED (code {ret})"
            _pipeline_status["log_output"].append(f"[{time.strftime('%H:%M:%S')}] Execution finished: {status_msg}")
            _current_proc = None
        clear_api_cache()

    except Exception as e:
        with _pipeline_lock:
            _pipeline_status["running"] = False
            _pipeline_status["exit_code"] = -1
            _pipeline_status["log_output"].append(f"[{time.strftime('%H:%M:%S')}] Error: {e}")
            _current_proc = None
        clear_api_cache()


_api_cache: Dict[str, Dict[str, Any]] = {}


def get_cached_api(key: str, ttl_sec: float, func):
    """Retrieve API response from memory cache or compute and store."""
    now = time.time()
    cached = _api_cache.get(key)
    if cached and (now - cached["ts"] < ttl_sec):
        return cached["data"]
    data = func()
    _api_cache[key] = {"ts": now, "data": data}
    return data


def clear_api_cache():
    """Clear cached API payloads."""
    _api_cache.clear()


def find_latest_calendar_csv_fast() -> Optional[Path]:
    """Fast shallow check for the latest calendar.csv without slow recursive disk globbing."""
    bundle_cal = PROJECT_ROOT / "data" / "outputs" / "final_submission_bundle" / "calendar.csv"
    if bundle_cal.exists():
        return bundle_cal
    outputs_dir = PROJECT_ROOT / "data" / "outputs"
    if outputs_dir.exists():
        try:
            subdirs = sorted(
                [d for d in outputs_dir.iterdir() if d.is_dir() and d.name != "temp_thumbs"],
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            for d in subdirs:
                c = d / "calendar.csv"
                if c.exists():
                    return c
        except Exception:
            pass
    return None


class IncuBrixRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP handler serving IncuBrix studio assets, reports, and REST APIs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def address_string(self) -> str:
        """Prevent Windows reverse DNS lookup timeout on localhost (saves 5-10s per request)."""
        return str(self.client_address[0])

    def log_message(self, format: str, *args: Any) -> None:
        """Lightweight non-blocking server logger."""
        sys.stderr.write(f"[{time.strftime('%H:%M:%S')}] {self.client_address[0]} {format % args}\n")

    def end_headers(self):
        # Enable CORS and disable aggressive caching for local dashboard updates
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
        self.send_header("Accept-Ranges", "bytes")
        if self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Root redirect to index.html
        if path == "/":
            self.path = "/index.html"
            return super().do_GET()

        # URL aliases for ease of access
        if path.startswith("/videos/"):
            path = f"/data/outputs/final_submission_bundle/videos/{Path(path).name}"
            self.path = path

        if path.startswith("/carousels/"):
            sub_name = path.replace("/carousels/", "")
            p1 = PROJECT_ROOT / "content" / "assets" / sub_name
            p2 = PROJECT_ROOT / "data" / "outputs" / "final_submission_bundle" / "carousels" / sub_name
            if p1.exists():
                self.path = f"/content/assets/{sub_name}"
            elif p2.exists():
                self.path = f"/data/outputs/final_submission_bundle/carousels/{sub_name}"

        # REST API Endpoints
        if path == "/api/status":
            self._handle_api_status()
            return

        if path == "/api/carousels":
            self._handle_api_carousels()
            return

        if path == "/api/videos":
            self._handle_api_videos()
            return

        if path == "/api/assets":
            self._handle_api_assets()
            return

        if path == "/api/calendar":
            self._handle_api_calendar()
            return

        if path == "/api/audit":
            self._handle_api_audit()
            return

        if path == "/api/preference":
            self._handle_api_preference()
            return

        # HTTP 206 Partial Content Range Support for smooth MP4 video playback
        if path.endswith(".mp4"):
            file_path = (PROJECT_ROOT / path.lstrip("/")).resolve()
            if not file_path.exists():
                alt_path = (PROJECT_ROOT / "data" / "outputs" / "final_submission_bundle" / "videos" / Path(path).name).resolve()
                if alt_path.exists():
                    file_path = alt_path

            if file_path.exists() and file_path.is_file():
                file_size = file_path.stat().st_size
                range_header = self.headers.get("Range")
                if range_header:
                    match = re.match(r"bytes=(\d+)-(\d*)", range_header)
                    if match:
                        start = int(match.group(1))
                        end = int(match.group(2)) if match.group(2) else file_size - 1
                        end = min(end, file_size - 1)
                        length = end - start + 1

                        self.send_response(206)
                        self.send_header("Content-Type", "video/mp4")
                        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                        self.send_header("Content-Length", str(length))
                        self.send_header("Accept-Ranges", "bytes")
                        self.end_headers()

                        with open(file_path, "rb") as f:
                            f.seek(start)
                            self.wfile.write(f.read(length))
                        return

        # Fallback to standard static file server
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/run":
            self._handle_api_run()
            return

        if path == "/api/cancel":
            self._handle_api_cancel()
            return

        self.send_error(404, "Endpoint Not Found")

    def _send_json_response(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_api_status(self) -> None:
        with _pipeline_lock:
            status_copy = dict(_pipeline_status)

        # Add system summary
        rep_json = PROJECT_ROOT / "reports" / "audit_report_30.json"
        audit_summary = {}
        if rep_json.exists():
            try:
                with open(rep_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    audit_summary = {
                        "total_assets": data.get("total_assets", 0),
                        "total_videos": data.get("total_videos", 0),
                        "total_carousels": data.get("total_carousels", 0),
                        "platforms": data.get("platforms", []),
                        "pass_rate": data.get("checklist_pass_rate_pct", 0.0),
                        "all_passed": data.get("all_checklist_passed", False),
                        "timestamp": data.get("timestamp"),
                    }
            except Exception:
                pass

        pref_json = PROJECT_ROOT / "reports" / "preference_test_summary.json"
        pref_summary = {}
        if pref_json.exists():
            try:
                with open(pref_json, "r", encoding="utf-8") as f:
                    pref_data = json.load(f)
                    pref_summary = {
                        "unique_respondents": pref_data.get("unique_respondents", 0),
                        "overall_a_pct": pref_data.get("overall_a_pct", 0.0),
                        "overall_b_pct": pref_data.get("overall_b_pct", 0.0),
                        "sample_met": pref_data.get("sample_adequacy_met", False),
                    }
            except Exception:
                pass

        resp = {
            "status": "ready",
            "pipeline": status_copy,
            "audit_summary": audit_summary,
            "preference_summary": pref_summary,
        }
        self._send_json_response(resp)

    def _handle_api_calendar(self) -> None:
        """Find the latest calendar.csv and return parsed row dictionaries."""
        def _fetch():
            cal_path = find_latest_calendar_csv_fast()
            if not cal_path or not cal_path.exists():
                return {"entries": [], "file": None}
            entries = []
            try:
                with open(cal_path, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        entries.append(dict(r))
            except Exception as e:
                return {"error": str(e), "entries": []}
            return {"entries": entries, "file": str(cal_path.relative_to(PROJECT_ROOT))}

        self._send_json_response(get_cached_api("calendar", 5.0, _fetch))

    def _handle_api_audit(self) -> None:
        def _fetch():
            rep_json = PROJECT_ROOT / "reports" / "audit_report_30.json"
            if not rep_json.exists():
                return {"error": "audit_report_30.json not found"}
            try:
                with open(rep_json, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                return {"error": str(e)}

        self._send_json_response(get_cached_api("audit", 5.0, _fetch))

    def _handle_api_preference(self) -> None:
        def _fetch():
            pref_json = PROJECT_ROOT / "reports" / "preference_test_summary.json"
            if not pref_json.exists():
                return {"error": "preference_test_summary.json not found"}
            try:
                with open(pref_json, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                return {"error": str(e)}

        self._send_json_response(get_cached_api("preference", 5.0, _fetch))

    def _handle_api_carousels(self) -> None:
        """Scan content/assets for all carousel_* directories and list their slides + post copy."""
        def _fetch():
            assets_dir = PROJECT_ROOT / "content" / "assets"
            carousels = []
            if assets_dir.exists():
                for d in sorted(assets_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                    if d.is_dir() and d.name.startswith("carousel_"):
                        slides = [f"/content/assets/{d.name}/{f.name}" for f in sorted(d.iterdir()) if f.name.endswith(".png")]
                        if slides:
                            name_pretty = d.name.replace("carousel_", "").replace("_", " ").title()
                            spec_file = d / "spec.json"
                            spec_data = {}
                            post_caption = ""
                            hook_title = name_pretty
                            if spec_file.exists():
                                try:
                                    with open(spec_file, "r", encoding="utf-8") as sf:
                                        spec_data = json.load(sf)
                                        s_list = spec_data.get("slides", [])
                                        if s_list:
                                            hook_title = s_list[0].get("title") or name_pretty
                                            core_msg = s_list[0].get("body_points", [""])[0] if s_list[0].get("body_points") else ""
                                            bullets = s_list[1].get("body_points", []) if len(s_list) > 1 else []
                                            cta = s_list[2].get("cta_text", "Follow @IncuBrix • Link in bio") if len(s_list) > 2 else "Follow @IncuBrix • Link in bio"
                                            b_text = "\n".join([f"• {b}" for b in bullets])
                                            post_caption = f"{hook_title}\n\n{core_msg}\n\nKey Takeaways:\n{b_text}\n\n{cta}\n#IncuBrix #ContentRepurposing #CreatorEconomy #WorkflowAutomation"
                                except Exception:
                                    pass

                            carousels.append({
                                "id": d.name,
                                "title": hook_title if hook_title != name_pretty else name_pretty,
                                "folder_name": d.name,
                                "slides_count": len(slides),
                                "slides": slides,
                                "spec": spec_data,
                                "post_caption": post_caption,
                                "mtime": d.stat().st_mtime,
                            })
            return {"carousels": carousels, "total": len(carousels)}

        self._send_json_response(get_cached_api("carousels", 5.0, _fetch))

    def _handle_api_videos(self) -> None:
        """Scan content/assets and data/outputs for all rendered .mp4 video reels + post copy."""
        def _fetch():
            cal_path = find_latest_calendar_csv_fast()
            video_captions = {}
            if cal_path and cal_path.exists():
                try:
                    with open(cal_path, "r", newline="", encoding="utf-8") as cf:
                        reader = csv.DictReader(cf)
                        for r in reader:
                            if "video" in r.get("format", "").lower():
                                platform = r.get("platform", "")
                                video_captions[platform] = {
                                    "hook": r.get("hook", ""),
                                    "caption": r.get("caption", ""),
                                    "hashtags": r.get("hashtags", ""),
                                    "cta": r.get("CTA", ""),
                                }
                except Exception:
                    pass

            fresh_videos = []
            master_videos = []

            # 1. content/assets/reel_*/*.mp4
            assets_dir = PROJECT_ROOT / "content" / "assets"
            if assets_dir.exists():
                for d in sorted(assets_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                    if d.is_dir() and d.name.startswith("reel_"):
                        for f in sorted(d.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                            if f.suffix == ".mp4" and "TEMP" not in f.name and not f.name.startswith("."):
                                size_mb = round(f.stat().st_size / (1024 * 1024), 2)
                                title = f.stem.replace("reel_", "").replace("_", " ").title()
                                cap_info = video_captions.get("tiktok") or video_captions.get("instagram_reels") or {}
                                fresh_videos.append({
                                    "id": f.stem,
                                    "title": f"Reel: {title} ({size_mb} MB)",
                                    "url": f"/content/assets/{d.name}/{f.name}",
                                    "size_mb": size_mb,
                                    "mtime": f.stat().st_mtime,
                                    "group": "✨ Freshly Rendered Pipeline Reels",
                                    "hook": cap_info.get("hook", title),
                                    "caption": cap_info.get("caption", f"Stop the scroll with high-retention vertical video.\n\nLearn the full workflow: https://incubrix.com"),
                                    "hashtags": cap_info.get("hashtags", "#IncuBrix #VideoMarketing #CreatorEconomy"),
                                    "cta": cap_info.get("cta", "Follow @IncuBrix for weekly breakdowns"),
                                })

            # 2. data/outputs/final_submission_bundle/videos/*.mp4
            master_dir = PROJECT_ROOT / "data" / "outputs" / "final_submission_bundle" / "videos"
            if master_dir.exists():
                for f in sorted(master_dir.iterdir(), key=lambda p: p.name):
                    if f.suffix == ".mp4" and "TEMP" not in f.name and not f.name.startswith("."):
                        size_mb = round(f.stat().st_size / (1024 * 1024), 2)
                        title = f.stem.replace("_", " ").title()
                        master_videos.append({
                            "id": f.stem,
                            "title": f"Reel: {title} ({size_mb} MB)",
                            "url": f"/data/outputs/final_submission_bundle/videos/{f.name}",
                            "size_mb": size_mb,
                            "mtime": f.stat().st_mtime,
                            "group": "🎬 10 Master Submission Bundle Reels",
                        })

            return {
                "fresh_reels": fresh_videos,
                "master_reels": master_videos,
                "total": len(fresh_videos) + len(master_videos),
            }

        self._send_json_response(get_cached_api("videos", 5.0, _fetch))

    def _handle_api_assets(self) -> None:
        """Return assets from the latest calendar.csv or audit_report_30.json."""
        def _fetch():
            cal_path = find_latest_calendar_csv_fast()
            assets = []
            if cal_path and cal_path.exists():
                try:
                    with open(cal_path, "r", newline="", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for r in reader:
                            assets.append({
                                "asset_id": r.get("id", ""),
                                "platform": r.get("platform", ""),
                                "format": r.get("format", ""),
                                "pillar": r.get("pillar", ""),
                                "hook": r.get("hook", ""),
                                "caption": r.get("caption", ""),
                                "hashtags": r.get("hashtags", ""),
                                "cta": r.get("CTA", ""),
                                "tracking_link": r.get("tracking_link", ""),
                                "file_path": r.get("file_path", ""),
                                "scheduled_datetime": r.get("scheduled_datetime", ""),
                                "target_metric": r.get("target_metric", ""),
                                "status": r.get("status", "scheduled"),
                            })
                except Exception:
                    pass

            if not assets:
                rep_json = PROJECT_ROOT / "reports" / "audit_report_30.json"
                if rep_json.exists():
                    try:
                        with open(rep_json, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            assets = data.get("assets", [])
                    except Exception:
                        pass
            return {"assets": assets, "total": len(assets)}

        self._send_json_response(get_cached_api("assets", 5.0, _fetch))

    def _handle_api_run(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            params = json.loads(body)
        except Exception:
            params = {}

        mode = params.get("mode", "batch_fast")

        with _pipeline_lock:
            if _pipeline_status["running"]:
                self._send_json_response({"error": "A pipeline task is already actively running."}, status=409)
                return

        python_bin = sys.executable or "python"

        if mode == "batch_full":
            cmd = [python_bin, "-u", "scripts/build_30.py"]
            task_name = "Full Batch Engine (MoviePy Video + Carousels + Audit)"
        elif mode == "batch_fast":
            cmd = [python_bin, "-u", "scripts/build_30.py", "--skip-video"]
            task_name = "Fast Batch Engine (Carousels + Copy + Audit)"
        elif mode == "single_input":
            raw_text = params.get("raw_text", "").strip()
            if raw_text:
                custom_file = PROJECT_ROOT / "content" / "sources" / "custom_input.md"
                custom_file.parent.mkdir(parents=True, exist_ok=True)
                custom_file.write_text(raw_text, encoding="utf-8")
                src = str(custom_file)
            else:
                src = params.get("input_file", "content/sources/input_1_autonomous_pipelines_blog.md")
            
            render_video = params.get("render_video", False)
            video_flag = [] if render_video else ["--skip-video"]
            cmd = [python_bin, "-u", "-m", "src.main", "--input", src, *video_flag, "--force"]
            task_name = f"Single Input Pipeline: {Path(src).name}"
        elif mode == "self_healing":
            cmd = [python_bin, "-u", "-m", "src.main", "--input", "data/inputs/sample_input.txt", "--simulate-failure", "--skip-video", "--force"]
            task_name = "Self-Healing Automated Brand Recovery Demo"
        else:
            self._send_json_response({"error": f"Invalid mode: {mode}"}, status=400)
            return

        thread = threading.Thread(target=_run_pipeline_background, args=(cmd, task_name), daemon=True)
        thread.start()

        self._send_json_response({
            "status": "started",
            "task_name": task_name,
            "cmd": cmd,
        })

    def _handle_api_cancel(self) -> None:
        """Terminate the currently active pipeline subprocess and update status."""
        global _current_proc, _pipeline_status
        with _pipeline_lock:
            if not _pipeline_status["running"] or not _current_proc:
                self._send_json_response({"status": "idle", "message": "No pipeline task is currently running."})
                return

            proc = _current_proc
            _pipeline_status["running"] = False
            _pipeline_status["exit_code"] = -9
            _pipeline_status["log_output"].append(f"[{time.strftime('%H:%M:%S')}] 🛑 Task CANCELLED by user request.")
            _current_proc = None

        if proc:
            try:
                proc.terminate()
                proc.kill()
            except Exception:
                pass

        self._send_json_response({"status": "cancelled", "message": "Pipeline generation task successfully aborted."})


def main() -> None:
    parser = argparse.ArgumentParser(description="IncuBrix Web Command Center Server")
    parser.add_argument("--port", "-p", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--host", default="0.0.0.0", help="Host address (default: 0.0.0.0)")
    args = parser.parse_args()

    ports_to_try = [args.port]
    if args.port == 8000:
        ports_to_try.extend([8080, 8081, 8001, 8501, 5000])

    httpd = None
    active_port = args.port
    for p in ports_to_try:
        try:
            server_address = (args.host, p)
            http.server.ThreadingHTTPServer.allow_reuse_address = False
            httpd = http.server.ThreadingHTTPServer(server_address, IncuBrixRequestHandler)
            active_port = p
            break
        except (PermissionError, OSError) as e:
            if p == ports_to_try[-1]:
                raise e
            continue

    url = f"http://localhost:{active_port}"
    print("\n" + "=" * 70, flush=True)
    print("      INCUBRIX AUTONOMOUS ENGINE: WEB COMMAND CENTER RUNNING      ", flush=True)
    print("=" * 70, flush=True)
    print(f" URL:            {url}", flush=True)
    print(f" Preference UI:  {url}/tools/preference_test.html", flush=True)
    print(f" REST API:       {url}/api/status", flush=True)
    print(" Press Ctrl+C in terminal to stop.", flush=True)
    print("=" * 70 + "\n", flush=True)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping IncuBrix Web Server...")
        httpd.server_close()


if __name__ == "__main__":
    main()
