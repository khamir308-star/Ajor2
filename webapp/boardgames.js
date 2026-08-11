/* ============================================================
   🎲 منچ (Ludo) و مارپله (Snakes & Ladders) — Ajorpareh Mini App
   - منچ: ۲ نفره (شما + ربات) با قوانین ساده‌شدهٔ کلاسیک
   - مارپله: ۲ نفره (شما + ربات) یا تکنفره با ربات
   ============================================================ */
(function () {
  "use strict";

  let BG = null; // state
  let root = null;
  let mounted = false;
  let timers = [];

  function $id(i) { return document.getElementById(i); }
  function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
  function rollDie() { return Math.floor(Math.random() * 6) + 1; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  // ===== منچ (Ludo) =====
  // مسیر ۵۲ خانه (خانه‌های شماره 0 تا 51). هر بازیکن ۴ مهره.
  // خانه شروع هر بازیکن: قرمز=0، آبی=13، زرد=26، سبز=39
  const LUDO_COLORS = [
    { id: 0, name: "قرمز", emoji: "🔴", start: 0 },
    { id: 1, name: "آبی", emoji: "🔵", start: 13 },
    { id: 2, name: "زرد", emoji: "🟡", start: 26 },
    { id: 3, name: "سبز", emoji: "🟢", start: 39 },
  ];
  const LUDO_HOME_DIST = 50; // فاصله تا خانه نهایی از خانه شروع (بعد از ۵۱ دور می‌زند)

  function ludoInit(players) {
    // players: [{color, name, isBot}] — 2 یا 4
    const state = {
      game: "ludo",
      players: players.map((p, i) => ({
        ...p,
        colorId: i,
        pieces: [-1, -1, -1, -1], // -1 = خانه، 0..51 = روی مسیر
        finished: 0,
      })),
      turn: 0,
      phase: "playing",
      dice: null,
      canRoll: true,
      winner: null,
      log: [],
      startColor: pick(players).colorId,
      rolledSix: 0,
    };
    state.turn = state.startColor;
    return state;
  }

  function ludoPosition(piece, colorId) {
    // موقعیت مهره روی مسیر (۰..۵۱) → خانه
    if (piece < 0) return -1;
    const start = LUDO_COLORS[colorId].start;
    return (start + piece) % 52;
  }

  function ludoCanMove(state, colorId, pieceIdx) {
    const p = state.players[colorId];
    const pos = p.pieces[pieceIdx];
    if (pos < 0) {
      // در خانه: فقط با ۶ می‌تونه بیرون بیاد
      return state.dice === 6;
    }
    // روی مسیر: باید دقیقاً به خانه نهایی برسه یا رد نشه
    return pos + state.dice <= LUDO_HOME_DIST;
  }

  function ludoMove(state, colorId, pieceIdx) {
    const p = state.players[colorId];
    const roll = state.dice;
    if (p.pieces[pieceIdx] < 0) {
      // بیرون آمدن از خانه با ۶
      p.pieces[pieceIdx] = 0;
      addLog(state, `${p.name} مهره ${pieceIdx + 1} رو با ۶ بیرون آورد! 🚀`);
      // خوردن مهره حریف در خانه 0
      for (const other of state.players) {
        if (other.colorId === colorId) continue;
        for (let j = 0; j < 4; j++) {
          if (other.pieces[j] === 0) {
            other.pieces[j] = -1;
            addLog(state, `💥 ${p.name} مهره ${other.name} رو خورد!`);
          }
        }
      }
    } else {
      const target = p.pieces[pieceIdx] + roll;
      if (target > LUDO_HOME_DIST) {
        addLog(state, `${p.name}: حرکت نامعتبر (بیشتر از خانه نهایی).`);
        return false;
      }
      p.pieces[pieceIdx] = target;
      addLog(state, `${p.name} مهره ${pieceIdx + 1} رو ${roll} تا جلو برد.`);
      if (target === LUDO_HOME_DIST) {
        p.finished += 1;
        addLog(state, `🏁 ${p.name} یک مهره رو به خانه رسوند! (${p.finished}/4)`);
        if (p.finished === 4) {
          state.phase = "done";
          state.winner = colorId;
          addLog(state, `👑 ${p.name} برنده شد!`);
        }
      } else {
        // خوردن مهره حریف در خانه جدید
        const pos = ludoPosition(target, colorId);
        for (const other of state.players) {
          if (other.colorId === colorId) continue;
          for (let j = 0; j < 4; j++) {
            if (other.pieces[j] >= 0 && ludoPosition(other.pieces[j], other.colorId) === pos) {
              other.pieces[j] = -1;
              addLog(state, `💥 ${p.name} مهره ${other.name} رو خورد!`);
            }
          }
        }
      }
    }
    return true;
  }

  function ludoAI(state) {
    const colorId = state.turn;
    const p = state.players[colorId];
    // قانون ساده: بیرون آوردن با ۶؛ وگرنه نزدیک‌ترین مهره به خانه
    if (state.dice === 6) {
      for (let i = 0; i < 4; i++) if (p.pieces[i] < 0) return i;
    }
    let best = -1, bestPos = -1;
    for (let i = 0; i < 4; i++) {
      if (p.pieces[i] >= 0 && ludoCanMove(state, colorId, i) && p.pieces[i] > bestPos) {
        bestPos = p.pieces[i];
        best = i;
      }
    }
    if (best === -1) {
      for (let i = 0; i < 4; i++) if (p.pieces[i] < 0) return i;
    }
    return best;
  }

  function ludoAdvance(state) {
    // بعد از حرکت: اگر ۶ بزند دوباره نوبت؛ وگرنه نوبت بعدی
    if (state.dice === 6 && state.phase === "playing") {
      state.canRoll = true;
      addLog(state, `🎲 ${state.players[state.turn].name} ۶ آورد؛ دوباره نوبتشه!`);
    } else if (state.phase === "playing") {
      state.turn = (state.turn + 1) % state.players.length;
      state.canRoll = true;
    }
  }

  // ===== مارپله (Snakes & Ladders) =====
  const SL_BOARD = 100; // خانه 1 تا 100
  const SL_LADDERS = { 4: 14, 9: 31, 20: 38, 28: 84, 40: 59, 51: 67, 63: 81, 71: 91 };
  const SL_SNAKES = { 17: 7, 54: 34, 62: 19, 64: 60, 87: 24, 93: 73, 95: 75, 99: 78 };

  function slInit(playerName, difficulty) {
    return {
      game: "snakes",
      players: [
        { name: playerName, isBot: false, pos: 0 },
        { name: difficulty === "easy" ? "🤖 ربات (آسان)" : difficulty === "hard" ? "🤖 ربات (سخت)" : "🤖 ربات", isBot: true, pos: 0 },
      ],
      turn: 0,
      phase: "playing",
      dice: null,
      canRoll: true,
      winner: null,
      difficulty: difficulty || "medium",
      log: [],
    };
  }

  function slMove(state, playerIdx, roll) {
    const p = state.players[playerIdx];
    let target = p.pos + roll;
    if (target > SL_BOARD) {
      addLog(state, `${p.name} ${roll} آورد ولی از ۱۰۰ رد شد؛ باید دقیق برسه.`);
      return;
    }
    p.pos = target;
    addLog(state, `${p.name} ${roll} تا جلو رفت → خانه ${target}`);
    if (SL_LADDERS[target]) {
      addLog(state, `🪜 نردبان! از ${target} به ${SL_LADDERS[target]}!`);
      p.pos = SL_LADDERS[target];
    } else if (SL_SNAKES[target]) {
      addLog(state, `🐍 مار! از ${target} به ${SL_SNAKES[target]}!`);
      p.pos = SL_SNAKES[target];
    }
    if (p.pos === SL_BOARD) {
      state.phase = "done";
      state.winner = playerIdx;
      addLog(state, `👑 ${p.name} اول به خانه ۱۰۰ رسید و برنده شد!`);
    }
  }

  function slAI(state) {
    // ربات مارپله ساده: همیشه تاس می‌اندازد (هیچ تصمیمی نیست)
    return;
  }

  // ===== رندر =====
  function boardPathHTML(state) {
    // مسیر منچ: ۵۲ خانه در ۸ ردیف مارپیچی
    let html = `<div class="bg-board">`;
    const perRow = 7;
    const rows = 8; // 7*8=56 خانه نمایشی (۵۲ + ۴ خانه شروع)
    // مسیر ساده: از پایین به بالا زیگزاگ
    for (let r = 0; r < rows; r++) {
      html += `<div class="bg-row">`;
      for (let c = 0; c < perRow; c++) {
        const idx = r * perRow + c;
        // خانه‌های مسیر: 0..51 (از پایین-راست)
        const isPath = idx < 52;
        const homeIdx = idx - 52; // 0..3 = خانه‌های شروع رنگ‌ها
        const colorHome = homeIdx >= 0 && homeIdx < 4 ? LUDO_COLORS[homeIdx].emoji : "";
        let cls = "bg-cell";
        let content = "";
        if (isPath) {
          const color = LUDO_COLORS[idx % 4].emoji;
          content = color;
          cls += " path";
        } else if (colorHome) {
          cls += " home";
          content = colorHome;
        }
        // مهره‌های روی این خانه
        const piecesHere = [];
        if (BG && BG.game === "ludo") {
          for (const p of BG.players) {
            for (let pi = 0; pi < 4; pi++) {
              if (p.pieces[pi] >= 0 && ludoPosition(p.pieces[pi], p.colorId) === idx) {
                piecesHere.push(p.emoji);
              }
            }
          }
        }
        if (piecesHere.length) content = piecesHere.join("");
        html += `<div class="${cls}" ${isPath ? `data-path="${idx}"` : ""}>${content}</div>`;
      }
      html += `</div>`;
    }
    html += `</div>`;
    return html;
  }

  function slBoardHTML(state) {
    // مارپله: ۱۰x۱۰ شبکه، خانه 1 پایین-راست
    let html = `<div class="bg-board sl-board">`;
    for (let row = 0; row < 10; row++) {
      html += `<div class="bg-row">`;
      for (let col = 0; col < 10; col++) {
        // چیدمان مارپیچی
        let num;
        if (row % 2 === 0) {
          num = (9 - row) * 10 + col + 1;
        } else {
          num = (9 - row) * 10 + (9 - col) + 1;
        }
        let cls = "bg-cell sl-cell";
        let content = num;
        let extra = "";
        if (SL_LADDERS[num]) { cls += " ladder"; extra = "🪜"; }
        if (SL_SNAKES[num]) { cls += " snake"; extra = "🐍"; }
        // مهره‌ها
        const here = [];
        for (const p of state.players) if (p.pos === num) here.push(p.isBot ? "🤖" : "🧑");
        if (here.length) content = here.join("");
        else if (extra) content = extra + `<small>${num}</small>`;
        html += `<div class="${cls}">${content}</div>`;
      }
      html += `</div>`;
    }
    html += `</div>`;
    return html;
  }

  function addLog(state, msg) {
    state.log.push(msg);
    if (state.log.length > 40) state.log = state.log.slice(-40);
  }

  function render() {
    if (!root || !BG) return;
    const chip = $id("bgStatusChip");
    const state = BG;

    let html = "";
    if (state.game === "ludo") {
      const current = state.players[state.turn];
      html += `<div class="hokm-table">`;
      html += `<div class="hokm-teamline">`;
      for (const p of state.players) {
        html += `<div class="hokm-team ${p.isBot ? "opp" : "you"}" style="${state.turn === p.colorId ? "box-shadow:0 0 12px rgba(34,230,226,.4)" : ""}"><small>${p.emoji} ${esc(p.name)}</small>${p.finished}/4</div>`;
      }
      html += `</div>`;
      html += boardPathHTML(state);
      html += `<div class="bg-dice-area">`;
      if (state.phase === "playing" && state.canRoll && !current.isBot) {
        html += `<button class="hokm-btn gold" id="bgRollBtn">🎲 تاس بنداز</button>`;
      } else if (state.phase === "playing" && state.canRoll && current.isBot) {
        html += `<span class="bg-thinking">🤖 ${esc(current.name)} داره فکر می‌کنه…</span>`;
      }
      if (state.dice) html += `<div class="bg-dice-result">🎲 ${state.dice}</div>`;
      if (state.phase === "done") {
        html += `<button class="hokm-btn gold" id="bgAgainBtn">🔄 بازی دوباره</button>`;
      }
      html += `</div>`;
      html += `</div>`;
      html += `<div class="hokm-dash"><div class="hokm-dash-item"><b>${state.players[0].finished}/4</b><span>مهره‌های شما</span></div><div class="hokm-dash-item"><b>${state.dice || "—"}</b><span>آخرین تاس</span></div><div class="hokm-dash-item"><b>${state.players[state.turn].name.includes("ربات") ? "ربات" : "شما"}</b><span>نوبت</span></div></div>`;
    } else {
      // مارپله
      const current = state.players[state.turn];
      html += `<div class="hokm-table">`;
      html += `<div class="hokm-teamline">`;
      for (const p of state.players) {
        html += `<div class="hokm-team ${p.isBot ? "opp" : "you"}" style="${state.turn === state.players.indexOf(p) ? "box-shadow:0 0 12px rgba(34,230,226,.4)" : ""}"><small>${esc(p.name)}</small>خانه ${p.pos}</div>`;
      }
      html += `</div>`;
      html += slBoardHTML(state);
      html += `<div class="bg-dice-area">`;
      if (state.phase === "playing" && state.canRoll && !current.isBot) {
        html += `<button class="hokm-btn gold" id="bgRollBtn">🎲 تاس بنداز</button>`;
      } else if (state.phase === "playing" && state.canRoll && current.isBot) {
        html += `<span class="bg-thinking">🤖 ${esc(current.name)} داره فکر می‌کنه…</span>`;
      }
      if (state.dice) html += `<div class="bg-dice-result">🎲 ${state.dice}</div>`;
      if (state.phase === "done") {
        html += `<button class="hokm-btn gold" id="bgAgainBtn">🔄 بازی دوباره</button>`;
      }
      html += `</div>`;
      html += `</div>`;
      html += `<div class="hokm-dash"><div class="hokm-dash-item"><b>${state.players[0].pos}</b><span>خانه شما</span></div><div class="hokm-dash-item"><b>${state.dice || "—"}</b><span>آخرین تاس</span></div><div class="hokm-dash-item"><b>${state.players[1].pos}</b><span>خانه ربات</span></div></div>`;
    }

    // لاگ
    html += `<div class="hokm-log">${state.log.map((l) => `<div>${esc(l)}</div>`).join("")}</div>`;
    root.innerHTML = html;

    // رویدادها
    const rollBtn = $id("bgRollBtn");
    if (rollBtn) {
      rollBtn.addEventListener("click", () => {
        if (!BG || BG.phase !== "playing" || !BG.canRoll) return;
        rollAndMove();
      });
    }
    $id("bgAgainBtn")?.addEventListener("click", () => showSetup());
    const logEl = root.querySelector(".hokm-log");
    if (logEl) logEl.scrollTop = logEl.scrollHeight;
    if (chip) chip.textContent = BG.phase === "done" ? "پایان" : "در جریان";
  }

  function rollAndMove() {
    const state = BG;
    const current = state.players[state.turn];
    if (!state.canRoll || state.phase !== "playing") return;
    state.canRoll = false;
    const roll = rollDie();
    state.dice = roll;
    addLog(state, `🎲 ${current.name} تاس انداخت: ${roll}`);

    if (state.game === "ludo") {
      // بررسی حرکت ممکن
      let moved = false;
      for (let i = 0; i < 4; i++) {
        if (ludoCanMove(state, current.colorId, i)) {
          ludoMove(state, current.colorId, i);
          moved = true;
          break;
        }
      }
      if (!moved) {
        addLog(state, `${current.name} نمی‌تونه حرکت کنه.`);
      }
      ludoAdvance(state);
    } else {
      slMove(state, state.turn, roll);
      if (state.phase === "playing") {
        if (roll === 6) {
          addLog(state, `${current.name} ۶ آورد؛ دوباره نوبتشه!`);
        } else {
          state.turn = 1 - state.turn;
        }
        state.canRoll = true;
      }
    }
    render();

    // نوبت ربات
    if (state.phase === "playing" && state.canRoll && state.players[state.turn].isBot) {
      timers.push(setTimeout(() => {
        if (BG && BG.phase === "playing" && BG.canRoll && BG.players[BG.turn].isBot) {
          rollAndMove();
        }
      }, 900));
    }
  }

  // ===== راه‌اندازی =====
  function showSetup() {
    BG = null;
    if (!root) return;
    const chip = $id("bgStatusChip");
    if (chip) chip.textContent = "آماده";
    root.innerHTML = `
      <div class="hokm-intro">
        <div style="font-size:44px">🎲</div>
        <h2>منچ و مارپله</h2>
        <p>دو بازی کلاسیک تخته‌ای — با ربات بازی کن:</p>
        <div class="hokm-actions" style="flex-direction:column;align-items:stretch;max-width:300px;margin:0 auto;gap:10px">
          <button class="hokm-btn" id="bgLudoBtn">🎲 منچ (دو نفره)</button>
          <button class="hokm-btn gold" id="bgSnakesBtn">🐍 مارپله (با ربات)</button>
        </div>
        <div class="hokm-rules" style="margin-top:16px">
          <b>قوانین منچ:</b><br>
          • هر بازیکن ۴ مهره داره؛ با ۶ مهره از خانه بیرون میاد.<br>
          • هر ۶ = یک نوبت اضافه؛ مهره حریف رو که بگیری، می‌فرستیش خانه.<br>
          • اولی که هر ۴ مهره رو به خانه برسونه برنده‌ست.<br><br>
          <b>قوانین مارپله:</b><br>
          • تاس بنداز و برو جلو؛ نردبان = صعود، مار = سقوط!<br>
          • دقیقاً باید به خانه ۱۰۰ برسی.
        </div>
      </div>`;
    $id("bgLudoBtn").addEventListener("click", () => startLudo());
    $id("bgSnakesBtn").addEventListener("click", () => {
      const name = prompt("اسمت چیه؟", "بازیکن") || "بازیکن";
      BG = slInit(name.slice(0, 20), "medium");
      addLog(BG, "🎲 مارپله شروع شد!");
      render();
      // ربات شروع کنه یا کاربر؟ کاربر اول
    });
  }

  function startLudo() {
    const name = prompt("اسمت چیه؟", "بازیکن") || "بازیکن";
    BG = ludoInit([
      { name: name.slice(0, 20), isBot: false },
      { name: "🤖 ربات", isBot: true },
    ]);
    addLog(BG, "🎲 منچ شروع شد! اول با ۶ مهره‌ات رو بیرون بیار.");
    render();
  }

  const BoardGamesApp = {
    mount() {
      if (mounted) return;
      mounted = true;
      root = $id("boardGamesRoot");
      showSetup();
    },
    unmount() {
      mounted = false;
      timers.forEach((t) => clearTimeout(t));
      timers = [];
      root = null;
      BG = null;
    },
  };

  window.BoardGamesApp = BoardGamesApp;
})();
