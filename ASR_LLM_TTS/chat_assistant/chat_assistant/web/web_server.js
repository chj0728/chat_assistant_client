    const ACTIVE_LOG_NAME = "asr_llm_tts";
    const POLL_INTERVAL_MS = 1000;

    const state = {
      selectedLog: null,
      offset: 0,
      liveOffset: 0,
      pollTimer: null,
      logs: [],
      activeTab: "logs",
      configLoaded: false,
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
      liveClearBtn: document.getElementById("liveClearBtn"),
      liveViewer: document.getElementById("liveViewer"),
      historyViewer: document.getElementById("historyViewer"),
      tabLogs: document.getElementById("tabLogs"),
      tabConfig: document.getElementById("tabConfig"),
      logsPane: document.getElementById("logsPane"),
      configPane: document.getElementById("configPane"),
      reloadConfigBtn: document.getElementById("reloadConfigBtn"),
      saveConfigBtn: document.getElementById("saveConfigBtn"),
      saveAndReloadConfigBtn: document.getElementById("saveAndReloadConfigBtn"),
      configEditor: document.getElementById("configEditor"),
      configStatus: document.getElementById("configStatus"),
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

    function setConfigStatus(text) {
      els.configStatus.textContent = text;
    }

    function switchTab(tabName) {
      state.activeTab = tabName;
      const showLogs = tabName === "logs";

      els.tabLogs.classList.toggle("active", showLogs);
      els.tabConfig.classList.toggle("active", !showLogs);
      els.logsPane.classList.toggle("hidden", !showLogs);
      els.configPane.classList.toggle("hidden", showLogs);

      if (showLogs) {
        startPollingActiveLog(false);
      } else {
        stopPolling();
      }
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

    async function loadConfig() {
      setConfigStatus("配置加载中...");
      els.configEditor.disabled = true;
      els.reloadConfigBtn.disabled = true;
      els.saveConfigBtn.disabled = true;
      els.saveAndReloadConfigBtn.disabled = true;
      try {
        const data = await fetchJson("/api/config");
        els.configEditor.value = data.content || "";
        state.configLoaded = true;
        setConfigStatus(`已加载 ${data.path}`);
      } catch (err) {
        setConfigStatus("加载失败: " + err.message);
      } finally {
        els.configEditor.disabled = false;
        els.reloadConfigBtn.disabled = false;
        els.saveConfigBtn.disabled = false;
        els.saveAndReloadConfigBtn.disabled = false;
      }
    }

    async function saveConfig() {
      setConfigStatus("保存中...");
      els.saveConfigBtn.disabled = true;
      els.saveAndReloadConfigBtn.disabled = true;
      try {
        await fetchJson("/api/config", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: els.configEditor.value }),
        });
        setConfigStatus("配置已保存");
        return true;
      } catch (err) {
        setConfigStatus("保存失败: " + err.message);
        return false;
      } finally {
        els.saveConfigBtn.disabled = false;
        els.saveAndReloadConfigBtn.disabled = false;
      }
    }

    async function postReloadConfig() {
      setConfigStatus("正在调用 reload_config...");
      els.saveAndReloadConfigBtn.disabled = true;
      try {
        const data = await fetchJson("/api/reload_config", { method: "POST" });
        setConfigStatus(data.message || "配置已重载");
      } catch (err) {
        setConfigStatus("重载失败: " + err.message);
      } finally {
        els.saveAndReloadConfigBtn.disabled = false;
      }
    }

    async function saveAndReloadConfig() {
      const ok = await saveConfig();
      if (!ok) return;
      await postReloadConfig();
    }

    async function selectLog(logName) {
      if (logName === ACTIVE_LOG_NAME) {
         els.liveViewer.classList.remove("hidden");
         els.historyViewer.classList.add("hidden");
         // 点击实时日志时，重新加载实时日志
         startPollingActiveLog(true);
         return; 
      }
      
      els.historyViewer.classList.remove("hidden");
      els.liveViewer.classList.add("hidden");
      
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
    els.tabLogs.addEventListener("click", () => switchTab("logs"));
    els.tabConfig.addEventListener("click", () => switchTab("config"));
    els.reloadConfigBtn.addEventListener("click", loadConfig);
    els.saveConfigBtn.addEventListener("click", saveConfig);
    els.saveAndReloadConfigBtn.addEventListener("click", saveAndReloadConfig);
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
        switchTab("logs");
        await loadLogList();
        await loadConfig();
        
        // Setup live logging regardless of what is selected
        const active = state.logs.find(x => x.is_active);
        if (active) {
          els.liveViewer.classList.remove("hidden");
          els.historyViewer.classList.add("hidden");
          startPollingActiveLog();
        } else {
          setStatus("未找到实时日志 asr_llm_tts", true);
        }

      } catch (err) {
        setStatus("初始化失败: " + err.message, false);
      }
    })();
