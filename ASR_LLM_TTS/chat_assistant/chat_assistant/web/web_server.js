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
      configSubTab: "quick",
      quickConfigParams: null,
      quickConfigLoaded: false,
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
      subTabQuick: document.getElementById("subTabQuick"),
      subTabAdvanced: document.getElementById("subTabAdvanced"),
      quickConfigPane: document.getElementById("quickConfigPane"),
      advancedConfigPane: document.getElementById("advancedConfigPane"),
      quickConfigForm: document.getElementById("quickConfigForm"),
      quickReloadBtn: document.getElementById("quickReloadBtn"),
      quickSaveBtn: document.getElementById("quickSaveBtn"),
      quickSaveReloadBtn: document.getElementById("quickSaveReloadBtn"),
      quickConfigStatus: document.getElementById("quickConfigStatus"),
    };

    const CONFIG_SCHEMA = [
      {
        group: "🎤 ASR 语音识别",
        fields: [
          { key: "asr_enable", label: "启用 ASR", type: "bool" },
          { key: "asr_server", label: "ASR 服务类型", type: "checklist", options: ["asr_local", "asr_remote"] },
          { key: "asr_local.host", label: "本地 Host", type: "text", placeholder: "192.168.x.x" },
          { key: "asr_local.port", label: "本地 Port", type: "number" },
          { key: "asr_local.use_websocket", label: "WebSocket", type: "bool" },
          { key: "asr_local.timeout_sec", label: "超时(秒)", type: "number", step: 1 },
          { key: "asr_remote.host", label: "远程 Host", type: "text", placeholder: "192.168.x.x" },
          { key: "asr_remote.port", label: "远程 Port", type: "number" },
        ]
      },
      {
        group: "🤖 LLM 大语言模型",
        fields: [
          { key: "llm_enable", label: "启用 LLM", type: "bool" },
          { key: "llm.host", label: "Host", type: "text", placeholder: "192.168.x.x" },
          { key: "llm.port", label: "Port", type: "number" },
          { key: "llm.timeout_sec", label: "超时(秒)", type: "number", step: 1 },
          { key: "llm.temperature", label: "Temperature", type: "number", step: 0.1, min: 0, max: 1 },
          { key: "llm.max_tokens", label: "Max Tokens", type: "number", step: 1 },
          { key: "llm.enable_thinking", label: "启用思考过程", type: "bool" },
          { key: "llm.enable_stream", label: "流式输出", type: "bool" },
          { key: "llm.system_prompt", label: "系统提示语", type: "textarea" },
        ]
      },
      {
        group: "🔊 TTS 语音合成",
        fields: [
          { key: "tts_enable", label: "启用 TTS", type: "bool" },
          { key: "tts_server", label: "TTS 服务类型", type: "checklist", options: ["tts_local", "tts_remote"] },
          { key: "tts_local.host", label: "本地 Host", type: "text" },
          { key: "tts_local.port", label: "本地 Port", type: "number" },
          { key: "tts_local.speaker_id", label: "Speaker ID", type: "number" },
          { key: "tts_local.speed", label: "语速", type: "number", step: 0.1 },
          { key: "tts_local.use_websocket", label: "WebSocket", type: "bool" },
          { key: "tts_local.timeout_sec", label: "超时(秒)", type: "number", step: 1 },
          { key: "tts_remote.host", label: "远程 Host", type: "text" },
          { key: "tts_remote.port", label: "远程 Port", type: "number" },
          { key: "tts_remote.voice_type", label: "音色", type: "select", options: [
              { value: "default", label: "default (女性活泼)" },
              { value: "zh", label: "zh (男性非标准)" },
              { value: "hard_zh", label: "hard_zh (男性业余)" },
              { value: "longshu_zh", label: "longshu_zh (男性专业)" },
              { value: "longwan_zh", label: "longwan_zh (女性专业)" },
            ]
          },
        ]
      },
      {
        group: "👋 KWS 唤醒词检测",
        fields: [
          { key: "KWS.enable", label: "启用唤醒词", type: "bool" },
          { key: "KWS.wake_word", label: "唤醒词", type: "text" },
          { key: "KWS.fuzzy_similarity_threshold", label: "模糊匹配阈值", type: "number", step: 0.01, min: 0, max: 1 },
          { key: "KWS.failed_kws_counts", label: "未检测到唤醒词次数", type: "number" },
          { key: "KWS.failed_kws_threshold", label: "提示间隔(秒)", type: "number" },
          { key: "KWS.reactive_kws_threshold", label: "重置唤醒间隔(秒)", type: "number" },
        ]
      },
      {
        group: "📊 VAD 语音活动检测",
        fields: [
          { key: "VAD.mode", label: "VAD 模式", type: "select", options: [
              { value: 0, label: "0 - 最宽松" },
              { value: 1, label: "1 - 平衡" },
              { value: 2, label: "2 - 较严格" },
              { value: 3, label: "3 - 最严格" },
            ]
          },
          { key: "VAD.no_speech_threshold", label: "静音阈值(秒)", type: "number", step: 0.01 },
          { key: "VAD.decibel_threshold", label: "分贝阈值(dB)", type: "number", step: 1 },
          { key: "VAD.min_recording_duration", label: "最短录音(秒)", type: "number", step: 0.1 },
          { key: "VAD.max_recording_duration", label: "最长录音(秒)", type: "number", step: 1 },
          { key: "VAD.pause_duration", label: "暂停时长(秒)", type: "number", step: 0.1 },
        ]
      },
      {
        group: "⚙️ 其他设置",
        fields: [
          { key: "enable_replace_special_characters", label: "替换特殊字符", type: "bool" },
          { key: "enable_interrupt_tts", label: "打断 TTS", type: "bool" },
          { key: "energy_instability_check", label: "能量不稳定检测", type: "bool" },
        ]
      },
    ];

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
        if (!state.quickConfigLoaded) {
          loadQuickConfig();
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

    /* ---- Quick Config (structured form) ---- */

    function switchConfigSub(subTab) {
      state.configSubTab = subTab;
      const isQuick = subTab === "quick";
      els.subTabQuick.classList.toggle("active", isQuick);
      els.subTabAdvanced.classList.toggle("active", !isQuick);
      els.quickConfigPane.classList.toggle("hidden", !isQuick);
      els.advancedConfigPane.classList.toggle("hidden", isQuick);
      if (isQuick) {
        loadQuickConfig();
      } else {
        loadConfig();
      }
    }

    function getNestedValue(obj, keyPath) {
      const parts = keyPath.split(".");
      let cur = obj;
      for (const p of parts) {
        if (cur == null || typeof cur !== "object") return undefined;
        cur = cur[p];
      }
      return cur;
    }

    function setQuickStatus(text) {
      els.quickConfigStatus.textContent = text;
    }

    async function loadQuickConfig() {
      setQuickStatus("配置加载中...");
      els.quickReloadBtn.disabled = true;
      els.quickSaveBtn.disabled = true;
      els.quickSaveReloadBtn.disabled = true;
      try {
        const data = await fetchJson("/api/config/params");
        state.quickConfigParams = data.params || {};
        state.quickConfigLoaded = true;
        renderQuickConfig(state.quickConfigParams);
        setQuickStatus("配置已加载");
      } catch (err) {
        setQuickStatus("加载失败: " + err.message);
      } finally {
        els.quickReloadBtn.disabled = false;
        els.quickSaveBtn.disabled = false;
        els.quickSaveReloadBtn.disabled = false;
      }
    }

    function renderQuickConfig(params) {
      const form = els.quickConfigForm;
      form.innerHTML = "";
      for (const section of CONFIG_SCHEMA) {
        const group = document.createElement("div");
        group.className = "config-group";
        const title = document.createElement("h3");
        title.className = "config-group-title";
        title.textContent = section.group;
        group.appendChild(title);

        const grid = document.createElement("div");
        grid.className = "config-grid";

        for (const field of section.fields) {
          const value = getNestedValue(params, field.key);
          const node = createFieldNode(field, value);
          grid.appendChild(node);
        }

        group.appendChild(grid);
        form.appendChild(group);
      }
    }

    function createFieldNode(field, value) {
      const wrapper = document.createElement("div");
      wrapper.className = "config-field" + (field.type === "textarea" ? " wide" : "");

      const label = document.createElement("label");
      label.textContent = field.label;
      label.setAttribute("for", "cfg_" + field.key);
      wrapper.appendChild(label);

      switch (field.type) {
        case "bool": {
          const row = document.createElement("div");
          row.className = "toggle-row";
          const input = document.createElement("input");
          input.type = "checkbox";
          input.className = "toggle";
          input.id = "cfg_" + field.key;
          input.checked = !!value;
          const txt = document.createElement("span");
          txt.className = "toggle-text";
          txt.textContent = value ? "开启" : "关闭";
          input.addEventListener("change", () => { txt.textContent = input.checked ? "开启" : "关闭"; });
          row.appendChild(input);
          row.appendChild(txt);
          wrapper.appendChild(row);
          break;
        }
        case "number": {
          const input = document.createElement("input");
          input.type = "number";
          input.id = "cfg_" + field.key;
          input.value = value != null ? value : "";
          if (field.step != null) input.step = field.step;
          if (field.min != null) input.min = field.min;
          if (field.max != null) input.max = field.max;
          wrapper.appendChild(input);
          break;
        }
        case "text": {
          const input = document.createElement("input");
          input.type = "text";
          input.id = "cfg_" + field.key;
          input.value = value != null ? value : "";
          if (field.placeholder) input.placeholder = field.placeholder;
          wrapper.appendChild(input);
          break;
        }
        case "textarea": {
          const ta = document.createElement("textarea");
          ta.id = "cfg_" + field.key;
          ta.value = value != null ? value : "";
          ta.rows = 3;
          wrapper.appendChild(ta);
          break;
        }
        case "select": {
          const sel = document.createElement("select");
          sel.id = "cfg_" + field.key;
          for (const opt of (field.options || [])) {
            const o = document.createElement("option");
            o.value = opt.value;
            o.textContent = opt.label;
            if (value != null && String(value) === String(opt.value)) o.selected = true;
            sel.appendChild(o);
          }
          wrapper.appendChild(sel);
          break;
        }
        case "checklist": {
          const cw = document.createElement("div");
          cw.className = "checklist-wrapper";
          const curList = Array.isArray(value) ? value : [];
          for (const opt of (field.options || [])) {
            const item = document.createElement("div");
            item.className = "checklist-item";
            const cb = document.createElement("input");
            cb.type = "checkbox";
            cb.value = opt;
            cb.checked = curList.includes(opt);
            cb.dataset.key = field.key;
            const cbId = "cfg_" + field.key + "_" + opt;
            cb.id = cbId;
            const lbl = document.createElement("label");
            lbl.textContent = opt;
            lbl.setAttribute("for", cbId);
            item.appendChild(cb);
            item.appendChild(lbl);
            cw.appendChild(item);
          }
          wrapper.appendChild(cw);
          break;
        }
      }

      return wrapper;
    }

    function collectFormUpdates() {
      const updates = {};
      for (const section of CONFIG_SCHEMA) {
        for (const field of section.fields) {
          if (field.type === "checklist") {
            const cbs = document.querySelectorAll(`[data-key="${field.key}"]`);
            updates[field.key] = Array.from(cbs).filter(cb => cb.checked).map(cb => cb.value);
            continue;
          }
          const el = document.getElementById("cfg_" + field.key);
          if (!el) continue;
          switch (field.type) {
            case "bool":
              updates[field.key] = el.checked;
              break;
            case "number":
              updates[field.key] = el.value === "" ? 0 : Number(el.value);
              break;
            case "select": {
              const isNumeric = field.options && field.options.length > 0 && typeof field.options[0].value === "number";
              updates[field.key] = isNumeric ? Number(el.value) : el.value;
              break;
            }
            default:
              updates[field.key] = el.value;
          }
        }
      }
      return updates;
    }

    async function saveQuickConfig() {
      setQuickStatus("保存中...");
      els.quickSaveBtn.disabled = true;
      els.quickSaveReloadBtn.disabled = true;
      try {
        const updates = collectFormUpdates();
        await fetchJson("/api/config/params", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ updates }),
        });
        state.configLoaded = false;
        setQuickStatus("配置已保存");
        return true;
      } catch (err) {
        setQuickStatus("保存失败: " + err.message);
        return false;
      } finally {
        els.quickSaveBtn.disabled = false;
        els.quickSaveReloadBtn.disabled = false;
      }
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

    async function saveAndReloadQuickConfig() {
      const ok = await saveQuickConfig();
      if (!ok) return;
      els.quickSaveReloadBtn.disabled = true;
      try {
        await _callReloadConfig(setQuickStatus);
      } finally {
        els.quickSaveReloadBtn.disabled = false;
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
    els.subTabQuick.addEventListener("click", () => switchConfigSub("quick"));
    els.subTabAdvanced.addEventListener("click", () => switchConfigSub("advanced"));
    els.reloadConfigBtn.addEventListener("click", loadConfig);
    els.saveConfigBtn.addEventListener("click", saveConfig);
    els.saveAndReloadConfigBtn.addEventListener("click", saveAndReloadConfig);
    els.quickReloadBtn.addEventListener("click", loadQuickConfig);
    els.quickSaveBtn.addEventListener("click", saveQuickConfig);
    els.quickSaveReloadBtn.addEventListener("click", saveAndReloadQuickConfig);
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
