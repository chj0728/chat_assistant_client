import argparse
import json
import mimetypes
import os
import posixpath
import urllib.parse
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ACTIVE_LOG_NAME = "asr_llm_tts"


def get_default_logs_dir() -> Path:
    """Resolve logs directory under the chat_assistant package root."""
    return Path(__file__).resolve().parent.parent / "logs"


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


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ASR LLM TTS 日志浏览</title>
  <style>
    :root {
      --bg: #f7f9fc;
      --panel: #ffffff;
      --panel-2: #eef3f8;
      --text: #1f2a37;
      --muted: #6b7280;
      --line: #d6dee8;
      --accent: #0f766e;
      --danger: #b91c1c;
      --shadow: 0 10px 30px rgba(27, 39, 53, 0.08);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: radial-gradient(circle at 20% 0%, #d9f1ef 0%, var(--bg) 45%) no-repeat;
      color: var(--text);
      min-height: 100vh;
    }

    .layout {
      display: grid;
      grid-template-columns: 300px 1fr;
      grid-template-rows: 1fr 1fr;
      gap: 16px;
      padding: 16px;
      max-width: 1800px;
      margin: 0 auto;
      height: 100vh;
    }

    .layout > .panel:first-child {
      grid-row: span 2;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }

    .panel-header {
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .title {
      font-size: 18px;
      font-weight: 700;
      margin: 0;
      letter-spacing: 0.2px;
    }

    .subtitle {
      margin: 2px 0 0;
      color: var(--muted);
      font-size: 12px;
    }

    .btn {
      border: 1px solid transparent;
      background: var(--accent);
      color: #fff;
      border-radius: 8px;
      padding: 7px 12px;
      font-size: 13px;
      cursor: pointer;
      transition: transform 0.12s ease, opacity 0.2s ease;
    }

    .btn:hover { transform: translateY(-1px); }
    .btn:disabled { opacity: 0.55; cursor: not-allowed; transform: none; }

    .btn-danger { background: var(--danger); }
    .btn-light {
      background: #f8fafc;
      border-color: var(--line);
      color: var(--text);
    }

    .log-list {
      max-height: calc(100vh - 120px);
      overflow: auto;
      padding: 10px;
      background: var(--panel-2);
    }

    .log-item {
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: #fff;
      margin-bottom: 8px;
      cursor: pointer;
      transition: border-color 0.2s ease, transform 0.12s ease;
      animation: fade-in 0.2s ease;
    }

    .log-item:hover { border-color: #9cb3cc; transform: translateY(-1px); }
    .log-item.active { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(15, 118, 110, 0.12); }

    .name-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-size: 14px;
      font-weight: 600;
      margin-bottom: 4px;
      word-break: break-all;
    }

    .tag {
      font-size: 11px;
      border-radius: 99px;
      padding: 2px 8px;
      background: #e8f6f4;
      color: #0f766e;
      white-space: nowrap;
    }

    .meta {
      color: var(--muted);
      font-size: 12px;
      display: flex;
      justify-content: space-between;
      gap: 8px;
    }

    .viewer {
      display: flex;
      flex-direction: column;
      min-height: 0;
    }

    .viewer-toolbar {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }

    .status {
      color: var(--muted);
      font-size: 12px;
    }

    pre {
      margin: 0;
      padding: 16px;
      flex: 1;
      overflow: auto;
      font-family: "JetBrains Mono", "Fira Code", Consolas, monospace;
      font-size: 13px;
      line-height: 1.5;
      background: #0b1420;
      color: #e6f0ff;
      white-space: pre-wrap;
      word-break: break-word;
    }

    .empty {
      color: var(--muted);
      padding: 24px;
      text-align: center;
    }

    @media (max-width: 980px) {
      .layout {
        grid-template-columns: 1fr;
        grid-template-rows: auto;
        height: auto;
        padding: 10px;
      }

      .layout > .panel:first-child {
        grid-row: auto;
      }

      .log-list { max-height: 36vh; }
      .viewer { height: 40vh; }
    }

    @keyframes fade-in {
      from { opacity: 0; transform: translateY(4px); }
      to { opacity: 1; transform: translateY(0); }
    }
  </style>
</head>
<body>
  <div class="layout">
    <section class="panel">
      <div class="panel-header">
        <div>
          <h1 class="title">日志文件</h1>
          <p class="subtitle">实时文件 + 历史记录</p>
        </div>
        <button id="refreshBtn" class="btn btn-light">刷新</button>
      </div>
      <div id="logList" class="log-list"></div>
    </section>

    <!-- 实时日志窗口 -->
    <section class="panel viewer">
      <div class="panel-header">
        <div>
          <h2 class="title" style="font-size:16px;">实时日志 (asr_llm_tts)</h2>
          <p class="subtitle">实时增量更新</p>
        </div>
        <div class="viewer-toolbar">
          <button id="liveClearBtn" class="btn btn-light">清空窗口</button>
        </div>
      </div>
      <pre id="liveLogContent" class="empty">等待实时日志...</pre>
      <div class="panel-header" style="border-top: 1px solid var(--line); border-bottom: none;">
        <span id="liveStatus" class="status">等待操作</span>
      </div>
    </section>

    <!-- 历史日志窗口 -->
    <section class="panel viewer">
      <div class="panel-header">
        <div>
          <h2 id="viewerTitle" class="title" style="font-size:16px;">请选择历史日志</h2>
          <p class="subtitle">历史记录文件浏览</p>
        </div>
        <div class="viewer-toolbar">
          <button id="clearBtn" class="btn btn-light">清空窗口</button>
          <button id="deleteBtn" class="btn btn-danger" disabled>删除日志</button>
        </div>
      </div>
      <pre id="logContent" class="empty">尚未选择历史日志文件</pre>
      <div class="panel-header" style="border-top: 1px solid var(--line); border-bottom: none;">
        <span id="status" class="status">等待操作</span>
      </div>
    </section>
  </div>

  <script>
    const ACTIVE_LOG_NAME = "asr_llm_tts";
    const POLL_INTERVAL_MS = 1000;

    const state = {
      selectedLog: null,
      offset: 0,
      liveOffset: 0,
      pollTimer: null,
      logs: [],
    };

    const els = {
      logList: document.getElementById("logList"),
      logContent: document.getElementById("logContent"),
      liveLogContent: document.getElementById("liveLogContent"),
      viewerTitle: document.getElementById("viewerTitle"),
      status: document.getElementById("status"),
      liveStatus: document.getElementById("liveStatus"),
      refreshBtn: document.getElementById("refreshBtn"),
      deleteBtn: document.getElementById("deleteBtn"),
      clearBtn: document.getElementById("clearBtn"),
      liveClearBtn: document.getElementById("liveClearBtn")
    };

    function formatSize(bytes) {
      if (bytes < 1024) return bytes + " B";
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
      return (bytes / 1024 / 1024).toFixed(1) + " MB";
    }

    function setStatus(text, isLive = false) {
      if (isLive) els.liveStatus.textContent = text;
      else els.status.textContent = text;
    }

    function setLogText(text, replace = false, isLive = false) {
      const target = isLive ? els.liveLogContent : els.logContent;
      target.classList.remove("empty");
      
      if (replace) {
        target.textContent = text;
      } else {
        target.textContent += text;
      }
      
      target.scrollTop = target.scrollHeight;
    }

    function clearViewerText(isLive = false) {
      const target = isLive ? els.liveLogContent : els.logContent;
      target.textContent = "";
      target.classList.remove("empty");
    }

    function stopPolling() {
      if (state.pollTimer) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
      }
    }


    async function fetchJson(url, options = {}) {
      const resp = await fetch(url, options);
      if (!resp.ok) {
        let detail = resp.statusText;
        try {
          const body = await resp.json();
          detail = body.error || detail;
        } catch (_) {}
        throw new Error(detail);
      }
      return resp.json();
    }

    async function loadLogList() {
      const data = await fetchJson("/api/logs");
      state.logs = data.logs || [];
      renderLogList();
    }

    function renderLogList() {
      els.logList.innerHTML = "";
      if (state.logs.length === 0) {
        els.logList.innerHTML = '<div class="empty">日志目录为空</div>';
        return;
      }

      for (const log of state.logs) {
        const node = document.createElement("div");
        node.className = "log-item" + (state.selectedLog === log.name ? " active" : "");
        node.innerHTML = `
          <div class="name-row">
            <span>${log.name}</span>
            ${log.is_active ? '<span class="tag">实时</span>' : '<span class="tag" style="background:#f3f4f6;color:#4b5563;">历史</span>'}
          </div>
          <div class="meta">
            <span>${formatSize(log.size)}</span>
            <span>${log.mtime}</span>
          </div>
        `;
        node.addEventListener("click", () => selectLog(log.name));
        els.logList.appendChild(node);
      }
    }

    async function readChunk(logName, from) {
      const encoded = encodeURIComponent(logName);
      return fetchJson(`/api/logs/${encoded}?from=${from}`);
    }

    async function selectLog(logName) {
      if (logName === ACTIVE_LOG_NAME) {
         // 点击实时日志时，重新加载实时日志
         startPollingActiveLog(true);
         return; 
      }
      
      state.selectedLog = logName;
      state.offset = 0;
      renderLogList();
      clearViewerText(false);

      els.viewerTitle.textContent = `历史日志: ${logName}`;
      els.deleteBtn.disabled = false;
      setStatus("加载中...", false);

      try {
        while (true) {
          const data = await readChunk(logName, state.offset);
          state.offset = data.next_offset;
          if (data.content) setLogText(data.content, false, false);
          if (!data.has_more) break;
        }

        setStatus(`已加载，偏移量 ${state.offset}`, false);
      } catch (err) {
        setStatus("加载失败: " + err.message, false);
      }
    }

    function startPollingActiveLog(forceReload = false) {
      stopPolling();
      
      if (forceReload) {
        state.liveOffset = 0;
        clearViewerText(true);
      }
      
      setStatus("加载初始内容...", true);
      
      // Initial load phase: we could just poll and it'll get the entire file eventually or load it all at once.
      // Easiest is just starting polling from offset 0
      state.pollTimer = setInterval(async () => {
        try {
          const data = await readChunk(ACTIVE_LOG_NAME, state.liveOffset);
          state.liveOffset = data.next_offset;
          if (data.content) {
            setLogText(data.content, false, true);
            setStatus(`实时更新中，偏移量 ${state.liveOffset}`, true);
          }
        } catch (err) {
          setStatus("实时更新失败: " + err.message, true);
        }
      }, POLL_INTERVAL_MS);
      
      // Trigger an immediate initial load without waiting 1s
      (async function immediatelyLoadLive() {
          try {
             while (true) {
               const data = await readChunk(ACTIVE_LOG_NAME, state.liveOffset);
               state.liveOffset = data.next_offset;
               if (data.content) {
                 setLogText(data.content, false, true);
               }
               if (!data.has_more) break;
             }
             setStatus(`实时更新中，偏移量 ${state.liveOffset}`, true);
          } catch (e) {
             // Let the interval handle future retries
          }
      })();
    }

    async function deleteSelectedLog() {
      const logName = state.selectedLog;
      if (!logName || logName === ACTIVE_LOG_NAME) return;

      const ok = confirm(`确认删除历史日志 ${logName} 吗？`);
      if (!ok) return;

      try {
        await fetchJson(`/api/logs/${encodeURIComponent(logName)}`, { method: "DELETE" });
        if (state.selectedLog === logName) {
          state.selectedLog = null;
          state.offset = 0;
          els.viewerTitle.textContent = "请选择历史日志";
          els.logContent.textContent = "已删除该日志，请重新选择";
          els.logContent.classList.add("empty");
        }
        await loadLogList();
        setStatus(`已删除 ${logName}`, false);
      } catch (err) {
        setStatus("删除失败: " + err.message, false);
      }
    }

    els.refreshBtn.addEventListener("click", async () => {
      try {
        await loadLogList();
        setStatus("日志列表已刷新", false);
      } catch (err) {
        setStatus("刷新失败: " + err.message, false);
      }
    });

    els.deleteBtn.addEventListener("click", deleteSelectedLog);
    els.clearBtn.addEventListener("click", () => {
      clearViewerText(false);
      setStatus("窗口已清空（不会影响文件内容）", false);
    });
    els.liveClearBtn.addEventListener("click", () => {
      clearViewerText(true);
      setStatus("窗口已清空（不会影响文件内容）", true);
    });

    window.addEventListener("beforeunload", stopPolling);

    (async function init() {
      try {
        await loadLogList();
        
        // Setup live logging regardless of what is selected
        const active = state.logs.find(x => x.is_active);
        if (active) {
          startPollingActiveLog();
        } else {
          setStatus("未找到实时日志 asr_llm_tts", true);
        }

        // Auto select a historical log if available
        const history = state.logs.find(x => !x.is_active);
        if (history) {
           await selectLog(history.name);
        }

      } catch (err) {
        setStatus("初始化失败: " + err.message, false);
      }
    })();
  </script>
</body>
</html>
"""


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

    def _parse_path(self) -> tuple[str, list[str], dict]:
        parsed = urllib.parse.urlsplit(self.path)
        clean_path = posixpath.normpath(urllib.parse.unquote(parsed.path))
        parts = [x for x in clean_path.split("/") if x]
        query = urllib.parse.parse_qs(parsed.query)
        return clean_path, parts, query

    def do_GET(self) -> None:
        path, parts, query = self._parse_path()

        if path == "/":
            self._send_text(INDEX_HTML, content_type="text/html; charset=utf-8")
            return

        if path == "/healthz":
            self._send_json({"ok": True, "logs_dir": str(self._logs_dir())})
            return

        if path == "/api/logs":
            logs_dir = self._logs_dir()
            if not logs_dir.exists():
                logs_dir.mkdir(parents=True, exist_ok=True)
            self._send_json(
                {"logs": list_logs(logs_dir), "active_log": ACTIVE_LOG_NAME}
            )
            return

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

    def do_DELETE(self) -> None:
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logs_dir = Path(args.logs_dir).expanduser().resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)

    server = ThreadingHTTPServer((args.host, args.port), LogViewerHandler)
    server.logs_dir = logs_dir  # type: ignore[attr-defined]

    print(f"[log-web] serving on http://{args.host}:{args.port}")
    print(f"[log-web] logs dir: {logs_dir}")
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
