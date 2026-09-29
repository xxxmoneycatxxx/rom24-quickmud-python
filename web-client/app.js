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
    const statsEl        = document.getElementById("stats");
    const btnConnect     = document.getElementById("btn-connect");
    const btnDisconnect  = document.getElementById("btn-disconnect");
    const btnReconnect   = document.getElementById("btn-reconnect");
    const quickInput     = document.getElementById("quick-input");
    const btnSend        = document.getElementById("btn-send");
    const minimapCanvas  = document.getElementById("minimap");
    const minimapLabel   = document.getElementById("minimap-label");
    const minimapCtx     = minimapCanvas ? minimapCanvas.getContext("2d") : null;
    const minimapClearBtn = document.getElementById("minimap-clear");

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
    // NOTE: FitAddon is NOT used – it fails to attach fit() due to version mismatch.
    // We use manual measurement instead (see fitTerminal below).
    try { term.loadAddon(new WebLinksAddon.WebLinksAddon()); } catch (_) { /* noop */ }
    try { term.loadAddon(new Unicode11Addon.Unicode11Addon()); term.unicode.activeVersion = "11"; } catch (_) { /* noop */ }

    term.open(termContainer);

    /** Fit terminal to container by measuring actual character cell size. */
    function fitTerminal() {
        var w = termContainer.clientWidth;
        var h = termContainer.clientHeight;
        if (w <= 0 || h <= 0) return;
        var probe = document.createElement("span");
        probe.style.cssText = "position:absolute;visibility:hidden;white-space:pre;font-family:'Consolas','Courier New',monospace;font-size:15px;";
        probe.textContent = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
        termContainer.appendChild(probe);
        var charW = probe.offsetWidth / 36;
        var charH = probe.offsetHeight;
        termContainer.removeChild(probe);
        if (charW > 0 && charH > 0) {
            var cols = Math.max(40, Math.floor(w / charW));
            var rows = Math.max(10, Math.floor(h / charH));
            if (term.cols !== cols || term.rows !== rows) {
                term.resize(cols, rows);
            }
        }
    }

    // Delay to ensure DOM layout is complete (minimap panel, etc.)
    setTimeout(fitTerminal, 80);
    window.addEventListener("resize", fitTerminal);

    // ── Application state ─────────────────────────────────────────────────
    let ws              = null;
    let reconnectTimer  = null;
    let autoReconnect   = true;
    let wasConnected    = false;
    let inputHistory    = [];   // command history for ↑/↓ navigation
    let historyIndex    = -1;   // -1 = not browsing history
    let promptShown     = false; // true when a prompt line is on the last terminal row

    // ── Tab completion state ──────────────────────────────────────────────
    var commandList     = [];    // available commands from server
    var tabMatches      = [];    // current completion candidates
    var tabCycleIndex   = -1;    // position in tabMatches cycle
    var tabPrefix       = "";   // original prefix being completed

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

    /** Update the HP/SP/Mana status bar from message fields. */
    function updateStats(msg) {
        if (msg.hp == null && msg.sp == null && msg.mana == null) return;
        var parts = [];
        if (msg.hp   != null) parts.push('<span class="hp">HP:'   + msg.hp   + '</span>');
        if (msg.sp   != null) parts.push('<span class="sp">SP:'   + msg.sp   + '</span>');
        if (msg.mana != null) parts.push('<span class="mana">Mana:' + msg.mana + '</span>');
        if (parts.length > 0) {
            statsEl.innerHTML = parts.join('<span class="sep">|</span>');
        }
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
        // Update status bar if the message carries stat fields.
        updateStats(msg);
        // Update minimap if the message carries room/exits data.
        if (msg.room != null) updateMinimap(msg);

        switch (msg.type) {
            case "output":
            case "info":
                // If a prompt is showing, erase it before writing new output.
                if (promptShown) {
                    term.write("\r\x1b[K");
                    promptShown = false;
                }
                termWriteLine(msg.text);
                term.scrollToBottom();
                break;

            case "prompt":
                var promptText = (msg.text || "").replace(/\r/g, "");
                // Erase previous prompt line if one is showing (dedup).
                if (promptShown) {
                    term.write("\r\x1b[K");
                }
                term.write(promptText);
                promptShown = true;
                // Force viewport to follow the prompt at the bottom.
                term.scrollToBottom();
                // Switch input to password mode when server requests it.
                quickInput.type = (msg.secret === true) ? "password" : "text";
                quickInput.placeholder = (msg.secret === true)
                    ? "输入密码后回车…"
                    : "输入命令后回车…";
                focusInput();
                break;

            case "commands":
                // Server sends available command list for tab completion.
                if (Array.isArray(msg.commands)) {
                    commandList = msg.commands;
                }
                break;

            default:
                if (msg.text) termWriteLine(msg.text);
        }
    }

    // ── Minimap ──────────────────────────────────────────────────────────
    //
    // Local room graph: vnum → { x, y, z, exits: string[], name: string }
    // Coordinates assigned by tracking player movement direction.
    // Rendered as a 5×5 grid centred on the current room, colour-coded by z.
    // Persisted to localStorage so explored rooms survive page reloads.
    //
    var STORAGE_KEY = "quickmud_minimap";
    var roomMap       = {};   // vnum → { x, y, z, exits, name }
    var currentVnum   = null;
    var currentZ      = 0;
    var pendingMove   = null; // direction string of last movement command

    var DIR_DELTA = {
        north: [0, -1, 0], south: [0, 1, 0],
        east:  [1, 0, 0],  west:  [-1, 0, 0],
        up:    [0, 0, 1],  down:  [0, 0, -1]
    };

    var DIR_ALIASES = {
        n: "north", s: "south", e: "east", w: "west",
        u: "up", d: "down"
    };

    /** Load saved roomMap from localStorage. */
    function loadMinimap() {
        try {
            var saved = localStorage.getItem(STORAGE_KEY);
            if (saved) {
                var data = JSON.parse(saved);
                if (data && data.roomMap) {
                    roomMap = data.roomMap;
                }
            }
        } catch (_) { /* corrupt data – start fresh */ }
    }

    /** Save roomMap to localStorage (throttled). */
    var saveTimer = null;
    function saveMinimap() {
        if (saveTimer) return;
        saveTimer = setTimeout(function () {
            saveTimer = null;
            try {
                localStorage.setItem(STORAGE_KEY, JSON.stringify({ roomMap: roomMap }));
            } catch (_) { /* quota exceeded – ignore */ }
        }, 500);
    }

    /** Clear saved map and reset. */
    function clearMinimap() {
        roomMap = {};
        currentVnum = null;
        currentZ = 0;
        try { localStorage.removeItem(STORAGE_KEY); } catch (_) { /* noop */ }
        if (minimapCtx) renderMinimap();
    }

    if (minimapClearBtn) {
        minimapClearBtn.addEventListener("click", function (e) {
            e.stopPropagation();
            clearMinimap();
        });
    }

    // Load saved map on init.
    loadMinimap();

    /** Update minimap state from a server message. */
    function updateMinimap(msg) {
        if (!minimapCtx) return;
        var vnum = msg.room;
        if (vnum == null) return;

        // If we just moved, assign coordinates relative to previous room.
        if (pendingMove && currentVnum != null && vnum !== currentVnum) {
            var delta = DIR_DELTA[pendingMove];
            if (delta && roomMap[currentVnum]) {
                var prev = roomMap[currentVnum];
                if (!roomMap[vnum]) {
                    roomMap[vnum] = { x: 0, y: 0, z: 0, exits: [], name: null };
                }
                var nr = roomMap[vnum];
                nr.x = prev.x + delta[0];
                nr.y = prev.y + delta[1];
                nr.z = prev.z + delta[2];
            }
        }
        pendingMove = null;

        currentVnum = vnum;
        if (!roomMap[vnum]) {
            roomMap[vnum] = { x: 0, y: 0, z: 0, exits: [], name: null };
        }
        var r = roomMap[vnum];
        if (msg.exits) r.exits = msg.exits;
        if (msg.room_name) r.name = msg.room_name;
        currentZ = r.z;
        saveMinimap();
        renderMinimap();
    }

    /** Height → colour mapping (height color scale). */
    function zColor(dz) {
        if (dz > 0)  return "#5dade2";  // above: blue
        if (dz < 0)  return "#e67e22";  // below: orange
        return "#2ecc71";               // same level: green
    }

    /** Render the 5×5 minimap grid on the canvas. */
    function renderMinimap() {
        if (!minimapCtx || !minimapCanvas) return;
        var ctx = minimapCtx;
        var W = minimapCanvas.width;
        var H = minimapCanvas.height;
        var GRID = 5;
        var CELL = Math.floor(Math.min(W, H) / GRID);
        var PAD  = Math.floor((W - CELL * GRID) / 2);

        ctx.clearRect(0, 0, W, H);

        // Background
        ctx.fillStyle = "#111";
        ctx.fillRect(0, 0, W, H);

        if (currentVnum == null) {
            ctx.fillStyle = "#555";
            ctx.font = "12px monospace";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText("等待连接…", W / 2, H / 2);
            return;
        }
        var cur = roomMap[currentVnum];
        if (!cur) return;
        var cx = cur.x, cy = cur.y, cz = cur.z;

        // Draw grid cells
        for (var gy = 0; gy < GRID; gy++) {
            for (var gx = 0; gx < GRID; gx++) {
                var wx = cx + (gx - 2);  // world x
                var wy = cy + (gy - 2);  // world y
                var px = PAD + gx * CELL;
                var py = PAD + gy * CELL;

                // Grid lines
                ctx.strokeStyle = "#2a2a2a";
                ctx.lineWidth = 1;
                ctx.strokeRect(px + 0.5, py + 0.5, CELL - 1, CELL - 1);

                // Check if any known room exists at this (wx, wy, cz)
                var found = null;
                for (var vn in roomMap) {
                    var rm = roomMap[vn];
                    if (rm.x === wx && rm.y === wy && rm.z === cz) {
                        found = rm;
                        break;
                    }
                }

                if (found) {
                    var dz = found.z - cz;
                    var isCurrent = (found === cur);
                    ctx.fillStyle = zColor(dz);
                    ctx.globalAlpha = isCurrent ? 1.0 : 0.55;
                    ctx.fillRect(px + 2, py + 2, CELL - 4, CELL - 4);
                    ctx.globalAlpha = 1.0;

                    // Up/down exit arrows
                    ctx.fillStyle = "#fff";
                    ctx.font = "bold " + Math.max(8, CELL * 0.35) + "px monospace";
                    ctx.textAlign = "center";
                    ctx.textBaseline = "middle";
                    var exs = found.exits || [];
                    if (exs.indexOf("up") >= 0) {
                        ctx.fillText("\u25B2", px + CELL / 2, py + CELL * 0.22);
                    }
                    if (exs.indexOf("down") >= 0) {
                        ctx.fillText("\u25BC", px + CELL / 2, py + CELL * 0.82);
                    }
                } else {
                    ctx.fillStyle = "#1a1a1a";
                    ctx.fillRect(px + 2, py + 2, CELL - 4, CELL - 4);
                }
            }
        }

        // Current room marker – bright pulsing border
        var cpx = PAD + 2 * CELL;
        var cpy = PAD + 2 * CELL;
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 2;
        ctx.strokeRect(cpx + 1, cpy + 1, CELL - 2, CELL - 2);
        // Inner dot
        ctx.fillStyle = "#fff";
        ctx.beginPath();
        ctx.arc(cpx + CELL / 2, cpy + CELL / 2, Math.max(2, CELL * 0.1), 0, Math.PI * 2);
        ctx.fill();

        // Directional connections from current room to adjacent known rooms
        ctx.lineWidth = 1;
        var exits = cur.exits || [];
        var dirArrow = {
            north: [2, 1], south: [2, 3],
            east:  [3, 2], west:  [1, 2]
        };
        for (var i = 0; i < exits.length; i++) {
            var d = exits[i];
            var a = dirArrow[d];
            if (!a) continue;
            // Check if target room is known
            var twx = cx + (a[0] - 2);
            var twy = cy + (a[1] - 2);
            var targetKnown = false;
            for (var vn2 in roomMap) {
                var rm2 = roomMap[vn2];
                if (rm2.x === twx && rm2.y === twy && rm2.z === cz) { targetKnown = true; break; }
            }
            ctx.strokeStyle = targetKnown ? "rgba(255,255,255,0.6)" : "rgba(255,255,255,0.2)";
            var tx = PAD + a[0] * CELL + CELL / 2;
            var ty = PAD + a[1] * CELL + CELL / 2;
            ctx.beginPath();
            ctx.moveTo(cpx + CELL / 2, cpy + CELL / 2);
            ctx.lineTo(tx, ty);
            ctx.stroke();
        }

        // Compass labels (N/E/S/W) outside the grid
        ctx.fillStyle = "#666";
        ctx.font = "9px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        var labelPad = 10;
        ctx.fillText("N", W / 2, PAD - labelPad);
        ctx.fillText("S", W / 2, PAD + GRID * CELL + labelPad);
        ctx.fillText("W", PAD - labelPad, PAD + GRID * CELL / 2);
        ctx.fillText("E", PAD + GRID * CELL + labelPad, PAD + GRID * CELL / 2);

        // Update label: room name, vnum, exits, z-level, explored count
        if (minimapLabel) {
            var nameStr = cur.name || "";
            var zStr = (cz === 0) ? "" : (cz > 0 ? " +" + cz : " " + cz);
            var explored = Object.keys(roomMap).length;
            var line1 = nameStr ? nameStr : "Room " + currentVnum;
            var line2 = explored + " rooms" + (exits.length ? " \u00B7 " + exits.length + " exits" : "") + zStr;
            minimapLabel.textContent = line1 + "  |  " + line2;
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
        // Erase the prompt line if one is showing, so the command appears cleanly.
        if (promptShown) {
            term.write("\r\x1b[K");
            promptShown = false;
        }
        term.writeln("");  // newline after previous output
        termWriteLine("\x1b[1;33m> " + text + "\x1b[0m");
    }

    function sendInput() {
        var text = quickInput.value;
        if (text.length === 0) return;

        // Track movement commands for minimap coordinate assignment.
        var cmd = text.trim().toLowerCase();
        if (DIR_DELTA[cmd] || DIR_ALIASES[cmd]) {
            pendingMove = DIR_ALIASES[cmd] || cmd;
        } else {
            pendingMove = null;
        }

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

        // Tab – command completion.
        if (e.key === "Tab") {
            e.preventDefault();
            if (commandList.length === 0) return;

            var val = quickInput.value;
            // Only complete the first word (command position).
            var spaceIdx = val.indexOf(" ");
            var prefix, isCommandWord;
            if (spaceIdx === -1) {
                prefix = val.toLowerCase();
                isCommandWord = true;
            } else {
                // After a space, no completion for now.
                return;
            }

            // If prefix changed since last Tab, recompute matches.
            if (prefix !== tabPrefix) {
                tabPrefix = prefix;
                tabMatches = [];
                tabCycleIndex = -1;
                if (prefix.length > 0) {
                    for (var i = 0; i < commandList.length; i++) {
                        if (commandList[i].toLowerCase().indexOf(prefix) === 0) {
                            tabMatches.push(commandList[i]);
                        }
                    }
                }
            }

            if (tabMatches.length === 0) return;

            if (tabMatches.length === 1) {
                // Single match – auto-complete with trailing space.
                quickInput.value = tabMatches[0] + " ";
                tabPrefix = "";
                tabMatches = [];
                tabCycleIndex = -1;
            } else {
                // Multiple matches – cycle through them.
                tabCycleIndex = (tabCycleIndex + 1) % tabMatches.length;
                quickInput.value = tabMatches[tabCycleIndex];
                // Show all options on first cycle.
                if (tabCycleIndex === 0) {
                    termWriteLine("\x1b[36m" + tabMatches.join("  ") + "\x1b[0m");
                    term.scrollToBottom();
                }
            }
            return;
        }

        // Any non-Tab key resets completion state.
        tabPrefix = "";
        tabMatches = [];
        tabCycleIndex = -1;

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
