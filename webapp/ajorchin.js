/* ============================================================
   🧱 آجرچین (Ajorpareh Brick Stacking) — Mini App Game
   ============================================================ */
(function () {
  "use strict";

  /* ---------- ثابت‌ها ---------- */
  const COLS = 10, ROWS = 20, CELL = 28;
  const COLORS = ["#00f0f0","#f0f000","#a000f0","#00f000","#f00000","#0000f0","#f0a000"];
  const SHAPES = [
    [[1,1,1,1]],                     // I
    [[1,1],[1,1]],                    // O
    [[0,1,0],[1,1,1]],               // T
    [[1,0],[1,1],[0,1]],             // S
    [[0,1],[1,1],[1,0]],             // Z
    [[0,0,1],[1,1,1]],               // J
    [[1,0,0],[1,1,1]],               // L
  ];
  const NEON = ["#00ffff","#ffff00","#cc00ff","#00ff00","#ff0000","#3366ff","#ff8800"];

  let canvas, ctx, board, current, currentX, currentY, currentColor, nextPiece, nextColor;
  let score, lines, level, gameOver, paused, started, dropTimer, dropInterval;
  let animatingLineClear = false;
  let clearedRows = [];
  let clearAnimFrame = 0;
  let touchStartX = 0, touchStartY = 0, touchMoved = false;

  function $(id) { return document.getElementById(id); }
  function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }

  function randomPiece() {
    const idx = Math.floor(Math.random() * SHAPES.length);
    return { shape: SHAPES[idx].map(r => [...r]), color: COLORS[idx], neon: NEON[idx], idx };
  }

  function initBoard() {
    board = Array.from({ length: ROWS }, () => Array(COLS).fill(null));
  }

  /* ---------- رسم ---------- */
  function drawCell(x, y, color, neon, ghost) {
    const px = x * CELL, py = y * CELL;
    if (ghost) {
      ctx.fillStyle = "rgba(255,255,255,0.08)";
      ctx.strokeStyle = "rgba(255,255,255,0.2)";
      ctx.lineWidth = 1;
      ctx.fillRect(px, py, CELL, CELL);
      ctx.strokeRect(px + 0.5, py + 0.5, CELL - 1, CELL - 1);
      return;
    }
    ctx.fillStyle = color;
    ctx.fillRect(px, py, CELL, CELL);
    // highlight
    ctx.fillStyle = "rgba(255,255,255,0.25)";
    ctx.fillRect(px, py, CELL, 3);
    ctx.fillRect(px, py, 3, CELL);
    // shadow
    ctx.fillStyle = "rgba(0,0,0,0.3)";
    ctx.fillRect(px, py + CELL - 3, CELL, 3);
    ctx.fillRect(px + CELL - 3, py, 3, CELL);
    // neon glow
    ctx.shadowColor = neon;
    ctx.shadowBlur = 6;
    ctx.strokeStyle = neon;
    ctx.lineWidth = 1.5;
    ctx.strokeRect(px + 1, py + 1, CELL - 2, CELL - 2);
    ctx.shadowBlur = 0;
  }

  function drawBoard() {
    ctx.fillStyle = "#0a0a1a";
    ctx.fillRect(0, 0, COLS * CELL, ROWS * CELL);
    // grid
    ctx.strokeStyle = "rgba(255,255,255,0.04)";
    ctx.lineWidth = 0.5;
    for (let c = 0; c <= COLS; c++) { ctx.beginPath(); ctx.moveTo(c*CELL,0); ctx.lineTo(c*CELL,ROWS*CELL); ctx.stroke(); }
    for (let r = 0; r <= ROWS; r++) { ctx.beginPath(); ctx.moveTo(0,r*CELL); ctx.lineTo(COLS*CELL,r*CELL); ctx.stroke(); }
    // board cells
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        if (board[r][c]) {
          const b = board[r][c];
          // flash effect for cleared rows
          if (clearedRows.includes(r) && animatingLineClear) {
            ctx.fillStyle = clearAnimFrame % 2 === 0 ? "#ffffff" : b.color;
            ctx.fillRect(c * CELL, r * CELL, CELL, CELL);
          } else {
            drawCell(c, r, b.color, b.neon, false);
          }
        }
      }
    }
    // ghost piece
    if (current && !gameOver && !animatingLineClear) {
      let gy = currentY;
      while (fits(current, currentX, gy + 1)) gy++;
      if (gy !== currentY) {
        for (let r = 0; r < current.length; r++)
          for (let c = 0; c < current[r].length; c++)
            if (current[r][c]) drawCell(currentX + c, gy + r, currentColor, "#fff", true);
      }
    }
    // current piece
    if (current && !gameOver && !animatingLineClear) {
      for (let r = 0; r < current.length; r++)
        for (let c = 0; c < current[r].length; c++)
          if (current[r][c]) drawCell(currentX + c, currentY + r, currentColor, currentColor, false);
    }
  }

  function drawNext() {
    const nc = $("ajorchinNext");
    if (!nc) return;
    const nctx = nc.getContext("2d");
    nctx.fillStyle = "#0a0a1a";
    nctx.fillRect(0, 0, nc.width, nc.height);
    if (!nextPiece) return;
    const ns = nextPiece.shape;
    const cellSize = 20;
    const ox = Math.floor((nc.width - ns[0].length * cellSize) / 2);
    const oy = Math.floor((nc.height - ns.length * cellSize) / 2);
    for (let r = 0; r < ns.length; r++)
      for (let c = 0; c < ns[r].length; c++)
        if (ns[r][c]) {
          const px = ox + c * cellSize, py = oy + r * cellSize;
          nctx.fillStyle = nextPiece.color;
          nctx.fillRect(px, py, cellSize, cellSize);
          nctx.fillStyle = "rgba(255,255,255,0.2)";
          nctx.fillRect(px, py, cellSize, 2);
          nctx.shadowColor = nextPiece.neon;
          nctx.shadowBlur = 4;
          nctx.strokeStyle = nextPiece.neon;
          nctx.lineWidth = 1;
          nctx.strokeRect(px + 1, py + 1, cellSize - 2, cellSize - 2);
          nctx.shadowBlur = 0;
        }
  }

  /* ---------- منطق بازی ---------- */
  function fits(shape, x, y) {
    for (let r = 0; r < shape.length; r++)
      for (let c = 0; c < shape[r].length; c++)
        if (shape[r][c]) {
          const nx = x + c, ny = y + r;
          if (nx < 0 || nx >= COLS || ny >= ROWS) return false;
          if (ny >= 0 && board[ny][nx]) return false;
        }
    return true;
  }

  function lock() {
    for (let r = 0; r < current.length; r++)
      for (let c = 0; c < current[r].length; c++)
        if (current[r][c]) {
          const ny = currentY + r;
          if (ny < 0) { gameOver = true; finishGame(); return; }
          board[ny][currentX + c] = { color: currentColor, neon: currentColor };
        }
    // check full lines
    const full = [];
    for (let r = 0; r < ROWS; r++)
      if (board[r].every(cell => cell !== null)) full.push(r);
    if (full.length > 0) {
      animatingLineClear = true;
      clearedRows = full;
      clearAnimFrame = 0;
      const animInterval = setInterval(() => {
        clearAnimFrame++;
        drawBoard();
        if (clearAnimFrame >= 8) {
          clearInterval(animInterval);
          // remove lines
          for (const row of full.sort((a, b) => b - a)) {
            board.splice(row, 1);
            board.unshift(Array(COLS).fill(null));
          }
          clearedRows = [];
          animatingLineClear = false;
          // scoring
          const pts = [0, 100, 300, 500, 800];
          score += (pts[full.length] || 800) * level;
          lines += full.length;
          level = Math.floor(lines / 10) + 1;
          dropInterval = Math.max(100, 800 - (level - 1) * 60);
          updateStats();
          spawnPiece();
        }
      }, 50);
      return;
    }
    spawnPiece();
  }

  function spawnPiece() {
    current = nextPiece.shape;
    currentColor = nextPiece.color;
    const neon = nextPiece.neon;
    currentX = Math.floor((COLS - current[0].length) / 2);
    currentY = -1;
    const np = randomPiece();
    nextPiece = np;
    drawNext();
    if (!fits(current, currentX, currentY)) {
      gameOver = true;
      finishGame();
    }
  }

  function moveLeft()  { if (fits(current, currentX - 1, currentY)) { currentX--; drawBoard(); } }
  function moveRight() { if (fits(current, currentX + 1, currentY)) { currentX++; drawBoard(); } }
  function moveDown()  {
    if (fits(current, currentX, currentY + 1)) { currentY++; return true; }
    else { lock(); return false; }
  }
  function rotate() {
    const rotated = current[0].map((_, i) => current.map(row => row[i]).reverse());
    if (fits(rotated, currentX, currentY)) { current = rotated; drawBoard(); }
    else if (fits(rotated, currentX - 1, currentY)) { current = rotated; currentX--; drawBoard(); }
    else if (fits(rotated, currentX + 1, currentY)) { current = rotated; currentX++; drawBoard(); }
  }
  function hardDrop() {
    while (fits(current, currentX, currentY + 1)) { currentY++; score += 2; }
    lock();
    updateStats();
    drawBoard();
  }

  function updateStats() {
    const el = $("ajorchinScore");
    if (el) el.textContent = score.toLocaleString("fa-IR");
    const lel = $("ajorchinLines");
    if (lel) lel.textContent = lines.toLocaleString("fa-IR");
    const lvl = $("ajorchinLevel");
    if (lvl) lvl.textContent = level.toLocaleString("fa-IR");
  }

  function tick() {
    if (gameOver || paused || !started || animatingLineClear) return;
    moveDown();
    drawBoard();
  }

  /* ---------- کنترل‌ها ---------- */
  function handleKey(e) {
    if (gameOver || !started) return;
    if (paused) { if (e.key === "p" || e.key === "Escape") togglePause(); return; }
    switch (e.key) {
      case "ArrowLeft": case "a": e.preventDefault(); moveLeft(); break;
      case "ArrowRight": case "d": e.preventDefault(); moveRight(); break;
      case "ArrowDown": case "s": e.preventDefault(); moveDown(); score += 1; updateStats(); drawBoard(); break;
      case "ArrowUp": case "w": e.preventDefault(); rotate(); break;
      case " ": e.preventDefault(); hardDrop(); break;
      case "p": case "Escape": togglePause(); break;
    }
  }

  function handleTouchStart(e) {
    if (gameOver || !started || paused) return;
    const t = e.touches[0];
    touchStartX = t.clientX;
    touchStartY = t.clientY;
    touchMoved = false;
  }

  function handleTouchMove(e) {
    if (gameOver || !started || paused) return;
    const t = e.touches[0];
    const dx = t.clientX - touchStartX;
    const dy = t.clientY - touchStartY;
    const threshold = 25;
    if (Math.abs(dx) > threshold && !touchMoved) {
      touchMoved = true;
      if (dx < 0) moveLeft(); else moveRight();
      touchStartX = t.clientX;
      touchMoved = false;
    }
    if (dy > threshold) {
      moveDown(); score += 1; updateStats(); drawBoard();
      touchStartY = t.clientY;
    }
    e.preventDefault();
  }

  function handleTouchEnd(e) {
    if (!touchMoved && e.changedTouches.length) {
      const dx = e.changedTouches[0].clientX - touchStartX;
      const dy = e.changedTouches[0].clientY - touchStartY;
      if (Math.abs(dx) < 15 && Math.abs(dy) < 15) {
        // tap = rotate
        rotate();
      }
    }
  }

  function togglePause() {
    if (gameOver || !started) return;
    paused = !paused;
    const overlay = $("ajorchinOverlay");
    if (overlay) {
      if (paused) {
        overlay.innerHTML = '<div class="ac-overlay-text">⏸️ متوقف شد</div><div class="ac-hint">برای ادامه دکمه Pause رو بزن</div>';
        overlay.style.display = "flex";
      } else {
        overlay.style.display = "none";
      }
    }
  }

  /* ---------- شروع / پایان ---------- */
  function startGame() {
    initBoard();
    score = 0; lines = 0; level = 1; gameOver = false; paused = false; started = true;
    animatingLineClear = false; clearedRows = [];
    dropInterval = 800;
    const np = randomPiece();
    nextPiece = np;
    spawnPiece();
    updateStats();
    drawBoard();
    drawNext();
    const overlay = $("ajorchinOverlay");
    if (overlay) overlay.style.display = "none";
    const startBtn = $("ajorchinStart");
    if (startBtn) startBtn.textContent = "🔄 شروع مجدد";
    if (dropTimer) clearInterval(dropTimer);
    dropTimer = setInterval(tick, 1000);
    setInterval(() => {
      if (!paused && !gameOver && started && !animatingLineClear) {
        clearInterval(dropTimer);
        dropTimer = setInterval(tick, dropInterval);
      }
    }, 5000);
  }

  function finishGame() {
    started = false;
    if (dropTimer) clearInterval(dropTimer);
    const overlay = $("ajorchinOverlay");
    if (overlay) {
      overlay.innerHTML = `<div class="ac-overlay-text">🧱 بازی تمام!</div>
        <div class="ac-final-score">امتیاز: <b>${score.toLocaleString("fa-IR")}</b></div>
        <div class="ac-final-lines">${lines.toLocaleString("fa-IR")} خط پاک شد · سطح ${level.toLocaleString("fa-IR")}</div>
        <button id="ajorchinRestart" class="ac-btn ac-btn-start">🔄 شروع مجدد</button>`;
      overlay.style.display = "flex";
      const rb = $("ajorchinRestart");
      if (rb) rb.onclick = startGame;
    }
    // report reward
    reportReward(score);
  }

  async function reportReward(finalScore) {
    try {
      const initData = window.Telegram?.WebApp?.initData || "";
      const resp = await fetch("/api/game/reward", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": initData },
        body: JSON.stringify({ game: "ajorchin", score: finalScore }),
      });
      const data = await resp.json();
      if (data.ok && data.awarded > 0) {
        const notice = $("ajorchinReward");
        if (notice) notice.textContent = `🎉 ${data.awarded.toLocaleString("fa-IR")} XP + ${data.awarded_coins?.toLocaleString("fa-IR") || 0} سکه`;
        if (window.AjorMiniApp?.refreshEconomy) window.AjorMiniApp.refreshEconomy();
      }
    } catch (_) {}
  }

  /* ---------- مانت ---------- */
  function mount() {
    const container = $("pageBoardgames");
    if (!container) return;
    container.innerHTML = `
      <div class="ac-wrapper">
        <h2 class="ac-title">🧱 آجرچین</h2>
        <div class="ac-stats">
          <div class="ac-stat"><span class="ac-stat-label">امتیاز</span><span id="ajorchinScore" class="ac-stat-value">۰</span></div>
          <div class="ac-stat"><span class="ac-stat-label">خطوط</span><span id="ajorchinLines" class="ac-stat-value">۰</span></div>
          <div class="ac-stat"><span class="ac-stat-label">سطح</span><span id="ajorchinLevel" class="ac-stat-value">۱</span></div>
        </div>
        <div class="ac-game-area">
          <canvas id="ajorchinCanvas" width="${COLS * CELL}" height="${ROWS * CELL}"></canvas>
          <div class="ac-side">
            <div class="ac-next-label">بعدی</div>
            <canvas id="ajorchinNext" width="100" height="80"></canvas>
            <div id="ajorchinReward" class="ac-reward-notice"></div>
          </div>
          <div id="ajorchinOverlay" class="ac-overlay">
            <div class="ac-overlay-text">🧱 آجرچین</div>
            <div class="ac-hint">آجرها رو بچین و خطوط رو پاک کن!</div>
            <button id="ajorchinStart" class="ac-btn ac-btn-start">▶️ شروع بازی</button>
          </div>
        </div>
        <div class="ac-controls">
          <button class="ac-ctrl-btn" data-dir="left">◀</button>
          <button class="ac-ctrl-btn" data-dir="rotate">🔄</button>
          <button class="ac-ctrl-btn ac-btn-drop" data-dir="down">⬇</button>
          <button class="ac-ctrl-btn" data-dir="right">▶</button>
          <button class="ac-ctrl-btn ac-btn-hard" data-dir="hard">⏬</button>
        </div>
        <div class="ac-instructions">
          <span>◀ ▶ حرکت · ⬆ چرخش · ⬇ سریع‌تر · Space پرتاب · کلیک = چرخش</span>
        </div>
      </div>`;

    canvas = $("ajorchinCanvas");
    ctx = canvas.getContext("2d");
    initBoard();
    drawBoard();

    // events
    document.addEventListener("keydown", handleKey);
    canvas.addEventListener("touchstart", handleTouchStart, { passive: true });
    canvas.addEventListener("touchmove", handleTouchMove, { passive: false });
    canvas.addEventListener("touchend", handleTouchEnd, { passive: true });

    $("ajorchinStart").onclick = startGame;

    // control buttons
    container.querySelectorAll("[data-dir]").forEach(btn => {
      btn.addEventListener("click", () => {
        if (gameOver || !started || paused) return;
        switch (btn.dataset.dir) {
          case "left": moveLeft(); break;
          case "right": moveRight(); break;
          case "down": moveDown(); score += 1; updateStats(); drawBoard(); break;
          case "rotate": rotate(); break;
          case "hard": hardDrop(); break;
        }
      });
    });
  }

  /* ---------- خروجی ---------- */
  window.AjorchinGame = { mount };
})();
