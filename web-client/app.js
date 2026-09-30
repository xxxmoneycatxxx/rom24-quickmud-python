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
    // Local room graph: vnum → { x, y, z, exits, name, sector, area }
    // Coordinates assigned by tracking player movement direction.
    // Teleports/recalls detected and placed via collision avoidance.
    // Rendered as a zoomable grid (3×3 – 9×9), terrain-coloured by sector.
    // Persisted to localStorage so explored rooms survive page reloads.
    //
    var STORAGE_KEY = "quickmud_minimap";
    var roomMap       = {};   // vnum → { x, y, z, exits, name, sector, area }
    var currentVnum   = null;
    var currentZ      = 0;
    var pendingMove   = null; // direction string of last movement command
    var gridSize      = 5;    // current zoom level (3–9, odd preferred)
    var hoveredRoom   = null; // vnum of room under cursor (for tooltip)

    var DIR_DELTA = {
        north: [0, -1, 0], south: [0, 1, 0],
        east:  [1, 0, 0],  west:  [-1, 0, 0],
        up:    [0, 0, 1],  down:  [0, 0, -1]
    };

    var DIR_ALIASES = {
        n: "north", s: "south", e: "east", w: "west",
        u: "up", d: "down"
    };

    // P1: Sector type → terrain colour (ROM merc.h SECT_* 0–10)
    var SECTOR_COLORS = {
        0: "#7f8c8d",  // INSIDE   – grey
        1: "#bdc3c7",  // CITY     – light grey
        2: "#a8d8a8",  // FIELD    – light green
        3: "#27ae60",  // FOREST   – dark green
        4: "#d4a76a",  // HILLS    – brown/tan
        5: "#8b6914",  // MOUNTAIN – dark brown
        6: "#3498db",  // WATER_SWIM – blue
        7: "#1a5276",  // WATER_NOSWIM – dark blue
        8: "#555555",  // UNUSED
        9: "#aed6f1",  // AIR      – sky blue
        10: "#f0c040"  // DESERT   – sandy yellow
    };

    // P3: Area name → distinct border colour (hash-based)
    var AREA_BORDER_PALETTE = [
        "#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6",
        "#1abc9c", "#e67e22", "#00bcd4", "#ff7043", "#ab47bc"
    ];
    var areaColorCache = {};
    function areaBorderColor(areaName) {
        if (!areaName) return "#555";
        if (areaColorCache[areaName]) return areaColorCache[areaName];
        var hash = 0;
        for (var i = 0; i < areaName.length; i++) {
            hash = ((hash << 5) - hash + areaName.charCodeAt(i)) | 0;
        }
        var color = AREA_BORDER_PALETTE[Math.abs(hash) % AREA_BORDER_PALETTE.length];
        areaColorCache[areaName] = color;
        return color;
    }

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
            var prev = roomMap[currentVnum];
            if (prev) {
                var prevExits = prev.exits || [];
                if (prevExits.indexOf(pendingMove) >= 0) {
                    // Normal move: direction matches an exit from previous room.
                    var delta = DIR_DELTA[pendingMove];
                    if (!roomMap[vnum]) {
                        roomMap[vnum] = { x: 0, y: 0, z: 0, exits: [], name: null, sector: 0, area: null };
                    }
                    var nr = roomMap[vnum];
                    nr.x = prev.x + delta[0];
                    nr.y = prev.y + delta[1];
                    nr.z = prev.z + delta[2];
                } else {
                    // P0: Teleport / portal / recall — direction not in exits.
                    // Place new room at a unique offset to avoid coordinate collision.
                    if (!roomMap[vnum]) {
                        roomMap[vnum] = { x: 0, y: 0, z: 0, exits: [], name: null, sector: 0, area: null };
                    }
                    var tr = roomMap[vnum];
                    tr.x = prev.x + 1;
                    tr.y = prev.y;
                    tr.z = prev.z;
                    // Collision resolution: shift east until we find an empty slot.
                    while (_roomAt(tr.x, tr.y, tr.z, vnum)) {
                        tr.x++;
                    }
                }
            }
        } else if (!pendingMove && currentVnum != null && vnum !== currentVnum) {
            // No pending move but room changed (login teleport, server redirect).
            if (!roomMap[vnum]) {
                var cur2 = roomMap[currentVnum];
                roomMap[vnum] = { x: 0, y: 0, z: 0, exits: [], name: null, sector: 0, area: null };
                var nr2 = roomMap[vnum];
                if (cur2) {
                    nr2.x = cur2.x + 1;
                    nr2.y = cur2.y;
                    nr2.z = cur2.z;
                    while (_roomAt(nr2.x, nr2.y, nr2.z, vnum)) { nr2.x++; }
                }
            }
        }
        pendingMove = null;

        currentVnum = vnum;
        if (!roomMap[vnum]) {
            roomMap[vnum] = { x: 0, y: 0, z: 0, exits: [], name: null, sector: 0, area: null };
        }
        var r = roomMap[vnum];
        if (msg.exits) r.exits = msg.exits;
        if (msg.room_name) r.name = msg.room_name;
        if (msg.sector != null) r.sector = msg.sector;
        if (msg.area_name) r.area = msg.area_name;
        currentZ = r.z;
        saveMinimap();
        renderMinimap();
    }

    /** Check if any room other than excludeVnum occupies (x, y, z). */
    function _roomAt(x, y, z, excludeVnum) {
        for (var vn in roomMap) {
            if (vn === String(excludeVnum)) continue;
            var rm = roomMap[vn];
            if (rm.x === x && rm.y === y && rm.z === z) return true;
        }
        return false;
    }

    /** Height → brightness modifier for terrain colour. */
    function zAlpha(dz) {
        if (dz > 0)  return 0.7;   // above: slightly dim
        if (dz < 0)  return 0.55;  // below: dimmer
        return 1.0;                 // same level: full brightness
    }

    /** Render the minimap grid on the canvas. */
    function renderMinimap() {
        if (!minimapCtx || !minimapCanvas) return;
        var ctx = minimapCtx;
        var W = minimapCanvas.width;
        var H = minimapCanvas.height;
        var GRID = gridSize;
        var HALF = Math.floor(GRID / 2);
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
            ctx.fillText("\u7B49\u5F85\u8FDE\u63A5\u2026", W / 2, H / 2);
            return;
        }
        var cur = roomMap[currentVnum];
        if (!cur) return;
        var cx = cur.x, cy = cur.y, cz = cur.z;

        // Draw grid cells
        for (var gy = 0; gy < GRID; gy++) {
            for (var gx = 0; gx < GRID; gx++) {
                var wx = cx + (gx - HALF);  // world x
                var wy = cy + (gy - HALF);  // world y
                var px = PAD + gx * CELL;
                var py = PAD + gy * CELL;

                // Grid lines
                ctx.strokeStyle = "#2a2a2a";
                ctx.lineWidth = 1;
                ctx.strokeRect(px + 0.5, py + 0.5, CELL - 1, CELL - 1);

                // Check if any known room exists at this (wx, wy, cz)
                var found = null;
                var foundVnum = null;
                for (var vn in roomMap) {
                    var rm = roomMap[vn];
                    if (rm.x === wx && rm.y === wy && rm.z === cz) {
                        found = rm;
                        foundVnum = vn;
                        break;
                    }
                }

                if (found) {
                    var dz = found.z - cz;
                    var isCurrent = (found === cur);
                    var isHovered = (foundVnum === String(hoveredRoom));

                    // P1: Terrain-coloured fill with z-level alpha modifier
                    var sectorType = found.sector != null ? found.sector : 0;
                    ctx.fillStyle = SECTOR_COLORS[sectorType] || SECTOR_COLORS[0];
                    ctx.globalAlpha = isCurrent ? 1.0 : zAlpha(dz) * 0.65;
                    ctx.fillRect(px + 2, py + 2, CELL - 4, CELL - 4);
                    ctx.globalAlpha = 1.0;

                    // P3: Area border colour (thin coloured outline)
                    if (found.area) {
                        ctx.strokeStyle = areaBorderColor(found.area);
                        ctx.lineWidth = isCurrent ? 2 : 1;
                        ctx.strokeRect(px + 2.5, py + 2.5, CELL - 5, CELL - 5);
                    }

                    // Hover highlight
                    if (isHovered && !isCurrent) {
                        ctx.strokeStyle = "rgba(255,255,255,0.7)";
                        ctx.lineWidth = 1;
                        ctx.strokeRect(px + 1.5, py + 1.5, CELL - 3, CELL - 3);
                    }

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

        // Current room marker – bright white border + inner dot
        var cpx = PAD + HALF * CELL;
        var cpy = PAD + HALF * CELL;
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
            north: [HALF, HALF - 1], south: [HALF, HALF + 1],
            east:  [HALF + 1, HALF], west:  [HALF - 1, HALF]
        };
        for (var i = 0; i < exits.length; i++) {
            var d = exits[i];
            var a = dirArrow[d];
            if (!a) continue;
            // Check if target room is known
            var twx = cx + (a[0] - HALF);
            var twy = cy + (a[1] - HALF);
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

        // Zoom indicator (bottom-right of canvas)
        ctx.fillStyle = "#444";
        ctx.font = "8px monospace";
        ctx.textAlign = "right";
        ctx.textBaseline = "bottom";
        ctx.fillText(GRID + "\u00D7" + GRID, W - 4, H - 3);

        // Update label: room name, area, vnum, exits, z-level, explored count
        if (minimapLabel) {
            var nameStr = cur.name || "";
            var zStr = (cz === 0) ? "" : (cz > 0 ? " +" + cz : " " + cz);
            var explored = Object.keys(roomMap).length;
            var areaStr = cur.area ? cur.area : "";
            var line1 = nameStr ? nameStr : "Room " + currentVnum;
            var line2 = (areaStr ? areaStr + " \u00B7 " : "") + explored + " rooms" + zStr;
            minimapLabel.textContent = line1 + "  |  " + line2;
        }

        // Update tooltip if hovering
        _updateTooltip();
    }

    // ── P2: Zoom controls ────────────────────────────────────────────────

    /** Set grid size and re-render. */
    function setGridSize(n) {
        gridSize = Math.max(3, Math.min(9, n));
        // Ensure odd for symmetric center
        if (gridSize % 2 === 0) gridSize = (gridSize > 5) ? gridSize - 1 : gridSize + 1;
        renderMinimap();
    }

    // Mouse wheel zoom on minimap canvas
    if (minimapCanvas) {
        minimapCanvas.addEventListener("wheel", function (e) {
            e.preventDefault();
            e.stopPropagation();
            setGridSize(gridSize + (e.deltaY < 0 ? 2 : -2));
        }, { passive: false });
    }

    // Keyboard shortcuts: +/- when minimap is focused (optional)
    // Zoom buttons in the clear button area
    var zoomInBtn = document.getElementById("minimap-zoom-in");
    var zoomOutBtn = document.getElementById("minimap-zoom-out");
    if (zoomInBtn) {
        zoomInBtn.addEventListener("click", function (e) {
            e.stopPropagation();
            setGridSize(gridSize + 2);
        });
    }
    if (zoomOutBtn) {
        zoomOutBtn.addEventListener("click", function (e) {
            e.stopPropagation();
            setGridSize(gridSize - 2);
        });
    }

    // ── P4: Click & hover interaction ────────────────────────────────────

    /** Convert canvas (px, py) to world (wx, wy, wz) or null. */
    function canvasToWorld(px, py) {
        if (!minimapCanvas || currentVnum == null) return null;
        var cur = roomMap[currentVnum];
        if (!cur) return null;
        var W = minimapCanvas.width;
        var H = minimapCanvas.height;
        var GRID = gridSize;
        var HALF = Math.floor(GRID / 2);
        var CELL = Math.floor(Math.min(W, H) / GRID);
        var PAD  = Math.floor((W - CELL * GRID) / 2);

        var gx = Math.floor((px - PAD) / CELL);
        var gy = Math.floor((py - PAD) / CELL);
        if (gx < 0 || gx >= GRID || gy < 0 || gy >= GRID) return null;

        var wx = cur.x + (gx - HALF);
        var wy = cur.y + (gy - HALF);
        var wz = cur.z;

        // Find room at this world position
        for (var vn in roomMap) {
            var rm = roomMap[vn];
            if (rm.x === wx && rm.y === wy && rm.z === wz) {
                return { vnum: vn, room: rm };
            }
        }
        return null;
    }

    // Tooltip element (created once, repositioned on hover)
    var tooltipEl = document.getElementById("minimap-tooltip");

    function _updateTooltip() {
        if (!tooltipEl || hoveredRoom == null) {
            if (tooltipEl) tooltipEl.style.display = "none";
            return;
        }
        var rm = roomMap[hoveredRoom];
        if (!rm) { tooltipEl.style.display = "none"; return; }

        var name = rm.name || ("Room " + hoveredRoom);
        var area = rm.area || "";
        var exits = (rm.exits || []).join(", ");
        var zStr = (rm.z === 0) ? "" : (rm.z > 0 ? " +" + rm.z : " " + rm.z);

        tooltipEl.innerHTML = "<b>" + name + "</b><br>"
            + "#" + hoveredRoom + zStr
            + (area ? "<br>" + area : "")
            + (exits ? "<br>\u2192 " + exits : "");
        tooltipEl.style.display = "block";
    }

    if (minimapCanvas) {
        // Enable pointer events on canvas for interaction
        minimapCanvas.style.pointerEvents = "auto";

        minimapCanvas.addEventListener("mousemove", function (e) {
            var rect = minimapCanvas.getBoundingClientRect();
            var px = e.clientX - rect.left;
            var py = e.clientY - rect.top;
            var hit = canvasToWorld(px, py);
            var newHover = hit ? hit.vnum : null;
            if (newHover !== hoveredRoom) {
                hoveredRoom = newHover;
                renderMinimap();
            }
        });

        minimapCanvas.addEventListener("mouseleave", function () {
            if (hoveredRoom !== null) {
                hoveredRoom = null;
                renderMinimap();
            }
        });

        minimapCanvas.addEventListener("click", function (e) {
            var rect = minimapCanvas.getBoundingClientRect();
            var hit = canvasToWorld(e.clientX - rect.left, e.clientY - rect.top);
            if (hit && String(currentVnum) !== hit.vnum) {
                // Display room info in terminal (works for all players, no goto required)
                var rm = hit.room;
                var info = "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n";
                info += "  Room #" + hit.vnum;
                if (rm.name) info += " \u2014 " + rm.name;
                if (rm.area) info += " [" + rm.area + "]";
                info += "\n";
                var exs = (rm.exits || []).join(", ");
                if (exs) info += "  Exits: " + exs + "\n";
                var zStr = (rm.z === 0) ? "" : (rm.z > 0 ? " (level +" + rm.z + ")" : " (level " + rm.z + ")");
                if (zStr) info += "  " + zStr + "\n";
                info += "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500";
                termWriteLine(info);
                term.scrollToBottom();
            }
        });
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
