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


def _run_pipeline_background(cmd: List[str], task_name: str) -> None:
    """Execute a CLI pipeline command in a separate background thread with live log streaming."""
    global _pipeline_status
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

    except Exception as e:
        with _pipeline_lock:
            _pipeline_status["running"] = False
            _pipeline_status["exit_code"] = -1
            _pipeline_status["log_output"].append(f"[{time.strftime('%H:%M:%S')}] Error: {e}")


class IncuBrixRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP handler serving IncuBrix studio assets, reports, and REST APIs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def end_headers(self):
        # Enable CORS and disable aggressive caching for local dashboard updates
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
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

        # REST API Endpoints
        if path == "/api/status":
            self._handle_api_status()
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

        # Fallback to standard static file server
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/run":
            self._handle_api_run()
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
        from scripts.fill_workbook import find_latest_calendar_csv

        cal_path = find_latest_calendar_csv()
        if not cal_path or not cal_path.exists():
            self._send_json_response({"entries": [], "file": None})
            return

        entries = []
        try:
            with open(cal_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    entries.append(dict(r))
        except Exception as e:
            self._send_json_response({"error": str(e), "entries": []}, status=500)
            return

        self._send_json_response({"entries": entries, "file": str(cal_path.relative_to(PROJECT_ROOT))})

    def _handle_api_audit(self) -> None:
        rep_json = PROJECT_ROOT / "reports" / "audit_report_30.json"
        if not rep_json.exists():
            self._send_json_response({"error": "audit_report_30.json not found"}, status=404)
            return
        try:
            with open(rep_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._send_json_response(data)
        except Exception as e:
            self._send_json_response({"error": str(e)}, status=500)

    def _handle_api_preference(self) -> None:
        pref_json = PROJECT_ROOT / "reports" / "preference_test_summary.json"
        if not pref_json.exists():
            self._send_json_response({"error": "preference_test_summary.json not found"}, status=404)
            return
        try:
            with open(pref_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._send_json_response(data)
        except Exception as e:
            self._send_json_response({"error": str(e)}, status=500)

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
            cmd = [python_bin, "scripts/build_30.py"]
            task_name = "Full Batch Engine (MoviePy Video + Carousels + Audit)"
        elif mode == "batch_fast":
            cmd = [python_bin, "scripts/build_30.py", "--skip-video"]
            task_name = "Fast Batch Engine (Carousels + Copy + Audit)"
        elif mode == "single_input":
            src = params.get("input_file", "content/sources/input_1_autonomous_pipelines_blog.md")
            cmd = [python_bin, "-m", "src.main", "--input", src, "--skip-video", "--force"]
            task_name = f"Single Input Pipeline: {Path(src).name}"
        elif mode == "self_healing":
            cmd = [python_bin, "-m", "src.main", "--input", "data/inputs/sample_input.txt", "--simulate-failure", "--skip-video", "--force"]
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


def main() -> None:
    parser = argparse.ArgumentParser(description="IncuBrix Web Command Center Server")
    parser.add_argument("--port", "-p", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    args = parser.parse_args()

    server_address = (args.host, args.port)
    httpd = http.server.ThreadingHTTPServer(server_address, IncuBrixRequestHandler)

    url = f"http://localhost:{args.port}"
    print("\n" + "=" * 70)
    print("      INCUBRIX AUTONOMOUS ENGINE: WEB COMMAND CENTER RUNNING      ")
    print("=" * 70)
    print(f" URL:            {url}")
    print(f" Preference UI:  {url}/tools/preference_test.html")
    print(f" REST API:       {url}/api/status")
    print(" Press Ctrl+C in terminal to stop.")
    print("=" * 70 + "\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping IncuBrix Web Server...")
        httpd.server_close()


if __name__ == "__main__":
    main()
