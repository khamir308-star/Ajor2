/* ============================================================
   🎴 بازی حکم چهارنفره — Ajorpareh Mini App
   حالت‌ها: حکم (با برش) · سرس (بدون برش، بزرگ برنده)
            نرس (بدون برش، کوچک برنده) · تک‌نرس (آس+کوچک برنده)
   تیم‌ها: شما + ربات شمال  ←→  ربات شرق + ربات غرب
   ============================================================ */
(function () {
  "use strict";

  const SUITS = [
    { id: "s", name: "پیک", symbol: "♠", color: "black" },
    { id: "h", name: "دل", symbol: "♥", color: "red" },
    { id: "d", name: "خشت", symbol: "♦", color: "red" },
    { id: "c", name: "گشنیز", symbol: "♣", color: "black" },
  ];
  const SUIT_ORDER = Object.fromEntries(SUITS.map((s, index) => [s.id, index]));
  function sortHand(hand) {
    return [...(hand || [])].sort((a, b) =>
      (SUIT_ORDER[a.s] ?? 99) - (SUIT_ORDER[b.s] ?? 99) || b.v - a.v
    );
  }
  const RANKS = [
    { v: 14, label: "آس" }, { v: 13, label: "شاه" }, { v: 12, label: "بی‌بی" },
    { v: 11, label: "سرباز" }, { v: 10, label: "۱۰" }, { v: 9, label: "۹" },
    { v: 8, label: "۸" }, { v: 7, label: "۷" }, { v: 6, label: "۶" },
    { v: 5, label: "۵" }, { v: 4, label: "۴" }, { v: 3, label: "۳" }, { v: 2, label: "۲" },
  ];
  const GAME_TYPES = {
    hokm: { name: "حکم", desc: "با برش؛ برگ بزرگ برنده", trump: true },
    sars: { name: "سرس", desc: "بدون برش؛ برگ بزرگ برنده", trump: false },
    nares: { name: "نرس", desc: "بدون برش؛ برگ کوچک برنده", trump: false },
    tek: { name: "تک‌نرس", desc: "بدون برش؛ آس بزرگ، بعد ۲", trump: false },
  };
  const PLAYER_NAMES = ["شما", "ربات شرق", "ربات شمال", "ربات غرب"];
  const PLAYER_ICONS = ["🧑", "🤖", "🤖", "🤖"];
  // تیم‌ها: 0 و 2 (شما+شمال) در برابر 1 و 3 (شرق+غرب)
  const TEAM_OF = [0, 1, 0, 1];
  const WIN_SCORE = 7;
  const HAND_SIZE = 13;

  let S = null; // state
  let rootEl = null;
  let mounted = false;
  let timers = [];

  function $id(id) { return document.getElementById(id); }
  function rankOf(v) { return RANKS.find((r) => r.v === v) || RANKS[RANKS.length - 1]; }
  function suitOf(id) { return SUITS.find((s) => s.id === id) || SUITS[0]; }
  function cardKey(card) { return card.s + ":" + card.v; }
  function shuffle(arr) {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  }
  function makeDeck() {
    const deck = [];
    for (const s of SUITS) for (const r of RANKS) deck.push({ s: s.id, v: r.v });
    return shuffle(deck);
  }
  function teammate(p) { return p === 0 ? 2 : p === 2 ? 0 : p === 1 ? 3 : 1; }
  function opponentTeam(p) { return TEAM_OF[p] === 0 ? 1 : 0; }

  // ===== ارزش برگ در هر نوع بازی =====
  function trickValue(card, ledSuit, gameType) {
    if (gameType === "hokm") {
      const base = card.v;
      return card.s === S.trumpSuit ? base + 100 : base;
    }
    // بدون برش: برگ غیر از خال زمینه بی‌ارزش است
    if (card.s !== ledSuit) return 0;
    if (gameType === "sars") return card.v;
    if (gameType === "nares") return 15 - card.v; // ۲ بالاترین، آس پایین‌ترین
    if (gameType === "tek") return card.v === 14 ? 13 : 14 - card.v; // آس بالا (۱۳)، بعد ۲ (۱۲)، شاه پایین (۱)
    return card.v;
  }

  // ===== ساخت دست =====
  function deal() {
    const deck = makeDeck();
    S.hands = [[], [], [], []];
    // پخش کارت به سبک ۵-۴-۴ (ابتدا ۵ تا به حاکم، بعد ۴ تا به بقیه)
    let idx = 0;
    // دور اول: ۵ کارت به هر نفر
    for (let round = 0; round < 5; round++) {
      for (let p = 0; p < 4; p++) {
        S.hands[p].push(deck[idx++]);
      }
    }
    // دور دوم و سوم: ۴ کارت به هر نفر
    for (let round = 0; round < 4; round++) {
      for (let p = 0; p < 4; p++) {
        S.hands[p].push(deck[idx++]);
      }
    }
    for (let round = 0; round < 4; round++) {
      for (let p = 0; p < 4; p++) {
        S.hands[p].push(deck[idx++]);
      }
    }
    for (let p = 0; p < 4; p++) S.hands[p] = sortHand(S.hands[p]);
  }

  // ===== فاز حکم‌گیری =====
  function bidStrength(player) {
    const hand = S.hands[player];
    const perSuit = {};
    for (const c of hand) {
      perSuit[c.s] = perSuit[c.s] || [];
      perSuit[c.s].push(c);
    }
    let best = { suit: null, score: 0, count: 0, honors: 0 };
    for (const s of SUITS) {
      const cards = perSuit[s.id] || [];
      const honors = cards.filter((c) => c.v >= 11).length;
      const count = cards.length;
      const score = count * 2 + honors;
      if (score > best.score) best = { suit: s.id, score, count, honors };
    }
    return best;
  }

  function botBid(player) {
    const str = bidStrength(player);
    const diff = S.difficulty;
    if (diff === "easy") {
      // ربات‌های آسان کم‌تر حکم می‌گیرند
      return str.count >= 4 ? { call: true, ...str } : { call: Math.random() < 0.15, ...str };
    }
    if (diff === "medium") return { call: str.count >= 3 && str.score >= 7, ...str };
    return { call: str.count >= 3 && str.score >= 6, ...str };
  }

  function startBidding() {
    S.phase = "bid";
    S.bidIndex = 0;
    S.bidOrder = [(S.dealer + 1) % 4, (S.dealer + 2) % 4, (S.dealer + 3) % 4, S.dealer];
    log("🎴 <b>حکم‌گیری شروع شد</b> — هر کس ۵ برگ دیده و می‌تونه حکم بگیره یا پاس بده.");
    nextBid();
  }

  function nextBid() {
    if (S.bidIndex >= S.bidOrder.length) {
      log("😴 همه پاس دادن؛ دوباره پاس می‌دیم...");
      S.rounds = (S.rounds || 0) + 1;
      if (S.rounds > 4) {
        // حداکثر ۴ پاس مجدد؛ بعدش ربات با بیشترین قدرت حکم می‌گیره
        const best = [0, 1, 2, 3].map((p) => ({ p, s: bidStrength(p) })).sort((a, b) => b.s.score - a.s.score)[0];
        S.caller = best.p;
        botPickGameType();
        return;
      }
      deal();
      S.bidIndex = 0;
      nextBid();
      return;
    }
    const p = S.bidOrder[S.bidIndex];
    if (p === 0) {
      render();
      // کاربر: نمایش دکمه‌های حکم/پاس
      showBidPrompt();
    } else {
      const b = botBid(p);
      if (b.call) {
        S.caller = p;
        log(`🗣 <b>${PLAYER_NAMES[p]}</b> حکم می‌گیره! (${b.count} برگ ${suitOf(b.suit).name})`);
        botPickGameType();
      } else {
        log(`${PLAYER_ICONS[p]} <b>${PLAYER_NAMES[p]}</b> پاس کرد.`);
        S.bidIndex++;
        setTimeout(() => nextBid(), 700);
      }
    }
  }

  function botPickGameType() {
    const p = S.caller;
    const str = bidStrength(p);
    // ربات‌ها: معمولاً حکم معمولی؛ گاهی سرس/نرس
    const roll = Math.random();
    if (roll < 0.12) {
      S.gameType = "nares";
      S.trumpSuit = null;
      log(`🎯 <b>${PLAYER_NAMES[p]}</b> نوع بازی: <b>نرس</b> (کوچک برنده)`);
    } else if (roll < 0.22) {
      S.gameType = "sars";
      S.trumpSuit = null;
      log(`🎯 <b>${PLAYER_NAMES[p]}</b> نوع بازی: <b>سرس</b> (بدون برش)`);
    } else {
      S.gameType = "hokm";
      S.trumpSuit = str.suit || SUITS[0].id;
      log(`🎯 <b>${PLAYER_NAMES[p]}</b> نوع بازی: <b>حکم ${suitOf(S.trumpSuit).name}</b>`);
    }
    afterGameTypeChosen();
  }

  function afterGameTypeChosen() {
    S.phase = "play";
    S.roundTrick = 0;
    S.teamScores = [0, 0];
    S.tricksTaken = [0, 0];
    S.trick = [];
    S.trickLeader = null;
    S.playedAll = new Set();
    log(`📦 بقیه برگ‌ها پخش شد؛ هر کس ${HAND_SIZE} برگ داره.`);
    log(`🏁 تیم اولی که به <b>${WIN_SCORE} دست</b> برسه برنده‌ست!`);
    // قانون حکم: خودِ حاکم دست اول را شروع می‌کند؛ سپس راست حاکم، یارش، چپ حاکم.
    const firstLeader = S.caller;
    log(`🔊 شروع دست اول با حاکم <b>${PLAYER_NAMES[firstLeader]}</b>`);
    startTrick(firstLeader);
  }

  // ===== پخش دست =====
  function startTrick(leader) {
    S.trick = [];
    S.trickLeader = leader;
    S.turn = leader;
    S.ledSuit = null;
    log(`— دست جدید؛ <b>${PLAYER_NAMES[leader]}</b> شروع می‌کنه —`);
    render();
    playTurn();
  }

  function playTurn() {
    if (S.phase !== "play") return;
    const p = S.turn;
    if (p === 0) {
      render();
      return; // منتظر کلیک کاربر
    }
    const card = aiChoose(p);
    setTimeout(() => playCard(p, card), 750);
  }

  function legalMoves(p) {
    if (!S.ledSuit) return S.hands[p].slice();
    const suitCards = S.hands[p].filter((c) => c.s === S.ledSuit);
    return suitCards.length ? suitCards : S.hands[p].slice();
  }

  function playCard(p, card) {
    if (S.phase !== "play") return;
    const idx = S.hands[p].findIndex((c) => cardKey(c) === cardKey(card));
    if (idx < 0) return;
    S.hands[p].splice(idx, 1);
    S.trick.push({ p, card });
    S.playedAll.add(cardKey(card));
    if (S.ledSuit === null) S.ledSuit = card.s;
    const who = p === 0 ? "شما" : PLAYER_NAMES[p];
    log(`${PLAYER_ICONS[p]} <b>${who}</b>: ${rankOf(card.v).label} ${suitOf(card.s).symbol}`);
    render();
    if (S.trick.length === 4) {
      setTimeout(() => finishTrick(), 800);
      return;
    }
    S.turn = (S.turn + 1) % 4;
    playTurn();
  }

  function trickWinnerIndex() {
    let bestIdx = 0;
    let bestVal = -1;
    for (let i = 0; i < S.trick.length; i++) {
      const v = trickValue(S.trick[i].card, S.ledSuit, S.gameType);
      if (v > bestVal) {
        bestVal = v;
        bestIdx = i;
      }
    }
    return bestIdx;
  }

  function finishTrick() {
    if (S.phase !== "play") return;
    const idx = trickWinnerIndex();
    const winner = S.trick[idx].p;
    const team = TEAM_OF[winner];
    S.tricksTaken[team]++;
    S.teamScores[team] = S.tricksTaken[team];
    const winName = winner === 0 ? "شما" : PLAYER_NAMES[winner];
    log(`🏆 <b>${winName}</b> دست رو برد! (تیم ${team === 0 ? "شما 🤝 شمال" : "شرق 🤝 غرب"}: ${S.teamScores[0]} - ${S.teamScores[1]})`, "win");
    S.trick = [];
    S.ledSuit = null;
    render();
    // بام: ۱۳ دست پشت سر هم
    const totalTricks = S.tricksTaken[0] + S.tricksTaken[1];
    if (totalTricks === 13) {
      const bamTeam = S.tricksTaken[0] === 13 ? 0 : S.tricksTaken[1] === 13 ? 1 : null;
      if (bamTeam !== null) {
        finishGame(bamTeam, true);
        return;
      }
    }
    if (S.teamScores[0] >= WIN_SCORE || S.teamScores[1] >= WIN_SCORE) {
      finishGame(S.teamScores[0] >= WIN_SCORE ? 0 : 1, false);
      return;
    }
    startTrick(winner);
  }

  function finishGame(winningTeam, isBam) {
    S.phase = "done";
    const youWon = winningTeam === 0;
    const oppScore = winningTeam === 0 ? S.teamScores[1] : S.teamScores[0];
    const isKoot = oppScore === 0;
    log(isBam
      ? `👑 <b>بام!</b> تیم ${winningTeam === 0 ? "شما" : "حریف"} هر ۱۳ دست رو برد!`
      : `🏁 تیم ${winningTeam === 0 ? "شما 🤝 شمال" : "شرق 🤝 غرب"} به ${WIN_SCORE} دست رسید!`, "win");
    render();
    showResult(youWon, isBam, isKoot);
  }

  // ===== هوش مصنوعی =====
  function aiChoose(p) {
    const legal = legalMoves(p);
    const diff = S.difficulty;
    if (diff === "easy") return legal[Math.floor(Math.random() * legal.length)];

    // کارت‌های بازی‌شده برای شمارش
    const remaining = { s: 13, h: 13, d: 13, c: 13 };
    for (const key of S.playedAll) {
      const suit = key.split(":")[0];
      remaining[suit]--;
    }

    const isFollowing = S.ledSuit !== null;
    if (!isFollowing) return aiLead(p, diff, remaining);

    const suitCards = S.hands[p].filter((c) => c.s === S.ledSuit);
    if (suitCards.length) return aiFollow(p, suitCards, diff);
    return aiVoid(p, diff);
  }

  function aiLead(p, diff, remaining) {
    const hand = S.hands[p];
    const counts = {};
    for (const c of hand) counts[c.s] = (counts[c.s] || 0) + 1;
    // ترجیح: خالی‌کردن خال‌های کم‌کارت؛ رهبری با برگ پایین از خال بلند
    const sortedSuits = SUITS.map((s) => s.id).sort((a, b) => (counts[a] || 0) - (counts[b] || 0));
    for (const s of sortedSuits) {
      const cards = hand.filter((c) => c.s === s);
      if (!cards.length) continue;
      const low = [...cards].sort((a, b) => a.v - b.v)[0];
      if (diff === "hard") {
        // اگر آس تنها و بقیه‌ی خال رفته → رهبری کن
        if (cards.length === 1 && cards[0].v === 14 && remaining[s] <= 2) return cards[0];
      }
      return low;
    }
    return hand[hand.length - 1];
  }

  function aiFollow(p, suitCards, diff) {
    // آیا الان دست رو می‌بریم؟
    let currentBest = -1;
    let currentBestIsTrump = false;
    for (const t of S.trick) {
      const v = trickValue(t.card, S.ledSuit, S.gameType);
      if (v > currentBest) { currentBest = v; currentBestIsTrump = t.card.s === S.trumpSuit && S.gameType === "hokm"; }
    }
    const sorted = [...suitCards].sort((a, b) => a.v - b.v);
    const winners = sorted.filter((c) => trickValue(c, S.ledSuit, S.gameType) > currentBest);
    if (winners.length) {
      // کم‌ارزش‌ترین برنده (اقتصادی)
      return winners[0];
    }
    // نمی‌تونیم ببریم → کم‌ارزش‌ترین رو قربانی کن (ولی اگه هم‌تیمی برنده‌ست، بالاترین رو ننداز)
    const partnerWinning = S.trick.length > 0 && TEAM_OF[S.trick[S.trick.length - 1].p] === TEAM_OF[p] && false;
    return sorted[0];
  }

  function aiVoid(p, diff) {
    const hand = S.hands[p];
    const hasTrump = S.gameType === "hokm" && S.trumpSuit && hand.some((c) => c.s === S.trumpSuit);
    // آیا حریف در حال بردن با برگ بالاست؟
    let currentBest = -1;
    for (const t of S.trick) {
      const v = trickValue(t.card, S.ledSuit, S.gameType);
      if (v > currentBest) currentBest = v;
    }
    const trickSoFar = S.trick;
    const oppLeadingStrong = trickSoFar.length >= 2 && trickSoFar.some((t) => TEAM_OF[t.p] === TEAM_OF[p] && trickValue(t.card, S.ledSuit, S.gameType) >= 11);
    const partnerInTrick = trickSoFar.some((t) => TEAM_OF[t.p] === TEAM_OF[p]);
    if (hasTrump && diff === "hard") {
      // برش فقط وقتی ارزشش رو داره: حریف با برگ بالا می‌بره و هم‌تیمی نداریم که ببره
      const oppWinning = !partnerInTrick && trickSoFar.some((t) => TEAM_OF[t.p] !== TEAM_OF[p] && trickValue(t.card, S.ledSuit, S.gameType) > 10);
      if (oppWinning || trickSoFar.length === 3) {
        const trumps = hand.filter((c) => c.s === S.trumpSuit).sort((a, b) => a.v - b.v);
        if (trumps.length) return trumps[0];
      }
    }
    // دور ریختن کم‌ارزش‌ترین
    return [...hand].sort((a, b) => a.v - b.v)[0];
  }

  // ===== رندر =====
  function cardHTML(card, opts) {
    const s = suitOf(card.s);
    const r = rankOf(card.v);
    const cls = ["hokm-card", s.color, opts?.playable ? "playable" : "", opts?.disabled ? "disabled" : "", opts?.selected ? "selected" : "", opts?.suitBreak ? "suit-break" : ""].filter(Boolean).join(" ");
    // چهره کارت‌ها (شاه/بی‌بی/سرباز)
    const faceMap = {14: "🂡", 13: "🤴", 12: "👸", 11: "🃏"};
    const isFace = card.v >= 11 && card.v <= 13;
    const isAce = card.v === 14;
    const center = isFace ? `<span class="hokm-face">${faceMap[card.v] || s.symbol}</span>` :
                   isAce ? `<span class="hokm-center" style="font-size:28px">${s.symbol}</span>` :
                   `<span class="hokm-center">${s.symbol}</span>`;
    const cornerContent = `${r.label}<br>${s.symbol}`;
    return `<div class="${cls}" data-key="${cardKey(card)}">` +
      `<span class="hokm-corner hokm-corner-top">${cornerContent}</span>` +
      center +
      `<span class="hokm-corner hokm-corner-bottom">${cornerContent}</span></div>`;
  }
  function cardBackHTML(leading) {
    return `<div class="hokm-card ${leading ? "leading" : ""}"></div>`;
  }

  function render() {
    if (!rootEl) return;
    if (!S) return;
    const gameType = GAME_TYPES[S.gameType] || GAME_TYPES.hokm;
    const youTeam = TEAM_OF[0] === 0 ? 0 : 1;
    const oppTeam = 1 - youTeam;
    const trumpText = S.gameType === "hokm" && S.trumpSuit ? `حکم: ${suitOf(S.trumpSuit).symbol} ${suitOf(S.trumpSuit).name}` : `نوع: ${gameType.name}`;
    const turn = S.turn;
    const phase = S.phase;

    let html = "";
    html += `<div class="hokm-table">`;
    // امتیاز تیم‌ها
    html += `<div class="hokm-teamline">`;
    html += `<div class="hokm-team you"><small>تیم شما 🤝 شمال</small>${S.teamScores ? S.teamScores[youTeam] : 0} دست</div>`;
    html += `<div class="hokm-team opp"><small>تیم شرق 🤝 غرب</small>${S.teamScores ? S.teamScores[oppTeam] : 0} دست</div>`;
    html += `</div>`;

    // مرکز
    html += `<div class="hokm-center">`;
    // سمت چپ: ربات غرب (3)
    html += `<div class="hokm-side">`;
    html += `<span class="hokm-player-name ${turn === 3 ? "active" : ""}">🤖 غرب</span>`;
    if (phase === "play" && S.hands) {
      html += `<div class="hokm-bot-cards ${S.trickLeader === 3 ? "leading" : ""}">${S.hands[3].map(() => cardBackHTML()).join("")}</div>`;
    }
    html += `</div>`;
    // وسط: کارت‌های بازی‌شده + ترامپ
    html += `<div class="hokm-played">`;
    const slotOrder = S.trickLeader !== null ? [S.trickLeader, (S.trickLeader + 1) % 4, (S.trickLeader + 2) % 4, (S.trickLeader + 3) % 4] : [0, 1, 2, 3];
    for (let i = 0; i < 4; i++) {
      const found = S.trick.find((t) => t.p === slotOrder[i]);
      html += `<div class="hokm-played-slot ${found ? "" : "empty"}">${found ? cardHTML(found.card) : "·"}</div>`;
    }
    html += `</div>`;
    // سمت راست: ربات شرق (1)
    html += `<div class="hokm-side">`;
    html += `<span class="hokm-player-name ${turn === 1 ? "active" : ""}">🤖 شرق</span>`;
    if (phase === "play" && S.hands) {
      html += `<div class="hokm-bot-cards ${S.trickLeader === 1 ? "leading" : ""}">${S.hands[1].map(() => cardBackHTML()).join("")}</div>`;
    }
    html += `</div>`;
    html += `</div>`;

    // بالا: ربات شمال (2) هم‌تیمی
    html += `<div class="hokm-side">`;
    html += `<span class="hokm-player-name ${turn === 2 ? "active" : ""}">🤖 شمال (هم‌تیمی تو)</span>`;
    if (phase === "play" && S.hands) {
      html += `<div class="hokm-bot-cards ${S.trickLeader === 2 ? "leading" : ""}">${S.hands[2].map(() => cardBackHTML()).join("")}</div>`;
    }
    html += `</div>`;

    // ترامپ / نوع بازی
    html += `<div class="hokm-trump-box"><span class="hokm-trump-chip">${trumpText}</span></div>`;

    // دست کاربر
    if (phase === "play" && S.hands && S.hands[0]) {
      const legal = S.turn === 0 ? legalMoves(0) : [];
      const legalKeys = new Set(legal.map(cardKey));
      html += `<div class="hokm-hand">`;
      html += sortHand(S.hands[0]).map((c, index, hand) => cardHTML(c, {
        playable: S.turn === 0 && legalKeys.has(cardKey(c)),
        suitBreak: index > 0 && hand[index - 1].s !== c.s,
      })).join("");
      html += `</div>`;
    }
    html += `</div>`;

    // دکمه‌ها
    html += `<div class="hokm-actions">`;
    if (phase === "play" && S.turn === 0) {
      html += `<button class="hokm-btn" id="hokmPlayBtn">🎯 بازی برگ</button>`;
      html += `<button class="hokm-btn ghost" id="hokmCancelBtn">انصراف</button>`;
    }
    if (phase === "done") {
      html += `<button class="hokm-btn gold" id="hokmAgainBtn">🔄 بازی دوباره</button>`;
      html += `<button class="hokm-btn ghost" data-go="games">خروج از میز</button>`;
    }
    html += `</div>`;

    // وضعیت
    html += `<div class="hokm-dash">`;
    html += `<div class="hokm-dash-item"><b>${S.trick ? S.trick.length : 0}/4</b><span>برگ این دست</span></div>`;
    html += `<div class="hokm-dash-item"><b>${S.tricksTaken ? S.tricksTaken[youTeam] : 0}</b><span>دست‌های شما</span></div>`;
    html += `<div class="hokm-dash-item"><b>${phase === "bid" ? "در حال حکم‌گیری" : phase === "done" ? "پایان" : turn === 0 ? "نوبت شما" : "در حال بازی…"}</b><span>وضعیت</span></div>`;
    html += `</div>`;

    // لاگ
    html += `<div class="hokm-log" id="hokmLog">${S.logs.map((l) => l).join("")}</div>`;

    rootEl.innerHTML = html;

    // رویدادها
    if (phase === "play" && S.turn === 0) {
      const playBtn = $id("hokmPlayBtn");
      const cancelBtn = $id("hokmCancelBtn");
      let selected = null;
      rootEl.querySelectorAll(".hokm-hand .hokm-card.playable").forEach((el) => {
        el.addEventListener("click", () => {
          if (selected === el.dataset.key) {
            el.classList.remove("selected");
            selected = null;
          } else {
            rootEl.querySelectorAll(".hokm-hand .hokm-card").forEach((c) => c.classList.remove("selected"));
            el.classList.add("selected");
            selected = el.dataset.key;
          }
        });
      });
      playBtn.addEventListener("click", () => {
        if (!selected) {
          flashLog("⚠️ اول یک برگ انتخاب کن!");
          return;
        }
        const card = S.hands[0].find((c) => cardKey(c) === selected);
        if (card) playCard(0, card);
      });
      cancelBtn.addEventListener("click", () => {
        rootEl.querySelectorAll(".hokm-hand .hokm-card").forEach((c) => c.classList.remove("selected"));
      });
    }
    if (phase === "done") {
      $id("hokmAgainBtn")?.addEventListener("click", () => showSetup());
    }
    const logEl = $id("hokmLog");
    if (logEl) logEl.scrollTop = logEl.scrollHeight;
  }

  function flashLog(msg) {
    S.logs.push(`<i style="color:#ffd54f">${msg}</i>`);
    if (S.logs.length > 60) S.logs = S.logs.slice(-60);
    render();
  }

  function log(msg, cls) {
    S.logs.push(`<div class="${cls || ""}">${msg}</div>`);
    if (S.logs.length > 60) S.logs = S.logs.slice(-60);
  }

  // ===== رابط کاربری حکم‌گیری =====
  function showBidPrompt() {
    const overlay = document.createElement("div");
    overlay.className = "hokm-modal-backdrop";
    overlay.id = "hokmBidModal";
    overlay.innerHTML = `
      <div class="hokm-modal">
        <h3>🎴 نوبت شما — حکم می‌گیری؟</h3>
        <p>۵ برگ اولت رو دیدی. اگه حکم بگیری، نوع بازی و خال حکم رو انتخاب می‌کنی.</p>
        <div class="hokm-actions">
          <button class="hokm-btn gold" id="bidCallBtn">🔥 حکم می‌گیرم</button>
          <button class="hokm-btn ghost" id="bidPassBtn">پاس</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    $id("bidCallBtn").addEventListener("click", () => {
      S.caller = 0;
      overlay.remove();
      showGameTypePick();
    });
    $id("bidPassBtn").addEventListener("click", () => {
      overlay.remove();
      log("🧑 <b>شما</b> پاس کردید.");
      S.bidIndex++;
      nextBid();
    });
  }

  function showGameTypePick() {
    const overlay = document.createElement("div");
    overlay.className = "hokm-modal-backdrop";
    overlay.id = "hokmTypeModal";
    let html = `<div class="hokm-modal"><h3>🎯 نوع بازی رو انتخاب کن</h3><p>حاکم تویی! قانون بازی رو تعیین کن:</p><div class="hokm-game-type-grid">`;
    for (const [id, t] of Object.entries(GAME_TYPES)) {
      html += `<button class="hokm-type-btn" data-type="${id}">${id === "hokm" ? "🃏" : id === "sars" ? "👑" : id === "nares" ? "🐜" : "🔥"} ${t.name}<small>${t.desc}</small></button>`;
    }
    html += `</div></div>`;
    overlay.innerHTML = html;
    document.body.appendChild(overlay);
    overlay.querySelectorAll(".hokm-type-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        S.gameType = btn.dataset.type;
        overlay.remove();
        if (S.gameType === "hokm") {
          showSuitPick();
        } else {
          S.trumpSuit = null;
          log(`🎯 <b>شما</b> نوع بازی: <b>${GAME_TYPES[S.gameType].name}</b>`);
          afterGameTypeChosen();
        }
      });
    });
  }

  function showSuitPick() {
    const overlay = document.createElement("div");
    overlay.className = "hokm-modal-backdrop";
    overlay.id = "hokmSuitModal";
    let html = `<div class="hokm-modal"><h3>🃏 خال حکم رو انتخاب کن</h3><p>برگ‌های این خال، برش می‌شن:</p><div class="hokm-suit-grid">`;
    for (const s of SUITS) {
      html += `<button class="hokm-suit-btn ${s.color}" data-suit="${s.id}"><span class="hokm-suit-big">${s.symbol}</span>${s.name}</button>`;
    }
    html += `</div></div>`;
    overlay.innerHTML = html;
    document.body.appendChild(overlay);
    overlay.querySelectorAll(".hokm-suit-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        S.trumpSuit = btn.dataset.suit;
        overlay.remove();
        log(`🎯 <b>شما</b> نوع بازی: <b>حکم ${suitOf(S.trumpSuit).name}</b>`);
        afterGameTypeChosen();
      });
    });
  }

  function showResult(youWon, isBam, isKoot) {
    const overlay = document.createElement("div");
    overlay.className = "hokm-modal-backdrop";
    overlay.id = "hokmResultModal";
    const title = youWon ? (isBam ? "👑 بام کردی!" : "🏆 بردید!") : (isBam ? "💔 حریف بام کرد" : "😢 باختید");
    const sub = isKoot ? (youWon ? "حریف کوت شد — ۰ به ۷! 🔥" : "شما کوت شدید...") : `${S.teamScores[0]} به ${S.teamScores[1]}`;
    overlay.innerHTML = `
      <div class="hokm-modal" style="text-align:center">
        <h3 style="font-size:24px">${title}</h3>
        <p>${sub}</p>
        <div class="hokm-actions">
          <button class="hokm-btn gold" id="resultAgainBtn">🔄 بازی دوباره</button>
          <button class="hokm-btn ghost" data-go="games">خروج</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    $id("resultAgainBtn").addEventListener("click", () => { overlay.remove(); showSetup(); });
    overlay.querySelector('[data-go="games"]')?.addEventListener("click", () => {
      overlay.remove();
      window.location.hash = "#games";
      document.querySelector('[data-nav="games"]')?.click();
    });
  }

  function clearOverlays() {
    ["hokmBidModal", "hokmTypeModal", "hokmSuitModal", "hokmResultModal"].forEach((id) => {
      document.getElementById(id)?.remove();
    });
  }

  // ===== ابزار حالت آنلاین =====
  let online = null; // {room, seat, pollTimer, yourName}
  let onlineBidPending = false;

  function apiInitData() {
    try {
      return (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData) || "";
    } catch (_) { return ""; }
  }
  async function hokmFetch(path, options = {}) {
    const headers = {
      ...(options.headers || {}),
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": apiInitData(),
    };
    const response = await fetch(path, { ...options, headers });
    let data = null;
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) {
      const msg = (data && (data.message || data.reason)) || `HTTP ${response.status}`;
      throw new Error(msg);
    }
    return data;
  }
  function getStartParam() {
    try {
      const sp = window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initDataUnsafe && window.Telegram.WebApp.initDataUnsafe.start_param;
      if (sp && sp.startsWith("hokm_")) return sp.slice(5);
    } catch (_) {}
    const q = new URLSearchParams(location.search);
    return q.get("room") || "";
  }
  function shortRoom(room) { return room ? room.slice(0, 6) + "…" : ""; }

  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch (_) { return false; }
  }

  function showOnlineHome() {
    clearOverlays();
    online = null;
    rootEl.innerHTML = `
      <div class="hokm-intro">
        <div style="font-size:40px">🌐</div>
        <h2>حکم آنلاین</h2>
        <p>یک اتاق بساز و لینکش رو برای رفیقت بفرست؛ دو نفره با دو ربات بازی کنید. هر نفر دست خودش رو داره و هم‌تیمی AI داری.</p>
        <div class="hokm-actions">
          <button class="hokm-btn gold" id="onlineCreateBtn">🏠 ساخت اتاق جدید</button>
          <button class="hokm-btn ghost" id="onlineBackBtn">بازگشت</button>
        </div>
      </div>`;
    $id("onlineCreateBtn").addEventListener("click", async () => {
      try {
        const data = await hokmFetch("/api/hokm", { method: "POST", body: JSON.stringify({ action: "create", difficulty: "medium" }) });
        if (!data.ok || !data.room) throw new Error("اتاق ساخته نشد");
        online = { room: data.room, seat: data.seat, isHost: true };
        showOnlineWaiting();
      } catch (e) { flashOnlineError(e.message); }
    });
    $id("onlineBackBtn").addEventListener("click", () => showSetup());
  }

  function flashOnlineError(msg) {
    if (!rootEl) return;
    const div = document.createElement("div");
    div.className = "hokm-log";
    div.innerHTML = `<b style="color:#ff6b6b">❌ ${msg.replace(/</g, "&lt;")}</b>`;
    rootEl.appendChild(div);
  }

  async function showOnlineWaiting() {
    if (!online) return;
    const link = `https://t.me/${window.SUPPORT_USERNAME || "Ajorparehbot"}/app?startapp=hokm_${online.room}`;
    rootEl.innerHTML = `
      <div class="hokm-intro">
        <div style="font-size:44px">🃏</div>
        <h2>اتاق ساخته شد!</h2>
        <p>این لینک رو برای رفیقت بفرست تا به بازی بپیونده:<br><code style="direction:ltr;display:block;font-size:11px;word-break:break-all;background:rgba(255,255,255,0.06);padding:10px;border-radius:10px;margin:8px 0">${link}</code></p>
        <div class="hokm-actions">
          <button class="hokm-btn gold" id="copyLinkBtn">📋 کپی لینک دعوت</button>
          <button class="hokm-btn" id="shareLinkBtn">📤 اشتراک‌گذاری</button>
        </div>
        <p style="color:var(--muted,#8a93a6);font-size:12px">منتظر نفر دوم… ⏳</p>
      </div>`;
    $id("copyLinkBtn").addEventListener("click", async () => {
      const ok = await copyText(link);
      flashToast(ok ? "لینک کپی شد ✅" : "کپی نشد؛ دستی کپی کن");
    });
    $id("shareLinkBtn").addEventListener("click", async () => {
      try {
        if (navigator.share) await navigator.share({ title: "بیا حکم بازی کنیم!", text: "به اتاق حکم من بپیوند:", url: link });
        else { const ok = await copyText(link); flashToast(ok ? "لینک کپی شد ✅" : "کپی نشد"); }
      } catch (_) {}
    });
    startOnlinePolling();
  }

  function startOnlinePolling() {
    stopOnlinePolling();
    online.pollTimer = setInterval(async () => {
      if (!online || !online.room) return;
      try {
        const data = await hokmFetch(`/api/hokm/state?room=${encodeURIComponent(online.room)}`);
        if (data.phase === "waiting") return; // هنوز نفر دوم نیست
        stopOnlinePolling();
        renderOnlineState(data);
      } catch (e) {
        // اتاق هنوز ساخته نشده یا خطای auth — در حالت waiting خطای not found معنی داره (صبر کن)
        if (String(e.message).includes("not found") || String(e.message).includes("not in room")) {
          // صبر کن
        }
      }
    }, 2000);
  }
  function stopOnlinePolling() {
    if (online && online.pollTimer) { clearInterval(online.pollTimer); online.pollTimer = null; }
  }

  // ---- رندر بازی آنلاین از state سرور ----
  function renderOnlineState(st) {
    online.seat = st.your_seat;
    const seatNames = st.seat_names || {};
    const nameOf = (s) => seatNames[s] || (s === st.your_seat ? "شما" : "ربات");
    const teammate = st.teammate;
    const gameTypeName = st.game_type_name || "";
    const trumpText = st.trump_suit ? `حکم: ${SUITS.find((x) => x.id === st.trump_suit)?.symbol || ""} ${st.trump_name || ""}` : `نوع: ${gameTypeName}`;

    let html = `<div class="hokm-table">`;
    html += `<div class="hokm-teamline">`;
    html += `<div class="hokm-team you"><small>تیم شما 🤝 ${nameOf(teammate)}</small>${st.tricks_taken[0]} دست</div>`;
    html += `<div class="hokm-team opp"><small>تیم حریف</small>${st.tricks_taken[1]} دست</div>`;
    html += `</div>`;

    // محل رندر کارت‌های روی میز (صرفاً نمایشی)
    html += `<div class="hokm-center"><div class="hokm-side"></div><div class="hokm-played">`;
    const played = st.trick || [];
    const slotKeys = ["s0", "s1", "s2", "s3"];
    for (const sk of slotKeys) {
      const found = played.find((t) => String(t.seat) === sk.slice(1));
      html += `<div class="hokm-played-slot ${found ? "" : "empty"}">${found ? cardHTML(found.card) : "·"}</div>`;
    }
    html += `</div><div class="hokm-side"></div></div>`;

    html += `<div class="hokm-trump-box"><span class="hokm-trump-chip">${trumpText}</span></div>`;

    // دست من
    if (st.phase === "play" && Array.isArray(st.hand)) {
      const isMyTurn = st.turn === st.your_seat;
      const legalKeys = new Set();
      if (isMyTurn) {
        if (st.led_suit) {
          st.hand.filter((c) => c.s === st.led_suit).forEach((c) => legalKeys.add(c.s + ":" + c.v));
          if (!st.hand.some((c) => c.s === st.led_suit)) st.hand.forEach((c) => legalKeys.add(c.s + ":" + c.v));
        } else {
          st.hand.forEach((c) => legalKeys.add(c.s + ":" + c.v));
        }
      }
      html += `<div class="hokm-hand">`;
      html += sortHand(st.hand).map((c, index, hand) => cardHTML(c, {
        playable: isMyTurn && legalKeys.has(c.s + ":" + c.v),
        suitBreak: index > 0 && hand[index - 1].s !== c.s,
      })).join("");
      html += `</div>`;
    }

    html += `</div>`;

    // وضعیت و دکمه‌ها
    html += `<div class="hokm-dash">`;
    html += `<div class="hokm-dash-item"><b>${(st.trick || []).length}/4</b><span>برگ این دست</span></div>`;
    html += `<div class="hokm-dash-item"><b>${st.tricks_taken[0]}</b><span>دست‌های شما</span></div>`;
    html += `<div class="hokm-dash-item"><b>${st.phase === "play" && st.turn === st.your_seat ? "نوبت شما" : st.phase === "done" ? "پایان" : "در حال بازی…"}</b><span>وضعیت</span></div>`;
    html += `</div>`;

    // دکمه‌های اکشن
    html += `<div class="hokm-actions">`;
    if (st.phase === "play" && st.turn === st.your_seat) {
      html += `<button class="hokm-btn" id="onlinePlayBtn">🎯 بازی برگ</button>`;
    }
    if (st.phase === "done") {
      html += `<button class="hokm-btn gold" id="onlineAgainBtn">🔄 بازی دوباره</button>`;
      html += `<button class="hokm-btn ghost" data-go="games">خروج</button>`;
    }
    html += `</div>`;

    // لاگ
    html += `<div class="hokm-log">${(st.log || []).map((l) => l).join("")}</div>`;
    rootEl.innerHTML = html;

    // رویدادها
    if (st.phase === "play" && st.turn === st.your_seat) {
      let selected = null;
      rootEl.querySelectorAll(".hokm-hand .hokm-card.playable").forEach((el) => {
        el.addEventListener("click", () => {
          if (selected === el.dataset.key) { el.classList.remove("selected"); selected = null; }
          else { rootEl.querySelectorAll(".hokm-hand .hokm-card").forEach((c) => c.classList.remove("selected")); el.classList.add("selected"); selected = el.dataset.key; }
        });
      });
      $id("onlinePlayBtn")?.addEventListener("click", async () => {
        if (!selected) { flashOnlineError("⚠️ اول یک برگ انتخاب کن!"); return; }
        const [s, v] = selected.split(":");
        try {
          const data = await hokmFetch("/api/hokm", { method: "POST", body: JSON.stringify({ action: "move", room: online.room, card: { s, v: Number(v) } }) });
          renderOnlineState(data);
        } catch (e) { flashOnlineError(e.message); }
      });
    }
    if (st.phase === "done") {
      $id("onlineAgainBtn")?.addEventListener("click", () => showOnlineHome());
      rootEl.querySelector('[data-go="games"]')?.addEventListener("click", () => { window.location.hash = "#games"; document.querySelector('[data-nav="games"]')?.click(); });
    }
  }

  // ---- فاز حکم‌گیری آنلاین ----
  function showOnlineBid(st) {
    clearOverlays();
    rootEl.innerHTML = `
      <div class="hokm-intro">
        <div style="font-size:40px">🎴</div>
        <h2>حکم می‌گیری؟</h2>
        <p>۵ برگ اولت رو دیدی؛ تصمیم بگیر:</p>
        <div class="hokm-actions">
          <button class="hokm-btn gold" id="obidCall">🔥 حکم می‌گیرم</button>
          <button class="hokm-btn ghost" id="obidPass">پاس</button>
        </div>
      </div>`;
    $id("obidCall").addEventListener("click", async () => {
      try {
        const data = await hokmFetch("/api/hokm", { method: "POST", body: JSON.stringify({ action: "move", room: online.room, take: true }) });
        if (data.phase === "bid_choose") showOnlineChoose(data);
        else renderOnlineState(data);
      } catch (e) { flashOnlineError(e.message); }
    });
    $id("obidPass").addEventListener("click", async () => {
      try {
        const data = await hokmFetch("/api/hokm", { method: "POST", body: JSON.stringify({ action: "move", room: online.room, take: false }) });
        renderOnlineState(data);
      } catch (e) { flashOnlineError(e.message); }
    });
  }

  function showOnlineChoose(st) {
    clearOverlays();
    let html = `<div class="hokm-intro"><div style="font-size:40px">🎯</div><h2>نوع بازی رو انتخاب کن</h2><p>حاکم تویی!</p><div class="hokm-game-type-grid">`;
    const types = { hokm: ["🃏", "حکم", "با برش"], sars: ["👑", "سرس", "بزرگ برنده"], nares: ["🐜", "نرس", "کوچک برنده"], tek: ["🔥", "تک‌نرس", "آس بعد ۲"] };
    for (const [id, t] of Object.entries(types)) {
      html += `<button class="hokm-type-btn" data-type="${id}">${t[0]} ${t[1]}<small>${t[2]}</small></button>`;
    }
    html += `</div><div id="onlineSuitPick" style="display:none" class="hokm-suit-grid">`;
    for (const s of SUITS) {
      html += `<button class="hokm-suit-btn ${s.color}" data-suit="${s.id}"><span class="hokm-suit-big">${s.symbol}</span>${s.name}</button>`;
    }
    html += `</div></div>`;
    rootEl.innerHTML = html;
    let chosenType = null;
    rootEl.querySelectorAll(".hokm-type-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        chosenType = btn.dataset.type;
        if (chosenType === "hokm") {
          document.getElementById("onlineSuitPick").style.display = "grid";
        } else {
          submitChoose(chosenType, null);
        }
      });
    });
    rootEl.querySelectorAll(".hokm-suit-btn").forEach((btn) => {
      btn.addEventListener("click", () => submitChoose("hokm", btn.dataset.suit));
    });
  }

  async function submitChoose(gameType, trump) {
    try {
      const data = await hokmFetch("/api/hokm", { method: "POST", body: JSON.stringify({ action: "move", room: online.room, game_type: gameType, trump: trump || null }) });
      renderOnlineState(data);
    } catch (e) { flashOnlineError(e.message); }
  }

  function renderBidWaiting(st) {
    const seatNames = st.seat_names || {};
    const waitingName = seatNames[st.bid_seat] || "حریف";
    rootEl.innerHTML = `
      <div class="hokm-intro">
        <div style="font-size:44px">⏳</div>
        <h2>حکم‌گیری در جریانه</h2>
        <p>منتظر تصمیم <b>${String(waitingName).replace(/</g, "&lt;")}</b> هستیم…</p>
        <div class="hokm-dash">
          <div class="hokm-dash-item"><b>${(st.trick || []).length}/4</b><span>برگ این دست</span></div>
          <div class="hokm-dash-item"><b>${st.tricks_taken[0]}</b><span>دست‌های شما</span></div>
          <div class="hokm-dash-item"><b>—</b><span>وضعیت</span></div>
        </div>
      </div>`;
  }

  function renderChooseWaiting(st) {
    const seatNames = st.seat_names || {};
    const callerName = seatNames[st.caller] || "حاکم";
    rootEl.innerHTML = `
      <div class="hokm-intro">
        <div style="font-size:44px">⏳</div>
        <h2>انتخاب نوع بازی</h2>
        <p><b>${String(callerName).replace(/</g, "&lt;")}</b> داره نوع بازی رو انتخاب می‌کنه…</p>
      </div>`;
  }

  function startOnlineGame() {
    stopOnlinePolling();
    // poll وضعیت بازی
    online.pollTimer = setInterval(async () => {
      if (!online || !online.room) return;
      try {
        const data = await hokmFetch(`/api/hokm/state?room=${encodeURIComponent(online.room)}`);
        if (data.phase === "bid") {
          if (data.bid_seat === data.your_seat) showOnlineBid(data);
          else renderBidWaiting(data);
          return;
        }
        if (data.phase === "bid_choose") {
          if (data.caller === data.your_seat) showOnlineChoose(data);
          else renderChooseWaiting(data);
          return;
        }
        renderOnlineState(data);
      } catch (_) {}
    }, 1500);
  }

  // ===== شروع / راه‌اندازی =====
  function showSetup() {
    clearOverlays();
    stopOnlinePolling();
    S = null;
    if (!rootEl) return;
    rootEl.innerHTML = `
      <div class="hokm-intro">
        <div style="font-size:40px">🎴</div>
        <h2>حکم چهارنفره</h2>
        <p>دو راه بازی: <b>محلی</b> با سه ربات، یا <b>آنلاین</b> با رفیقت (هر کدوم + یک ربات هم‌تیمی). تیم اولی که ۷ دست بگیره برنده‌ست.</p>
        <div class="hokm-actions" style="flex-direction:column;align-items:stretch;max-width:300px;margin:0 auto;gap:10px">
          <button class="hokm-btn" id="setupLocalBtn">🎮 بازی محلی (با ربات‌ها)</button>
          <button class="hokm-btn gold" id="setupOnlineBtn">🌐 بازی آنلاین با رفیق</button>
        </div>
        <div class="hokm-rules" style="margin-top:16px">
          <b>قوانین سریع:</b><br>
          • حکم: برش با خال حکم؛ بزرگ‌ترین برگ خالِ زمینه می‌بره مگر حکم.<br>
          • سرس: بدون برش؛ بزرگ‌ترین برگ می‌بره (آس بالاترین).<br>
          • نرس: بدون برش؛ کوچک‌ترین برگ می‌بره (۲ بالاترین، آس پایین‌ترین).<br>
          • تک‌نرس: بدون برش؛ آس بالاترین، بعد ۲، ۳، ... و شاه پایین‌ترین.<br>
          • اگه برگ خالِ زمینه نداری، برگ دیگه بی‌ارزشه (در سرس/نرس/تک‌نرس).<br>
          • هر دست = ۱ امتیاز؛ اول رسیدن به ۷ می‌بره. برد ۷-۰ = <b>کوت</b>.
        </div>
      </div>`;
    $id("setupLocalBtn").addEventListener("click", () => showLocalSetup());
    $id("setupOnlineBtn").addEventListener("click", () => showOnlineHome());
    const chip = $id("hokmStatusChip");
    if (chip) chip.textContent = "آماده";

    // ورود خودکار به اتاق از طریق لینک دعوت
    const roomParam = getStartParam();
    if (roomParam) {
      online = { room: roomParam, isGuest: true };
      joinOnlineRoom(roomParam);
    }
  }

  async function joinOnlineRoom(roomId) {
    try {
      const data = await hokmFetch("/api/hokm", { method: "POST", body: JSON.stringify({ action: "join", room: roomId }) });
      online.room = data.room;
      online.seat = data.your_seat;
      renderOnlineState(data);
      startOnlineGame();
    } catch (e) {
      // اتاق پر یا شروع‌شده یا نبوده
      flashOnlineError(e.message);
      online = null;
    }
  }

  function showLocalSetup() {
    clearOverlays();
    S = null;
    if (!rootEl) return;
    rootEl.innerHTML = `
      <div class="hokm-intro">
        <div style="font-size:40px">🎴</div>
        <h2>حکم محلی</h2>
        <p>با دو ربات حریف و یک ربات هم‌تیمی بازی کن.</p>
        <div class="hokm-diff-pick">
          <button class="hokm-diff-btn active" data-diff="medium">😊 آسان</button>
          <button class="hokm-diff-btn" data-diff="hard">😎 متوسط</button>
          <button class="hokm-diff-btn" data-diff="expert">🤯 سخت</button>
        </div>
        <div class="hokm-actions"><button class="hokm-btn" id="hokmStartBtn">🚀 شروع بازی</button></div>
      </div>`;
    rootEl.querySelectorAll(".hokm-diff-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        rootEl.querySelectorAll(".hokm-diff-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        S = { difficulty: btn.dataset.diff };
      });
    });
    $id("hokmStartBtn").addEventListener("click", () => {
      if (!S) S = {};
      startNewGame(S.difficulty || "medium");
    });
  }

  function startNewGame(difficulty) {
    clearOverlays();
    S = {
      difficulty: difficulty || "medium",
      dealer: Math.floor(Math.random() * 4),
      phase: "bid",
      logs: [],
      teamScores: [0, 0],
      tricksTaken: [0, 0],
      hands: [[], [], [], []],
      playedAll: new Set(),
      gameType: null,
      trumpSuit: null,
      caller: null,
      rounds: 0,
    };
    deal();
    log(`🎴 <b>بازی جدید شروع شد</b> — دیلر: ${PLAYER_NAMES[S.dealer]}`);
    log(`🎚 سختی: ${difficulty === "easy" ? "آسان" : difficulty === "hard" ? "متوسط" : "سخت"}`);
    const chip = $id("hokmStatusChip");
    if (chip) chip.textContent = "در جریان";
    startBidding();
    render();
  }

  const HokmApp = {
    mount() {
      if (mounted) return;
      mounted = true;
      rootEl = $id("hokmRoot");
      showSetup();
    },
    unmount() {
      mounted = false;
      clearOverlays();
      stopOnlinePolling();
      timers.forEach((t) => clearTimeout(t));
      timers = [];
      rootEl = null;
      S = null;
    },
    _debug: { getState: () => S },
  };

  window.HokmApp = HokmApp;
  window.__HokmTest = {
    startNewGame,
    getState: () => S,
    playCard,
    trickValue: (card, ledSuit, gt) => trickValue(card, ledSuit, gt),
    legalMoves,
    bidStrength,
    setState: (s) => { S = s; },
    userPass: () => { if (S && S.phase === "bid") { S.bidIndex++; nextBid(); } },
  };
})();
