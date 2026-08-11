/* ============================================================
   🐍 مار غذایی (Snake Game) — Ajorpareh Mini App
   ============================================================ */
(function () {
  "use strict";

  const COLS = 20, ROWS = 20, CELL = 24;
  const COLORS = { head: "#00ff88", body: "#00cc66", food: "#ff0066", bonus: "#ffcc00", wall: "#ff0000" };
  const NEON = { head: "#00ff88", body: "#00cc66", food: "#ff0066", bonus: "#ffcc00" };
  const DIRECTIONS = { up: {x:0,y:-1}, down: {x:0,y:1}, left: {x:-1,y:0}, right: {x:1,y:0} };

  let canvas, ctx, snake, food, bonus, direction, nextDirection, score, level, speed;
  let gameOver, paused, started, gameLoop, moveQueue;
  let touchStartX = 0, touchStartY = 0;
  let highScore = parseInt(localStorage.getItem("snake_high") || "0", 10);
  let bonusTimer = 0;

  function $(id) { return document.getElementById(id); }
  function rand(max) { return Math.floor(Math.random() * max); }

  function init() {
    const mid = Math.floor(ROWS / 2);
    snake = [{x: mid, y: mid}, {x: mid - 1, y: mid}, {x: mid - 2, y: mid}];
    direction = "right";
    nextDirection = "right";
    score = 0; level = 1; speed = 180;
    gameOver = false; paused = false; started = true;
    bonus = null; bonusTimer = 0;
    moveQueue = [];
    spawnFood();
    updateStats();
    const overlay = $("snakeOverlay");
    if (overlay) overlay.style.display = "none";
    if (gameLoop) clearInterval(gameLoop);
    gameLoop = setInterval(tick, speed);
  }

  function spawnFood() {
    let pos;
    do {
      pos = {x: rand(COLS), y: rand(ROWS)};
    } while (snake.some(s => s.x === pos.x && s.y === pos.y) || (bonus && bonus.x === pos.x && bonus.y === pos.y));
    food = pos;
  }

  function spawnBonus() {
    let pos;
    do {
      pos = {x: rand(COLS), y: rand(ROWS)};
    } while (snake.some(s => s.x === pos.x && s.y === pos.y) || (food && food.x === pos.x && food.y === pos.y));
    bonus = pos;
    bonusTimer = 80; // ticks
  }

  function drawCell(x, y, color, glow) {
    const px = x * CELL, py = y * CELL;
    ctx.fillStyle = color;
    ctx.fillRect(px + 1, py + 1, CELL - 2, CELL - 2);
    // highlight
    ctx.fillStyle = "rgba(255,255,255,0.2)";
    ctx.fillRect(px + 1, py + 1, CELL - 2, 3);
    ctx.fillRect(px + 1, py + 1, 3, CELL - 2);
    // neon glow
    if (glow) {
      ctx.shadowColor = glow;
      ctx.shadowBlur = 8;
      ctx.strokeStyle = glow;
      ctx.lineWidth = 1.5;
      ctx.strokeRect(px + 1, py + 1, CELL - 2, CELL - 2);
      ctx.shadowBlur = 0;
    }
  }

  function draw() {
    // background
    ctx.fillStyle = "#0a0a1a";
    ctx.fillRect(0, 0, COLS * CELL, ROWS * CELL);
    // grid
    ctx.strokeStyle = "rgba(255,255,255,0.03)";
    ctx.lineWidth = 0.5;
    for (let c = 0; c <= COLS; c++) { ctx.beginPath(); ctx.moveTo(c*CELL,0); ctx.lineTo(c*CELL,ROWS*CELL); ctx.stroke(); }
    for (let r = 0; r <= ROWS; r++) { ctx.beginPath(); ctx.moveTo(0,r*CELL); ctx.lineTo(COLS*CELL,r*CELL); ctx.stroke(); }

    // food
    if (food) {
      ctx.fillStyle = COLORS.food;
      ctx.beginPath();
      ctx.arc(food.x * CELL + CELL/2, food.y * CELL + CELL/2, CELL/2 - 2, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowColor = NEON.food;
      ctx.shadowBlur = 10;
      ctx.strokeStyle = NEON.food;
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.shadowBlur = 0;
    }

    // bonus
    if (bonus) {
      ctx.fillStyle = COLORS.bonus;
      ctx.beginPath();
      ctx.arc(bonus.x * CELL + CELL/2, bonus.y * CELL + CELL/2, CELL/2 - 2, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowColor = NEON.bonus;
      ctx.shadowBlur = 12;
      ctx.strokeStyle = NEON.bonus;
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.shadowBlur = 0;
      // sparkle effect
      if (bonusTimer % 4 < 2) {
        ctx.fillStyle = "rgba(255,255,255,0.6)";
        ctx.fillRect(bonus.x * CELL + CELL/2 - 2, bonus.y * CELL + 4, 4, CELL - 8);
        ctx.fillRect(bonus.x * CELL + 4, bonus.y * CELL + CELL/2 - 2, CELL - 8, 4);
      }
    }

    // snake
    snake.forEach((seg, i) => {
      const isHead = i === 0;
      const color = isHead ? COLORS.head : COLORS.body;
      const glow = isHead ? NEON.head : NEON.body;
      drawCell(seg.x, seg.y, color, glow);
      // eyes on head
      if (isHead) {
        const eyeSize = 3;
        ctx.fillStyle = "#000";
        const cx = seg.x * CELL + CELL / 2;
        const cy = seg.y * CELL + CELL / 2;
        const dir = DIRECTIONS[direction];
        ctx.beginPath();
        ctx.arc(cx + dir.y * 4 - 4, cy - dir.x * 4 - 2, eyeSize, 0, Math.PI * 2);
        ctx.arc(cx + dir.y * 4 + 4, cy - dir.x * 4 - 2, eyeSize, 0, Math.PI * 2);
        ctx.fill();
      }
    });
  }

  function tick() {
    if (gameOver || paused || !started) return;

    // process move queue
    if (moveQueue.length > 0) {
      const next = moveQueue.shift();
      if (isValidDirection(next)) {
        direction = next;
      }
    }

    const dir = DIRECTIONS[direction];
    const head = {x: snake[0].x + dir.x, y: snake[0].y + dir.y};

    // wall collision
    if (head.x < 0 || head.x >= COLS || head.y < 0 || head.y >= ROWS) {
      endGame(); return;
    }
    // self collision
    if (snake.some(s => s.x === head.x && s.y === head.y)) {
      endGame(); return;
    }

    snake.unshift(head);

    // eat food
    if (food && head.x === food.x && head.y === food.y) {
      score += 10 * level;
      level = Math.floor(score / 100) + 1;
      speed = Math.max(60, 180 - (level - 1) * 10);
      clearInterval(gameLoop);
      gameLoop = setInterval(tick, speed);
      spawnFood();
      // spawn bonus every 5 foods
      if (score % 50 === 0 && !bonus) spawnBonus();
    } else if (bonus && head.x === bonus.x && head.y === bonus.y) {
      score += 50 * level;
      bonus = null;
      bonusTimer = 0;
    } else {
      snake.pop();
    }

    // bonus expiry
    if (bonus) {
      bonusTimer--;
      if (bonusTimer <= 0) { bonus = null; }
    }

    updateStats();
    draw();
  }

  function isValidDirection(newDir) {
    const opposites = { up: "down", down: "up", left: "right", right: "left" };
    return newDir !== opposites[direction];
  }

  function move(dir) {
    if (gameOver || !started || paused) return;
    if (isValidDirection(dir)) {
      if (moveQueue.length < 2) moveQueue.push(dir);
    }
  }

  function updateStats() {
    const el = $("snakeScore");
    if (el) el.textContent = score.toLocaleString("fa-IR");
    const lel = $("snakeLevel");
    if (lel) lel.textContent = level.toLocaleString("fa-IR");
    const hel = $("snakeHigh");
    if (hel) hel.textContent = Math.max(score, highScore).toLocaleString("fa-IR");
    const lel2 = $("snakeLength");
    if (lel2) lel2.textContent = snake.length.toLocaleString("fa-IR");
  }

  function endGame() {
    gameOver = true;
    started = false;
    if (gameLoop) clearInterval(gameLoop);
    if (score > highScore) {
      highScore = score;
      localStorage.setItem("snake_high", String(highScore));
    }
    const overlay = $("snakeOverlay");
    if (overlay) {
      overlay.innerHTML = `<div class="sn-overlay-text">🐍 بازی تمام!</div>
        <div class="sn-final-score">امتیاز: <b>${score.toLocaleString("fa-IR")}</b></div>
        <div class="sn-final-info">طول مار: ${snake.length.toLocaleString("fa-IR")} · سطح ${level.toLocaleString("fa-IR")}</div>
        <div class="sn-high">رکورد: ${highScore.toLocaleString("fa-IR")}</div>
        <button id="snakeRestart" class="sn-btn sn-btn-start">🔄 شروع مجدد</button>`;
      overlay.style.display = "flex";
      $("snakeRestart").onclick = init;
    }
    reportReward(score);
  }

  function togglePause() {
    if (gameOver || !started) return;
    paused = !paused;
    const overlay = $("snakeOverlay");
    if (overlay) {
      if (paused) {
        overlay.innerHTML = '<div class="sn-overlay-text">⏸️ متوقف شد</div><button id="snakeResume" class="sn-btn sn-btn-start">▶️ ادامه</button>';
        overlay.style.display = "flex";
        $("snakeResume").onclick = togglePause;
      } else {
        overlay.style.display = "none";
      }
    }
  }

  // Controls
  function handleKey(e) {
    if (gameOver || !started) return;
    if (paused && e.key !== "p" && e.key !== "Escape") return;
    switch (e.key) {
      case "ArrowUp": case "w": e.preventDefault(); move("up"); break;
      case "ArrowDown": case "s": e.preventDefault(); move("down"); break;
      case "ArrowLeft": case "a": e.preventDefault(); move("left"); break;
      case "ArrowRight": case "d": e.preventDefault(); move("right"); break;
      case "p": case "Escape": togglePause(); break;
    }
  }

  function handleTouchStart(e) {
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
  }

  function handleTouchEnd(e) {
    if (gameOver || !started || paused) return;
    const dx = e.changedTouches[0].clientX - touchStartX;
    const dy = e.changedTouches[0].clientY - touchStartY;
    const threshold = 20;
    if (Math.abs(dx) < threshold && Math.abs(dy) < threshold) return;
    if (Math.abs(dx) > Math.abs(dy)) {
      move(dx > 0 ? "right" : "left");
    } else {
      move(dy > 0 ? "down" : "up");
    }
  }

  async function reportReward(finalScore) {
    try {
      const initData = window.Telegram?.WebApp?.initData || "";
      const resp = await fetch("/api/game/reward", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": initData },
        body: JSON.stringify({ game: "snake", score: finalScore }),
      });
      const data = await resp.json();
      if (data.ok && data.awarded > 0) {
        const notice = $("snakeReward");
        if (notice) notice.textContent = `🎉 ${data.awarded.toLocaleString("fa-IR")} XP + ${data.awarded_coins?.toLocaleString("fa-IR") || 0} سکه`;
        if (window.AjorMiniApp?.refreshEconomy) window.AjorMiniApp.refreshEconomy();
      }
    } catch (_) {}
  }

  function mount() {
    const container = $("pageSnake") || $("pageBoardgames");
    if (!container) return;
    container.innerHTML = `
      <div class="sn-wrapper">
        <h2 class="sn-title">🐍 مار غذایی</h2>
        <div class="sn-stats">
          <div class="sn-stat"><span class="sn-stat-label">امتیاز</span><span id="snakeScore" class="sn-stat-value">۰</span></div>
          <div class="sn-stat"><span class="sn-stat-label">سطح</span><span id="snakeLevel" class="sn-stat-value">۱</span></div>
          <div class="sn-stat"><span class="sn-stat-label">طول</span><span id="snakeLength" class="sn-stat-value">۳</span></div>
          <div class="sn-stat"><span class="sn-stat-label">رکورد</span><span id="snakeHigh" class="sn-stat-value">${highScore.toLocaleString("fa-IR")}</span></div>
        </div>
        <div class="sn-game-area">
          <canvas id="snakeCanvas" width="${COLS * CELL}" height="${ROWS * CELL}"></canvas>
          <div id="snakeOverlay" class="sn-overlay">
            <div class="sn-overlay-text">🐍 مار غذایی</div>
            <div class="sn-hint">غذا بخور، بزرگ شو، به خودت نخور!</div>
            <div class="sn-controls-hint">↑↓←→ یا لمس · P = توقف</div>
            <button id="snakeStart" class="sn-btn sn-btn-start">▶️ شروع بازی</button>
          </div>
        </div>
        <div class="sn-controls">
          <button class="sn-ctrl-btn" data-dir="up">⬆</button>
          <div class="sn-ctrl-row">
            <button class="sn-ctrl-btn" data-dir="left">⬅</button>
            <button class="sn-ctrl-btn sn-pause-btn" data-action="pause">⏸</button>
            <button class="sn-ctrl-btn" data-dir="right">➡</button>
          </div>
          <button class="sn-ctrl-btn" data-dir="down">⬇</button>
        </div>
        <div id="snakeReward" class="sn-reward-notice"></div>
      </div>`;

    canvas = $("snakeCanvas");
    ctx = canvas.getContext("2d");
    draw();

    document.addEventListener("keydown", handleKey);
    canvas.addEventListener("touchstart", handleTouchStart, { passive: true });
    canvas.addEventListener("touchend", handleTouchEnd, { passive: true });

    $("snakeStart").onclick = init;

    container.querySelectorAll("[data-dir]").forEach(btn => {
      btn.addEventListener("click", () => move(btn.dataset.dir));
    });
    container.querySelector("[data-action]")?.addEventListener("click", togglePause);
  }

  window.SnakeGame = { mount };
})();
