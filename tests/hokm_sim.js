// تست شبیه‌سازی بازی حکم بدون DOM واقعی
function makeEl() {
  return {
    innerHTML: "",
    textContent: "",
    dataset: {},
    classList: { add() {}, remove() {}, toggle() {} },
    style: {},
    scrollTop: 0,
    scrollHeight: 0,
    children: [],
    addEventListener() {},
    removeEventListener() {},
    appendChild() {},
    remove() {},
    querySelectorAll() { return []; },
    querySelector() { return null; },
  };
}
const elements = {};
global.document = {
  getElementById(id) { if (!elements[id]) elements[id] = makeEl(); return elements[id]; },
  createElement() { return makeEl(); },
  body: makeEl(),
  querySelector() { return null; },
  querySelectorAll() { return []; },
};
global.window = global;
global.location = { hash: "" };
global.setTimeout = (fn) => { try { fn(); } catch (e) { console.error("TIMER ERROR:", e.message); } return 0; };
global.clearTimeout = () => {};

require("../webapp/hokm.js");

const T = global.__HokmTest;
let failures = 0;
function check(name, cond) {
  if (cond) console.log("  ✅", name);
  else { failures++; console.log("  ❌", name); }
}

// 1) تست ارزش برگ در انواع بازی
console.log("== ارزش برگ ==");
T.setState({ trumpSuit: "h" });
const ace = { s: "s", v: 14 }, two = { s: "s", v: 2 }, trumpAce = { s: "h", v: 14 };
check("حکم: آس پیک = 14", T.trickValue(ace, "s", "hokm") === 14);
check("حکم: آس حکم (دل) = 114", T.trickValue(trumpAce, "s", "hokm") === 114);
check("سرس: آس = 14", T.trickValue(ace, "s", "sars") === 14);
check("سرس: دو = 2", T.trickValue(two, "s", "sars") === 2);
check("نرس: دو = 13 (بزرگترین)", T.trickValue(two, "s", "nares") === 13);
check("نرس: آس = 1 (کوچکترین)", T.trickValue(ace, "s", "nares") === 1);
check("تک‌نرس: آس = 13 (بالاترین)", T.trickValue(ace, "s", "tek") === 13);
check("تک‌نرس: دو = 12", T.trickValue(two, "s", "tek") === 12);
check("تک‌نرس: شاه = 1 (پایین‌ترین)", T.trickValue({ s: "s", v: 13 }, "s", "tek") === 1);
check("تک‌نرس: سرباز = 3", T.trickValue({ s: "s", v: 11 }, "s", "tek") === 3);
check("نرس: برگ غیر خال زمینه = 0", T.trickValue({ s: "h", v: 14 }, "s", "nares") === 0);

function autoPlayAll() {
  // نوبت‌های کاربر را خودکار بازی می‌کنیم تا بازی به پایان برسد
  let guard = 0;
  while (T.getState() && guard++ < 300) {
    const st = T.getState();
    if (st.phase === "bid") {
      T.userPass(); // کاربر در حکم‌گیری پاس می‌ده
      continue;
    }
    if (st.phase !== "play") break;
    if (st.turn === 0) {
      const legal = T.legalMoves(0);
      if (!legal.length) break;
      T.playCard(0, legal[0]);
    }
  }
  return T.getState() ? T.getState().phase : "?";
}

// 2) شبیه‌سازی بازی کامل (سه سختی)
console.log("== شبیه‌سازی بازی ==");
for (const diff of ["easy", "hard", "expert"]) {
  try {
    T.startNewGame(diff);
    const phase = autoPlayAll();
    const st = T.getState();
    check(`${diff}: بازی به پایان رسید (phase=${phase})`, phase === "done");
    check(`${diff}: امتیاز نهایی معتبر`, st.teamScores[0] + st.teamScores[1] >= 7);
  } catch (e) {
    failures++;
    console.log("  ❌", diff, "EXCEPTION:", e.message, e.stack ? e.stack.split("\n")[1] : "");
  }
}

// 3) شبیه‌سازی چند دست با هر نوع بازی (اجباری: نوع بازی توسط ربات انتخاب می‌شه، پس مستقیم ست می‌کنیم)
console.log("== انواع بازی ==");
for (const gt of ["hokm", "sars", "nares", "tek"]) {
  try {
    T.startNewGame("hard");
    const st = T.getState();
    st.gameType = gt;
    if (gt === "hokm") st.trumpSuit = "d"; else st.trumpSuit = null;
    T.setState(st);
    const phase = autoPlayAll();
    const st2 = T.getState();
    check(`${gt}: بازی کامل شد (${phase})`, phase === "done");
    check(`${gt}: امتیاز نهایی معتبر`, st2.teamScores[0] + st2.teamScores[1] >= 7);
  } catch (e) {
    failures++;
    console.log("  ❌", gt, "EXCEPTION:", e.message);
  }
}

// 4) تست legalMoves
console.log("== حرکات مجاز ==");
T.setState({ hands: [[{ s: "s", v: 14 }, { s: "h", v: 13 }, { s: "s", v: 2 }], [], [], []], ledSuit: "s", gameType: "hokm", trumpSuit: null, phase: "play", trick: [], trickLeader: 0, turn: 0, teamScores: [0,0], tricksTaken: [0,0], logs: [], playedAll: new Set() });
const moves = T.legalMoves(0);
check("با برگ پیک، فقط پیک مجازه", moves.length === 2);
T.setState({ hands: [[{ s: "s", v: 14 }, { s: "h", v: 13 }], [], [], []], ledSuit: "c", gameType: "hokm", trumpSuit: null, phase: "play", trick: [], trickLeader: 0, turn: 0, teamScores: [0,0], tricksTaken: [0,0], logs: [], playedAll: new Set() });
const moves2 = T.legalMoves(0);
check("بدون گشنیز، هر دو برگ مجازه", moves2.length === 2);

console.log(failures === 0 ? "\n🎉 ALL HOKM TESTS PASSED" : `\n💔 ${failures} FAILURES`);
process.exit(failures === 0 ? 0 : 1);
