/**
 * QuickMUD Web Client – xterm.js ↔ WebSocket bridge
 *
 * Input model: the bottom input bar is the PRIMARY (and only) input method.
 * xterm.js is display-only – it renders server output with ANSI colours but
 * does NOT capture keyboard input.  This avoids the confusing "cursor in the
 * terminal instead of the input box" problem.
 *
 * Wire protocol (matching mud/network/websocket_stream.py):
 *   Server → Client:
 *     { type: "output"|"info", text: string, ts?: string, ... }
 *     { type: "prompt",        text: string, session_state: string, secret: bool }
 *   Client → Server:
 *     { text: string }
 */

(function () {
    "use strict";

    // ── Configuration ─────────────────────────────────────────────────────
    const WS_RECONNECT_BASE_DELAY_MS = 2000;
    const WS_RECONNECT_MAX_DELAY_MS  = 30000;
    const RECONNECT_COUNTDOWN_SECS   = 5;
    const INPUT_HISTORY_MAX          = 100;

    // Derive WS URL from current page location so it works on any host.
    function deriveWsUrl() {
        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        return proto + "//" + location.host + "/ws";
    }

    // ── DOM handles ───────────────────────────────────────────────────────
    const termContainer  = document.getElementById("terminal-container");
    const statusEl       = document.getElementById("status");
    const btnConnect     = document.getElementById("btn-connect");
    const btnDisconnect  = document.getElementById("btn-disconnect");
    const btnReconnect   = document.getElementById("btn-reconnect");
    const quickInput     = document.getElementById("quick-input");
    const btnSend        = document.getElementById("btn-send");

    // ── Terminal (display-only) ───────────────────────────────────────────
    const term = new Terminal({
        cursorBlink:    false,  // display-only – no visible cursor needed
        cursorStyle:    "underline",
        fontSize:       15,
        fontFamily:     "'Consolas', 'Courier New', monospace",
        theme:          { background: "#000000", foreground: "#d0d0d0" },
        convertEol:     false,
        scrollback:     10000,
        allowProposedApi: true,
        disableStdin:   true,   // prevent any keyboard passthrough
    });

    // Addons – wrapped in try/catch so a missing file degrades gracefully.
    try { term.loadAddon(new FitAddon.FitAddon()); } catch (_) { /* noop */ }
    try { term.loadAddon(new WebLinksAddon.WebLinksAddon()); } catch (_) { /* noop */ }
    try { term.loadAddon(new Unicode11Addon.Unicode11Addon()); term.unicode.activeVersion = "11"; } catch (_) { /* noop */ }

    term.open(termContainer);
    if (typeof term.fit === "function") {
        term.fit();
        window.addEventListener("resize", function () { term.fit(); });
    }
    try {
        if (typeof WebglAddon !== "undefined") {
            const webgl = new WebglAddon.WebglAddon();
            webgl.onContextLoss(function () { webgl.dispose(); });
            term.loadAddon(webgl);
        }
    } catch (_) { /* fallback to default renderer */ }

    // ── Application state ─────────────────────────────────────────────────
    let ws              = null;
    let reconnectTimer  = null;
    let autoReconnect   = true;
    let wasConnected    = false;
    let inputHistory    = [];   // command history for ↑/↓ navigation
    let historyIndex    = -1;   // -1 = not browsing history

    // ── UI helpers ────────────────────────────────────────────────────────
    function setStatus(state, label) {
        statusEl.className = state;
        statusEl.textContent = label;
    }

    function updateButtons(connected, connecting) {
        btnConnect.disabled    = connected || connecting;
        btnDisconnect.disabled = !connected && !connecting;
        btnReconnect.disabled  = !wasConnected;
    }

    function termWriteLine(text) {
        var lines = text.split("\n");
        for (var i = 0; i < lines.length; i++) {
            term.writeln(lines[i].replace(/\r/g, ""));
        }
    }

    /** Keep the input box focused at all times. */
    function focusInput() {
        // Use requestAnimationFrame to avoid fighting with browser focus rules.
        requestAnimationFrame(function () { quickInput.focus(); });
    }

    // ── WebSocket layer ───────────────────────────────────────────────────
    function connect() {
        if (ws) { ws.close(); ws = null; }

        var url = deriveWsUrl();
        setStatus("connecting", "连接中…");
        updateButtons(false, true);

        ws = new WebSocket(url);

        ws.onopen = function () {
            setStatus("connected", "已连接");
            updateButtons(true, false);
            wasConnected  = true;
            autoReconnect = true;
            focusInput();
        };

        ws.onmessage = function (ev) {
            try {
                handleMessage(JSON.parse(ev.data));
            } catch (err) {
                termWriteLine(String(ev.data));
            }
        };

        ws.onclose = function () {
            setStatus("disconnected", "已断开");
            updateButtons(false, false);
            ws = null;
            if (autoReconnect) scheduleReconnect();
        };

        ws.onerror = function () {
            termWriteLine("\x1b[31m[连接错误]\x1b[0m");
        };
    }

    function disconnect() {
        autoReconnect = false;
        clearReconnectTimer();
        if (ws) { ws.close(); ws = null; }
        setStatus("disconnected", "已断开");
        updateButtons(false, false);
    }

    function sendLine(text) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ text: text }));
        }
    }

    // ── Message dispatch ──────────────────────────────────────────────────
    function handleMessage(msg) {
        switch (msg.type) {
            case "output":
            case "info":
                termWriteLine(msg.text);
                break;

            case "prompt":
                // Write prompt text WITHOUT trailing newline so it appears
                // at the bottom of the terminal output area.
                var promptText = (msg.text || "").replace(/\r/g, "");
                term.write(promptText);
                // Switch input to password mode when server requests it.
                quickInput.type = (msg.secret === true) ? "password" : "text";
                quickInput.placeholder = (msg.secret === true)
                    ? "输入密码后回车…"
                    : "输入命令后回车…";
                focusInput();
                break;

            default:
                if (msg.text) termWriteLine(msg.text);
        }
    }

    // ── Reconnect with exponential back-off + countdown ───────────────────
    function clearReconnectTimer() {
        if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    }

    function scheduleReconnect() {
        clearReconnectTimer();
        var remaining = RECONNECT_COUNTDOWN_SECS;
        setStatus("disconnected", remaining + "s 后重连…");

        reconnectTimer = setInterval(function () {
            remaining--;
            if (remaining <= 0) {
                clearReconnectTimer();
                connect();
            } else {
                setStatus("disconnected", remaining + "s 后重连…");
            }
        }, 1000);
    }

    // ── Input handling (bottom input bar is the sole input method) ────────

    /** Echo a command into the terminal for visual history. */
    function echoToTerminal(text) {
        term.writeln("");  // newline after the prompt
        termWriteLine("\x1b[1;33m> " + text + "\x1b[0m");
    }

    function sendInput() {
        var text = quickInput.value;
        if (text.length === 0) return;

        // Echo command to terminal for visual history.
        echoToTerminal(text);

        // Send to server.
        sendLine(text);

        // Save to history (deduplicate consecutive entries).
        if (inputHistory.length === 0 || inputHistory[inputHistory.length - 1] !== text) {
            inputHistory.push(text);
            if (inputHistory.length > INPUT_HISTORY_MAX) inputHistory.shift();
        }
        historyIndex = -1;

        // Clear input and reset password mode.
        quickInput.value = "";
        quickInput.type  = "text";
        quickInput.placeholder = "输入命令后回车…";
        focusInput();
    }

    btnSend.addEventListener("click", function () { sendInput(); });

    quickInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            e.preventDefault();
            sendInput();
            return;
        }

        // ↑ Arrow – navigate command history (backwards).
        if (e.key === "ArrowUp") {
            e.preventDefault();
            if (inputHistory.length === 0) return;
            if (historyIndex < 0) historyIndex = inputHistory.length - 1;
            else if (historyIndex > 0) historyIndex--;
            quickInput.value = inputHistory[historyIndex];
            return;
        }

        // ↓ Arrow – navigate command history (forwards).
        if (e.key === "ArrowDown") {
            e.preventDefault();
            if (historyIndex < 0) return;
            historyIndex++;
            if (historyIndex >= inputHistory.length) {
                historyIndex = -1;
                quickInput.value = "";
            } else {
                quickInput.value = inputHistory[historyIndex];
            }
            return;
        }
    });

    // ── Button wiring ─────────────────────────────────────────────────────
    btnConnect.addEventListener("click", function () {
        autoReconnect = true;
        connect();
        focusInput();
    });
    btnDisconnect.addEventListener("click", disconnect);
    btnReconnect.addEventListener("click", function () {
        autoReconnect = true;
        connect();
        focusInput();
    });

    // ── Boot ──────────────────────────────────────────────────────────────
    term.writeln("\x1b[1;36m╔══════════════════════════════════════╗\x1b[0m");
    term.writeln("\x1b[1;36m║\x1b[0m  \x1b[1;35mQuickMUD Web Client\x1b[0m                  \x1b[1;36m║\x1b[0m");
    term.writeln("\x1b[1;36m╚══════════════════════════════════════╝\x1b[0m");
    term.writeln("");
    term.writeln("\x1b[33m在下方输入框输入命令，按回车发送。\x1b[0m");
    term.writeln("\x1b[33m支持 ↑/↓ 翻阅历史命令。\x1b[0m");
    term.writeln("");

    // Auto-connect on page load.
    connect();

    // Always refocus the input box when user clicks anywhere on the page.
    document.addEventListener("click", function (e) {
        // Don't steal focus from buttons (connect/disconnect/reconnect/send).
        if (e.target.tagName === "BUTTON") return;
        focusInput();
    });

    // Refocus input when the window regains focus (tab switch, alt-tab, etc.).
    window.addEventListener("focus", focusInput);
    window.addEventListener("beforeunload", clearReconnectTimer);
})();
