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
      configFilesLoaded: false,
      configFiles: [],
      selectedConfig: null,
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
      configFileSelect: document.getElementById("configFileSelect"),
      configPath: document.getElementById("configPath"),
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
        if (!state.configFilesLoaded) {
          loadConfigFiles();
        } else if (!state.configLoaded) {
          loadConfig();
        }
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

        const nameRow = document.createElement("div");
        nameRow.className = "name-row";
        const name = document.createElement("span");
        name.textContent = log.name;
        const tag = document.createElement("span");
        tag.className = "tag";
        tag.textContent = log.is_active ? "实时" : "历史";
        if (!log.is_active) {
          tag.style.background = "#f3f4f6";
          tag.style.color = "#4b5563";
        }
        nameRow.appendChild(name);
        nameRow.appendChild(tag);

        const meta = document.createElement("div");
        meta.className = "meta";
        const size = document.createElement("span");
        size.textContent = formatSize(log.size);
        const mtime = document.createElement("span");
        mtime.textContent = log.mtime;
        meta.appendChild(size);
        meta.appendChild(mtime);

        node.appendChild(nameRow);
        node.appendChild(meta);
        node.addEventListener("click", () => selectLog(log.name));
        els.logList.appendChild(node);
      }
    }

    async function readChunk(logName, from) {
      const encoded = encodeURIComponent(logName);
      return fetchJson(`/api/logs/${encoded}?from=${from}`);
    }

    async function loadConfigFiles(preferredName = state.selectedConfig) {
      setConfigStatus("配置文件列表加载中...");
      els.configFileSelect.disabled = true;
      try {
        const data = await fetchJson("/api/config/files");
        state.configFiles = data.files || [];
        state.configFilesLoaded = true;

        els.configFileSelect.innerHTML = "";
        for (const file of state.configFiles) {
          const option = document.createElement("option");
          option.value = file.name;
          option.textContent = file.name + (file.is_active ? "（当前启用）" : "");
          els.configFileSelect.appendChild(option);
        }

        const names = state.configFiles.map(file => file.name);
        const nextName = names.includes(preferredName)
          ? preferredName
          : (names.includes(data.active) ? data.active : (names[0] || null));
        state.selectedConfig = nextName;
        if (!nextName) {
          state.configLoaded = false;
          els.configEditor.value = "";
          els.configPath.textContent = "config 目录中没有可编辑的 TOML 文件";
          setConfigStatus("未找到 TOML 配置文件");
          return;
        }

        els.configFileSelect.value = nextName;
        await loadConfig(nextName);
      } catch (err) {
        state.configFilesLoaded = false;
        setConfigStatus("配置文件列表加载失败: " + err.message);
      } finally {
        els.configFileSelect.disabled = false;
      }
    }

    async function loadConfig(configName = state.selectedConfig) {
      if (!configName) return;
      setConfigStatus("配置加载中...");
      els.configEditor.disabled = true;
      els.configFileSelect.disabled = true;
      els.reloadConfigBtn.disabled = true;
      els.saveConfigBtn.disabled = true;
      els.saveAndReloadConfigBtn.disabled = true;
      try {
        const data = await fetchJson(`/api/config?name=${encodeURIComponent(configName)}`);
        els.configEditor.value = data.content || "";
        state.selectedConfig = data.name;
        state.configLoaded = true;
        els.configPath.textContent = data.path;
        setConfigStatus(`已加载 ${data.name}`);
      } catch (err) {
        state.configLoaded = false;
        setConfigStatus("加载失败: " + err.message);
      } finally {
        els.configEditor.disabled = false;
        els.configFileSelect.disabled = false;
        els.reloadConfigBtn.disabled = false;
        els.saveConfigBtn.disabled = false;
        els.saveAndReloadConfigBtn.disabled = false;
      }
    }

    async function saveConfig() {
      if (!state.selectedConfig) return false;
      setConfigStatus("保存中...");
      els.saveConfigBtn.disabled = true;
      els.saveAndReloadConfigBtn.disabled = true;
      try {
        await fetchJson(`/api/config?name=${encodeURIComponent(state.selectedConfig)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: els.configEditor.value }),
        });
        setConfigStatus(`${state.selectedConfig} 已保存`);
        await refreshConfigFileOptions();
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
      els.saveAndReloadConfigBtn.disabled = true;
      try {
        await _callReloadConfig(setConfigStatus);
      } finally {
        els.saveAndReloadConfigBtn.disabled = false;
      }
    }

    async function saveAndReloadConfig() {
      const ok = await saveConfig();
      if (!ok) return;
      await postReloadConfig();
    }

    async function refreshConfigFileOptions() {
      const selectedName = state.selectedConfig;
      const data = await fetchJson("/api/config/files");
      state.configFiles = data.files || [];
      els.configFileSelect.innerHTML = "";
      for (const file of state.configFiles) {
        const option = document.createElement("option");
        option.value = file.name;
        option.textContent = file.name + (file.is_active ? "（当前启用）" : "");
        els.configFileSelect.appendChild(option);
      }
      if (selectedName) els.configFileSelect.value = selectedName;
    }

    let _reloadInFlight = false;

    async function _callReloadConfig(statusFn) {
      if (_reloadInFlight) {
        statusFn("正在重载中，请等待...");
        return;
      }
      _reloadInFlight = true;
      statusFn("正在调用 reload_config...");
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 35000);
      try {
        const data = await fetchJson("/api/reload_config", {
          method: "POST",
          signal: controller.signal,
        });
        statusFn(data.message || "配置已重载");
      } catch (err) {
        if (err.name === "AbortError") {
          statusFn("重载超时，请检查 ROS 服务是否运行");
        } else {
          statusFn("重载失败: " + err.message);
        }
      } finally {
        clearTimeout(timer);
        _reloadInFlight = false;
      }
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
    els.configFileSelect.addEventListener("change", () => {
      state.selectedConfig = els.configFileSelect.value;
      state.configLoaded = false;
      loadConfig();
    });
    els.reloadConfigBtn.addEventListener("click", () => loadConfig());
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
