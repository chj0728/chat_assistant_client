import argparse
import json
import mimetypes
import os
import posixpath
import re
import subprocess
import urllib.parse
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml
from config import get_default_config_path
from logger.logger import get_logs_dir

ACTIVE_LOG_NAME = "asr_llm_tts"
RELOAD_CONFIG_SERVICE = "/reload_config"
RELOAD_CONFIG_SERVICE_TYPE = "std_srvs/srv/Trigger"


def get_project_root_dir() -> Path:
    """Resolve project root path at ASR_LLM_TTS/chat_assistant."""
    return Path(__file__).resolve().parents[2]


def get_default_logs_dir() -> Path:
    """Resolve logs directory under the chat_assistant package root."""
    # return get_project_root_dir() / "logs"
    return get_logs_dir()


def web_get_default_config_path() -> Path:
    """Resolve config.yaml under the chat_assistant package root."""
    return get_default_config_path()


def get_default_html_path() -> Path:
    """Resolve web UI html file path under chat_assistant/web."""
    return Path(__file__).resolve().with_name("web_server.html")


def get_default_js_path() -> Path:
    """Resolve web UI JavaScript file path under chat_assistant/web."""
    return Path(__file__).resolve().with_name("web_server.js")


def iso_mtime(ts: float) -> str:
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def list_logs(logs_dir: Path) -> list[dict]:
    logs = []
    for item in logs_dir.iterdir():
        if not item.is_file():
            continue
        stat = item.stat()
        logs.append(
            {
                "name": item.name,
                "size": stat.st_size,
                "mtime": iso_mtime(stat.st_mtime),
                "is_active": item.name == ACTIVE_LOG_NAME,
            }
        )
    logs.sort(key=lambda x: (not x["is_active"], x["name"]), reverse=False)
    return logs


def safe_log_path(logs_dir: Path, log_name: str) -> Path:
    if not log_name or "/" in log_name or "\\" in log_name or ".." in log_name:
        raise ValueError("invalid log name")
    file_path = (logs_dir / log_name).resolve()
    logs_root = logs_dir.resolve()
    if file_path.parent != logs_root:
        raise ValueError("invalid log path")
    return file_path


def read_log_incremental(
    file_path: Path, start_offset: int, max_bytes: int = 1024 * 256
) -> tuple[str, int, bool]:
    if start_offset < 0:
        start_offset = 0
    with file_path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()

        # Handle truncation/rotation while frontend keeps an old offset.
        if start_offset > file_size:
            start_offset = 0

        f.seek(start_offset)
        data = f.read(max_bytes)
        next_offset = start_offset + len(data)
        has_more = next_offset < file_size

    return data.decode("utf-8", errors="replace"), next_offset, has_more


def load_index_html(html_path: Path) -> str:
    """Load web UI html from file; return fallback page if file is missing."""
    try:
        return html_path.read_text(encoding="utf-8")
    except OSError as e:
        return (
            "<!doctype html><html><head><meta charset='utf-8'><title>Web Server</title>"
            "</head><body><h3>web_server.html not found</h3>"
            f"<p>{html_path}</p><pre>{e}</pre></body></html>"
        )


def format_yaml_value(value, base_indent: int = 0) -> str:
    """Format a Python value for YAML text replacement."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, list):
        items = ", ".join(f"'{v}'" for v in value)
        return f"[{items}]"
    if isinstance(value, str):
        if "\n" in value or '"' in value or "{" in value:
            lines = value.split("\n")
            indent_str = " " * (base_indent + 2)
            formatted = "|\n" + "\n".join(indent_str + line for line in lines)
            return formatted
        return f'"{value}"'
    return f'"{value}"'


def _extract_inline_comment(rest: str) -> str:
    """Extract inline YAML comment from text after 'key: ', respecting quotes."""
    in_quote = None
    for i, c in enumerate(rest):
        if c in ('"', "'") and in_quote is None:
            in_quote = c
        elif c == in_quote:
            in_quote = None
        elif c == "#" and in_quote is None:
            return rest[i:]
    return ""


def _find_section_line(lines: list[str], section_key: str) -> int:
    """Find the line index of a top-level YAML section header."""
    pat = re.compile(r"^" + re.escape(section_key) + r"\s*:")
    for i, line in enumerate(lines):
        if pat.match(line):
            return i
    return -1


def _replace_line_value(
    lines: list[str], key: str, new_val: str, indent: int = 0, start: int = 0
) -> bool:
    """Replace a YAML value on its line, preserving inline comments."""
    indent_str = " " * indent
    key_pat = re.compile(r"^(" + re.escape(indent_str) + re.escape(key) + r"\s*:\s*)")
    for i in range(start, len(lines)):
        line = lines[i]
        if indent > 0:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not line[0].isspace():
                break
        m = key_pat.match(line)
        if m:
            prefix = m.group(1)
            rest = line[len(prefix) :]
            comment = _extract_inline_comment(rest)

            del_count = 0
            for j in range(i + 1, len(lines)):
                next_line = lines[j]
                if not next_line.strip():
                    del_count += 1
                elif next_line.startswith(" " * (indent + 1)):
                    del_count += 1
                else:
                    break

            for _ in range(del_count):
                lines.pop(i + 1)

            if "\n" in new_val:
                first_line, rest_val = new_val.split("\n", 1)
                new_line = prefix + first_line
                if comment:
                    new_line += " " + comment
                lines[i] = new_line
                for idx, rline in enumerate(rest_val.split("\n")):
                    lines.insert(i + 1 + idx, rline)
            else:
                new_line = prefix + new_val
                if comment:
                    new_line += " " + comment
                lines[i] = new_line
            return True
    return False


def update_yaml_text(text: str, updates: dict) -> str:
    """Apply dotted-key value updates to raw YAML, preserving comments."""
    lines = text.split("\n")
    for key_path, new_value in updates.items():
        parts = key_path.split(".")
        if len(parts) == 1:
            val_str = format_yaml_value(new_value, base_indent=0)
            _replace_line_value(lines, parts[0], val_str, indent=0)
        elif len(parts) == 2:
            val_str = format_yaml_value(new_value, base_indent=2)
            sec_idx = _find_section_line(lines, parts[0])
            if sec_idx >= 0:
                _replace_line_value(
                    lines, parts[1], val_str, indent=2, start=sec_idx + 1
                )
    return "\n".join(lines)


def call_reload_config_service(timeout_sec: float = 30.0) -> tuple[bool, str]:
    cmd = [
        "ros2",
        "service",
        "call",
        RELOAD_CONFIG_SERVICE,
        RELOAD_CONFIG_SERVICE_TYPE,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except FileNotFoundError:
        return False, "ros2 command not found in PATH"
    except subprocess.TimeoutExpired:
        return False, f"call timeout after {timeout_sec:.1f}s"

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    if result.returncode != 0:
        detail = stderr or stdout or f"exit code {result.returncode}"
        return False, detail

    # if "success: true" not in stdout.lower():
    #     detail = stdout or "service call returned without success=true"
    #     return False, detail

    return True, stdout


class LogViewerHandler(BaseHTTPRequestHandler):
    server_version = "ASRLogViewer/1.0"

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(
        self,
        payload: str,
        status: int = HTTPStatus.OK,
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        body = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _logs_dir(self) -> Path:
        return self.server.logs_dir  # type: ignore[attr-defined]

    def _config_path(self) -> Path:
        return self.server.config_path  # type: ignore[attr-defined]

    def _html_path(self) -> Path:
        return self.server.html_path  # type: ignore[attr-defined]

    def _js_path(self) -> Path:
        return self.server.js_path  # type: ignore[attr-defined]

    def _index_html(self) -> str:
        return self.server.index_html  # type: ignore[attr-defined]

    def _drain_body(self) -> None:
        """Read and discard any unread request body to keep the connection clean."""
        raw_len = self.headers.get("Content-Length", "0")
        try:
            content_len = int(raw_len)
        except ValueError:
            content_len = 0
        if content_len > 0:
            self.rfile.read(content_len)

    def _read_json_body(self) -> dict:
        raw_len = self.headers.get("Content-Length", "0")
        try:
            content_len = int(raw_len)
        except ValueError:
            raise ValueError("invalid content length")
        if content_len <= 0:
            return {}
        raw = self.rfile.read(content_len)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            raise ValueError("invalid json body")

    def _parse_path(self) -> tuple[str, list[str], dict]:
        parsed = urllib.parse.urlsplit(self.path)
        clean_path = posixpath.normpath(urllib.parse.unquote(parsed.path))
        parts = [x for x in clean_path.split("/") if x]
        query = urllib.parse.parse_qs(parsed.query)
        return clean_path, parts, query

    def do_GET(self) -> None:
        """Handle read-style API routes and index page rendering."""
        path, parts, query = self._parse_path()

        # UI home page.
        if path == "/":
            self._send_text(self._index_html(), content_type="text/html; charset=utf-8")
            return

        # External JavaScript for frontend logic.
        if path == "/web_server.js":
            js_path = self._js_path()
            if not js_path.exists() or not js_path.is_file():
                self._send_json(
                    {"error": f"js not found: {js_path}"},
                    status=HTTPStatus.NOT_FOUND,
                )
                return
            self._send_text(
                js_path.read_text(encoding="utf-8"),
                content_type="application/javascript; charset=utf-8",
            )
            return

        # Server health and resolved paths.
        if path == "/healthz":
            self._send_json(
                {
                    "ok": True,
                    "logs_dir": str(self._logs_dir()),
                    "config_path": str(self._config_path()),
                    "html_path": str(self._html_path()),
                    "js_path": str(self._js_path()),
                }
            )
            return

        # Read config.yaml content as plain text.
        if path == "/api/config":
            config_path = self._config_path()
            if not config_path.exists() or not config_path.is_file():
                self._send_json(
                    {"error": f"config not found: {config_path}"},
                    status=HTTPStatus.NOT_FOUND,
                )
                return
            content = config_path.read_text(encoding="utf-8")
            self._send_json({"path": str(config_path), "content": content})
            return

        # Structured config params as parsed YAML dict.
        if path == "/api/config/params":
            config_path = self._config_path()
            if not config_path.exists() or not config_path.is_file():
                self._send_json(
                    {"error": f"config not found: {config_path}"},
                    status=HTTPStatus.NOT_FOUND,
                )
                return
            content = config_path.read_text(encoding="utf-8")
            try:
                data = yaml.safe_load(content) or {}
            except yaml.YAMLError as e:
                self._send_json(
                    {"error": f"YAML parse error: {e}"},
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return
            self._send_json({"params": data})
            return

        # Query log list metadata.
        if path == "/api/logs":
            logs_dir = self._logs_dir()
            if not logs_dir.exists():
                logs_dir.mkdir(parents=True, exist_ok=True)
            self._send_json(
                {"logs": list_logs(logs_dir), "active_log": ACTIVE_LOG_NAME}
            )
            return

        # Read one log file incrementally.
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "logs":
            log_name = parts[2]
            try:
                file_path = safe_log_path(self._logs_dir(), log_name)
                if not file_path.exists() or not file_path.is_file():
                    self._send_json(
                        {"error": f"log not found: {log_name}"},
                        status=HTTPStatus.NOT_FOUND,
                    )
                    return

                raw_from = query.get("from", ["0"])[0]
                try:
                    start_offset = int(raw_from)
                except ValueError:
                    self._send_json(
                        {"error": "invalid from offset"}, status=HTTPStatus.BAD_REQUEST
                    )
                    return

                content, next_offset, has_more = read_log_incremental(
                    file_path, start_offset
                )
                self._send_json(
                    {
                        "name": log_name,
                        "content": content,
                        "next_offset": next_offset,
                        "has_more": has_more,
                        "is_active": log_name == ACTIVE_LOG_NAME,
                    }
                )
                return
            except ValueError as e:
                self._send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)
                return

        # fallback static mime support for future extension
        guessed_type, _ = mimetypes.guess_type(path)
        self._send_text(
            "Not Found",
            status=HTTPStatus.NOT_FOUND,
            content_type=guessed_type or "text/plain; charset=utf-8",
        )

    def do_PUT(self) -> None:
        """Handle update-style API routes."""
        path, parts, _ = self._parse_path()

        # Persist config.yaml text content.
        if path == "/api/config":
            config_path = self._config_path()
            try:
                body = self._read_json_body()
            except ValueError as e:
                self._send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)
                return

            content = body.get("content")
            if not isinstance(content, str):
                self._send_json(
                    {"error": "content must be string"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(content, encoding="utf-8")
            self._send_json({"ok": True, "saved": str(config_path)})
            return

        # Update specific config params by dotted key paths.
        if path == "/api/config/params":
            config_path = self._config_path()
            try:
                body = self._read_json_body()
            except ValueError as e:
                self._send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)
                return

            updates = body.get("updates")
            if not isinstance(updates, dict) or not updates:
                self._send_json(
                    {"error": "updates must be a non-empty object"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            if not config_path.exists() or not config_path.is_file():
                self._send_json(
                    {"error": f"config not found: {config_path}"},
                    status=HTTPStatus.NOT_FOUND,
                )
                return

            text = config_path.read_text(encoding="utf-8")
            new_text = update_yaml_text(text, updates)

            try:
                yaml.safe_load(new_text)
            except yaml.YAMLError as e:
                self._send_json(
                    {"error": f"generated YAML is invalid: {e}"},
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return

            config_path.write_text(new_text, encoding="utf-8")
            self._send_json({"ok": True, "saved": str(config_path)})
            return

        self._send_json(
            {"error": f"unknown route: {path}"}, status=HTTPStatus.NOT_FOUND
        )

    def _send_json_close(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        """Send JSON response and close the connection (no keep-alive)."""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_POST(self) -> None:
        """Handle action-style API routes."""
        self._drain_body()
        path, parts, _ = self._parse_path()

        # Trigger ROS reload_config service from web action.
        if path == "/api/reload_config":
            ok, detail = call_reload_config_service()
            if not ok:
                self._send_json_close(
                    {
                        "error": f"reload_config failed: {detail}",
                        "service": RELOAD_CONFIG_SERVICE,
                    },
                    status=HTTPStatus.BAD_GATEWAY,
                )
                return

            self._send_json_close(
                {
                    "ok": True,
                    "service": RELOAD_CONFIG_SERVICE,
                    "message": "配置已重载",
                    "detail": detail,
                }
            )
            return

        self._send_json(
            {"error": f"unknown route: {path}"}, status=HTTPStatus.NOT_FOUND
        )

    def do_DELETE(self) -> None:
        """Handle deletion routes for historical logs."""
        path, parts, _ = self._parse_path()
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "logs":
            log_name = parts[2]
            if log_name == ACTIVE_LOG_NAME:
                self._send_json(
                    {"error": "cannot delete active log"}, status=HTTPStatus.FORBIDDEN
                )
                return

            try:
                file_path = safe_log_path(self._logs_dir(), log_name)
            except ValueError as e:
                self._send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)
                return

            if not file_path.exists() or not file_path.is_file():
                self._send_json(
                    {"error": f"log not found: {log_name}"}, status=HTTPStatus.NOT_FOUND
                )
                return

            file_path.unlink()
            self._send_json({"ok": True, "deleted": log_name})
            return

        self._send_json(
            {"error": f"unknown route: {path}"}, status=HTTPStatus.NOT_FOUND
        )

    def log_message(self, fmt: str, *args) -> None:
        # Keep console output concise; stdout still shows startup hints.
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Log browser web server for ASR_LLM_TTS"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind host, default: 0.0.0.0")
    parser.add_argument(
        "--port", type=int, default=17890, help="Bind port, default: 17890"
    )
    parser.add_argument(
        "--logs-dir", default=str(get_default_logs_dir()), help="Log directory path"
    )
    parser.add_argument(
        "--config-path",
        default=str(web_get_default_config_path()),
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--html-path",
        default=str(get_default_html_path()),
        help="Path to web_server.html",
    )
    parser.add_argument(
        "--js-path",
        default=str(get_default_js_path()),
        help="Path to web_server.js",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logs_dir = Path(args.logs_dir).expanduser().resolve()
    config_path = Path(args.config_path).expanduser().resolve()
    html_path = Path(args.html_path).expanduser().resolve()
    js_path = Path(args.js_path).expanduser().resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)

    server = ThreadingHTTPServer((args.host, args.port), LogViewerHandler)
    server.logs_dir = logs_dir  # type: ignore[attr-defined]
    server.config_path = config_path  # type: ignore[attr-defined]
    server.html_path = html_path  # type: ignore[attr-defined]
    server.js_path = js_path  # type: ignore[attr-defined]
    server.index_html = load_index_html(html_path)  # type: ignore[attr-defined]

    print(f"[log-web] serving on http://{args.host}:{args.port}")
    print(f"[log-web] logs dir: {logs_dir}")
    print(f"[log-web] config path: {config_path}")
    print(f"[log-web] html path: {html_path}")
    print(f"[log-web] js path: {js_path}")
    print(f"[log-web] active log: {ACTIVE_LOG_NAME}")

    import signal
    import sys
    import threading

    def handle_sigterm(signum, frame):
        print("\n[log-web] received SIGTERM, stopping...")
        # running shutdown in a separate thread because shutdown() blocks until the server loop exits
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, handle_sigterm)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[log-web] stopped")
    finally:
        server.server_close()
        sys.exit(0)


if __name__ == "__main__":
    main()
