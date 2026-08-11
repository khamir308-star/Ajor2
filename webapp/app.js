(() => {
  "use strict";

  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];
  const fa = new Intl.NumberFormat("fa-IR");
  const tgCandidate = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  const tg = tgCandidate && (tgCandidate.initData || (tgCandidate.platform && tgCandidate.platform !== "unknown")) ? tgCandidate : null;

  let points = 0;
  let gameTimer = null;
  let reactionStart = 0;
  let reactionReady = false;
  let toastTimer = null;
  let hapticsEnabled = true;
  try { hapticsEnabled = localStorage.getItem("ajor_haptics") !== "off"; } catch (_) {}
  let newsItems = [];
  let newsLoaded = false;
  let activeNewsFilter = "all";
  let currentJoke = "";
  let profileState = null;
  let pendingAvatarData = null;
  let resetAvatarRequested = false;
  let serverOccasionState = null;
  let welcomeTimer = null;
  let channelPostsLoaded = false;
  let walletState = null;
  let clubState = null;
  let liveBoardPeriod = "weekly";
  let aiMode = "chat";
  let aiHistory = [];
  let aiStatus = null;
  let aiImageObjectUrl = null;

  const EMOJI_ROUNDS = [
    { emoji: "🐸 ☕ 👀", answer: "به من چه!", options: ["به من چه!", "صبح شنبه", "چای تلخ", "قورباغه خوابالو"] },
    { emoji: "🧠 🚫 📱", answer: "مغزم لود نمی‌شه", options: ["اینترنت قطع شد", "درس نخوندم", "مغزم لود نمی‌شه", "گوشی هوشمند"] },
    { emoji: "🛌 ⏰ 🚫", answer: "فقط پنج دقیقه دیگه", options: ["صبح بخیر", "فقط پنج دقیقه دیگه", "خواب زمستانی", "دیر رسیدم"] },
    { emoji: "💸 🪽 😭", answer: "پولام پرید", options: ["خرید موفق", "حقوق اومد", "پولام پرید", "سفر گرون"] },
    { emoji: "📶 🐢 😡", answer: "اینترنت لاک‌پشتی", options: ["مسابقه دو", "اینترنت لاک‌پشتی", "گوشی قدیمی", "بازی آنلاین"] },
    { emoji: "👀 🍿 🔥", answer: "تماشای دراما", options: ["آشپزی", "سینما رفتن", "تماشای دراما", "چشم‌زخم"] },
    { emoji: "🐈 ⌨️ 💻", answer: "گربه برنامه‌نویس", options: ["گربه برنامه‌نویس", "هک شدم", "کیبورد خراب", "جلسه آنلاین"] },
    { emoji: "🧑‍💻 ☕ 🌙", answer: "برنامه‌نویس شب‌کار", options: ["صبح کاری", "برنامه‌نویس شب‌کار", "کافه‌گردی", "امتحان فردا"] },
    { emoji: "📅 ➡️ 🏃", answer: "از شنبه شروع می‌کنم", options: ["تقویم ورزشی", "از شنبه شروع می‌کنم", "دیر کردم", "تعطیلات"] },
    { emoji: "😂 📱 🌙", answer: "تا صبح اسکرول", options: ["تماس شبانه", "تا صبح اسکرول", "فیلم کمدی", "خواب خوب"] },
    { emoji: "🤡 📸 ✨", answer: "ژست خیلی خاص", options: ["سیرک", "ژست خیلی خاص", "عکس خراب", "فیلتر جدید"] },
    { emoji: "🗣️ ❌ 🧠", answer: "حرف نزن مغزم لود نیست", options: ["ساکت باش", "حرف نزن مغزم لود نیست", "جلسه مهم", "صدات نمیاد"] },
  ];

  const WORLD_DAYS = {
    "1-1": "روز جهانی صلح و شروع سال نو", "1-4": "روز جهانی خط بریل", "1-24": "روز جهانی آموزش",
    "2-4": "روز جهانی مبارزه با سرطان", "2-14": "روز ولنتاین", "2-21": "روز جهانی زبان مادری",
    "3-8": "روز جهانی زنان", "3-17": "روز جهانی بوسیدن", "3-20": "روز جهانی شادی", "3-21": "روز جهانی شعر",
    "4-1": "روز جهانی شوخی و خنده", "4-7": "روز جهانی سلامت", "4-22": "روز جهانی زمین", "4-23": "روز جهانی کتاب",
    "5-1": "روز جهانی کارگر", "5-4": "روز جهانی جنگ ستارگان", "5-15": "روز جهانی خانواده", "5-20": "روز جهانی زنبور",
    "6-5": "روز جهانی محیط زیست", "6-8": "روز جهانی اقیانوس‌ها", "6-21": "روز جهانی موسیقی و یوگا", "6-22": "روز جهانی بغل کردن", "6-30": "روز جهانی شبکه‌های اجتماعی",
    "7-6": "روز جهانی بوسه", "7-17": "روز جهانی ایموجی", "7-28": "روز جهانی حفاظت از طبیعت", "7-29": "روز جهانی باران و روز جهانی ببر", "7-30": "روز جهانی دوستی",
    "8-8": "روز جهانی گربه", "8-12": "روز جهانی جوانان", "8-19": "روز جهانی عکاسی",
    "9-5": "روز جهانی خیریه", "9-8": "روز جهانی سوادآموزی", "9-21": "روز جهانی صلح", "9-27": "روز جهانی گردشگری",
    "10-1": "روز جهانی قهوه", "10-4": "روز جهانی حیوانات", "10-10": "روز جهانی سلامت روان", "10-31": "هالووین",
    "11-13": "روز جهانی مهربانی", "11-19": "روز جهانی مردان", "11-20": "روز جهانی کودکان",
    "12-3": "روز جهانی افراد دارای معلولیت", "12-5": "روز جهانی داوطلب", "12-10": "روز جهانی حقوق بشر", "12-18": "روز جهانی زبان عربی"
  };
  const GREGORIAN_MONTHS_FA = ["ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن", "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر"];
  const OCCASION_EN_FA = {
    "International Men's Day": "روز جهانی مردان",
    "International Men’s Day": "روز جهانی مردان",
    "World Men's Day": "روز جهانی مردان",
    "World Men’s Day": "روز جهانی مردان",
    "International Day of Men": "روز جهانی مردان",
    "World Consumer Rights Day": "روز جهانی حقوق مصرف‌کننده",
    "World Sleep Day": "روز جهانی خواب",
    "World Water Day": "روز جهانی آب",
    "World Poetry Day": "روز جهانی شعر",
    "World Theatre Day": "روز جهانی تئاتر",
    "International Day of Happiness": "روز جهانی شادی",
  };

  function translateOccasionTitle(title) {
    const value = String(title || "").trim();
    if (!value) return "مناسبت‌های امروز در حال بروزرسانی است";
    if (OCCASION_EN_FA[value]) return OCCASION_EN_FA[value];
    const normalized = value.replaceAll("’", "'");
    if (OCCASION_EN_FA[normalized]) return OCCASION_EN_FA[normalized];
    const lowered = normalized.toLowerCase();
    if (lowered.includes("men") && lowered.includes("day")) return "روز جهانی مردان";
    if (lowered.includes("women") && lowered.includes("day")) return "روز جهانی زنان";
    if (/^(world|international)\s/i.test(value)) return "مناسبت بین‌المللی امروز";
    return value;
  }

  const FACT_ROUNDS = [
    { text: "اختاپوس سه قلب دارد و خونش آبی‌رنگ است.", fact: true, note: "واقعیه؛ اختاپوس سه قلب دارد!", emoji: "🐙" },
    { text: "یک گربه با ردشدن از روی کیبورد، رکورد رسمی اسپیدران جهان را شکست.", fact: false, note: "این یکی ساخته ذهن اینترنت بود!", emoji: "🐈" },
    { text: "از نظر گیاه‌شناسی، موز نوعی توت محسوب می‌شود.", fact: true, note: "عجیب ولی واقعی؛ موز یک berry است.", emoji: "🍌" },
    { text: "حافظه ماهی قرمز فقط سه ثانیه است.", fact: false, note: "افسانه‌ست؛ ماهی‌ها می‌توانند مدت طولانی‌تری یاد بگیرند.", emoji: "🐟" },
    { text: "عسل در شرایط مناسب می‌تواند هزاران سال سالم بماند.", fact: true, note: "رطوبت کم و اسیدی‌بودن عسل کمکش می‌کند.", emoji: "🍯" },
    { text: "دیوار چین با چشم غیرمسلح از سطح ماه دیده می‌شود.", fact: false, note: "نه؛ این ادعا سال‌هاست رد شده.", emoji: "🌕" },
    { text: "کوسه‌ها قبل از به‌وجودآمدن درختان روی زمین بوده‌اند.", fact: true, note: "کوسه‌ها بیش از ۴۰۰ میلیون سال قدمت دارند.", emoji: "🦈" },
    { text: "خود بافت مغز گیرنده درد ندارد.", fact: true, note: "بافت مغز گیرنده درد ندارد؛ بافت‌های اطراف دارند.", emoji: "🧠" },
    { text: "انسان فقط از ده درصد مغزش استفاده می‌کند.", fact: false, note: "این یک باور غلط معروف است.", emoji: "🧑" },
    { text: "مدفوع وامبت‌ها معمولاً مکعبی‌شکل است.", fact: true, note: "بله؛ یکی از عجیب‌ترین فکت‌های طبیعت!", emoji: "🧊" },
    { text: "برج ایفل در تابستان چند سانتی‌متر بلندتر می‌شود.", fact: true, note: "فلز با گرما منبسط می‌شود.", emoji: "🗼" },
    { text: "دمای صاعقه می‌تواند از سطح خورشید بیشتر باشد.", fact: true, note: "کانال صاعقه می‌تواند چند برابر داغ‌تر باشد.", emoji: "⚡" },
  ];

  function haptic(type = "light") {
    if (!hapticsEnabled) return;
    if (tg && tg.HapticFeedback) {
      if (type === "success" || type === "error") tg.HapticFeedback.notificationOccurred(type);
      else tg.HapticFeedback.impactOccurred(type);
    } else if (navigator.vibrate) {
      navigator.vibrate(type === "success" ? [24, 35, 42] : type === "error" ? [60, 30, 60] : 18);
    }
  }

  function setupTelegram() {
    if (!tg) return;
    tg.ready();
    tg.expand();
    try {
      tg.setHeaderColor("#0b0a0f");
      tg.setBackgroundColor("#0b0a0f");
      tg.setBottomBarColor("#0b0a0f");
    } catch (_) {}
    const applySafeArea = () => {
      const safe = tg.safeAreaInset || {};
      const content = tg.contentSafeAreaInset || {};
      document.documentElement.style.setProperty("--tg-safe-top", `${Math.max(safe.top || 0, content.top || 0)}px`);
      document.documentElement.style.setProperty("--tg-safe-bottom", `${Math.max(safe.bottom || 0, content.bottom || 0)}px`);
    };
    applySafeArea();
    try {
      tg.onEvent("safeAreaChanged", applySafeArea);
      tg.onEvent("contentSafeAreaChanged", applySafeArea);
    } catch (_) {}
  }

  function showWelcomePop() {
    const firstName = tgCandidate?.initDataUnsafe?.user?.first_name || "رفیق";
    const messages = [
      `${firstName} جان، آماده‌ای امروز رکورد بترکونی؟ ⚡`,
      `اوه اوه! ${firstName} اومد؛ بازی‌ها جدی شدن 😎`,
      `${firstName}، جایزه و چالش امروز منتظرته! 🎁`,
      `خوش اومدی ${firstName}! حال خوبت رو روشن کن 🔥`,
      `${firstName} وارد شد؛ اینترنت آماده وایرال‌شدنه! 🚀`,
      `رفیقِ خفن برگشت! بزن بریم ${firstName} 👾`,
    ];
    const pop = $("#welcomePop");
    if (!pop) return;
    $("#welcomeMessage").textContent = messages[Math.floor(Math.random() * messages.length)];
    pop.classList.add("show"); pop.setAttribute("aria-hidden", "false"); haptic("light");
    clearTimeout(welcomeTimer);
    welcomeTimer = setTimeout(() => { pop.classList.remove("show"); pop.setAttribute("aria-hidden", "true"); }, 2200);
  }

  function closeWelcomePop() {
    clearTimeout(welcomeTimer);
    const pop = $("#welcomePop");
    pop?.classList.remove("show"); pop?.setAttribute("aria-hidden", "true");
  }

  function showToast(title, message, kind = "success") {
    const toast = $("#toast");
    $("b", toast).textContent = title;
    $("small", toast).textContent = message;
    toast.style.borderRightColor = kind === "error" ? "var(--danger)" : "var(--green)";
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 3200);
  }

  function addPoints(amount) {
    points += amount;
    $$('[data-points]').forEach(el => el.textContent = fa.format(points));
  }

  async function syncGameReward(game, score) {
    if (!tgCandidate?.initData) return;
    try {
      const response = await fetch("/api/game/reward", { method: "POST", headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": tgCandidate.initData }, body: JSON.stringify({ game, score }) });
      if (!response.ok) return;
      const data = await response.json();
      if (data.wallet) { walletState = data.wallet; renderWallet(); }
      if (clubState && Number.isFinite(data.coins)) { clubState.coins = data.coins; renderRewardsClub(); }
      if (data.awarded > 0) showToast(`+${fa.format(data.awarded)} امتیاز و +${fa.format(data.awarded_coins || 0)} سکه`, "پاداش واقعی به حسابت اضافه شد.");
    } catch (error) { console.warn("Game reward sync failed", error); }
  }

  function navigate(page, pushHash = true) {
    const target = $(`.page[data-page="${page}"]`);
    if (!target) return;
    $$(".page").forEach(section => section.classList.toggle("active", section === target));
    $$("[data-nav]").forEach(button => button.classList.toggle("active", button.dataset.nav === page));
    if (pushHash && history.replaceState) history.replaceState(null, "", `#${page}`);
    if (page === "news") loadNews();
    if (page === "rewards") loadRewardsClub();
    if (page === "ai") { loadAIStatus(); loadReminders(); }
    if (page === "hokm") { if (window.HokmApp) window.HokmApp.mount(); }
    else if (window.HokmApp) { window.HokmApp.unmount(); }
    if (page === "boardgames") { if (window.BoardGamesApp) window.BoardGamesApp.mount(); }
    else if (window.BoardGamesApp) { window.BoardGamesApp.unmount(); }
    if (page === "ajorchin") { if (window.AjorchinGame) window.AjorchinGame.mount(); }
    if (page === "snake") { if (window.SnakeGame) window.SnakeGame.mount(); }
    if (page === "calendar") { renderCalendar(); }
    if (page === "music") { setupMusicTabs(); }
    if (page === "shop") { loadShop(); }
    window.scrollTo({ top: 0, behavior: "smooth" });
    haptic("light");
  }

  function openBotStart(parameter) {
    const url = `https://t.me/Ajorparehbot?start=${encodeURIComponent(parameter)}`;
    if (tg?.openTelegramLink) tg.openTelegramLink(url);
    else window.open(url, "_blank", "noopener");
  }

  function setupBotActions() {
    $$('[data-open-bot]').forEach(button => {
      button.addEventListener("click", event => {
        event.preventDefault();
        openBotStart(button.dataset.openBot);
      });
    });
  }

  function setupNavigation() {
    $$('[data-nav]').forEach(button => button.addEventListener("click", () => navigate(button.dataset.nav)));
    $$('[data-go]').forEach(button => button.addEventListener("click", event => {
      event.preventDefault();
      navigate(button.dataset.go);
    }));
    const initial = location.hash.replace("#", "");
    if (["games", "challenges", "news", "media", "ai", "rewards", "leaderboard", "support", "profile", "hokm", "calendar", "boardgames", "ajorchin", "snake", "music"].includes(initial)) navigate(initial, false);
  }

  // ===== تقویم شمسی =====
  const JALALI_MONTHS_FA = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
  const JALALI_WEEKDAYS_FA = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"];
  const ISLAMIC_MONTHS_FA = ["محرم", "صفر", "ربیع‌الاول", "ربیع‌الثانی", "جمادی‌الاول", "جمادی‌الثانی", "رجب", "شعبان", "رمضان", "شوال", "ذی‌القعده", "ذی‌الحجه"];
  const CAL_OCCASIONS = {
    "1/1": "🎉 عید نوروز · جشن سال نو", "1/2": "🎉 عید نوروز", "1/3": "🎉 عید نوروز", "1/4": "🎉 تعطیل عید نوروز",
    "1/12": "🌹 روز جمهوری اسلامی ایران", "1/13": "🌳 سیزده‌به‌در · روز طبیعت", "1/18": "🎖 روز ارتش جمهوری اسلامی ایران",
    "1/25": "🌹 روز بزرگداشت عطار نیشابوری", "1/29": "🚀 روز ملی فناوری هسته‌ای",
    "2/1": "✍️ روز بزرگداشت سعدی", "2/2": "🌍 روز زمین پاک", "2/8": "👨‍🏫 روز معلم", "2/15": "🏡 روز شیراز و بزرگداشت سعدی",
    "2/18": "🧭 روز جهانی موزه و میراث فرهنگی", "2/25": "🌹 روز بزرگداشت فردوسی · روز پاسداشت زبان فارسی",
    "3/5": "🌹 روز جهانی محیط زیست", "3/14": "🌹 رحلت امام خمینی (ره)", "3/15": "📣 قیام ۱۵ خرداد",
    "3/21": "📖 روز ملی گل و گیاه", "3/29": "🌹 سالروز درگذشت دکتر مصدق",
    "4/13": "🏵 روز شهدا", "4/14": "✒️ روز قلم", "4/24": "🤝 روز تعاون",
    "5/1": "💪 روز مقاومت اسلامی", "5/3": "❤️ روز اهدای خون", "5/8": "🌹 روز مشروطه", "5/10": "👨‍👩‍👧 روز ملی خانواده",
    "5/26": "🌹 سالروز بازگشت آزادگان سرافراز به میهن", "5/27": "🌹 روز بزرگداشت شهید چمران",
    "6/1": "⚕️ روز بزرگداشت ابوعلی سینا · روز پزشک", "6/2": "🌹 روز بزرگداشت ابوریحان بیرونی", "6/4": "🇵🇸 روز همبستگی با مردم فلسطین",
    "6/5": "💊 روز داروسازی", "6/8": "🛡 روز ملی مبارزه با تروریسم", "6/26": "🚦 روز ملی حمل و نقل", "6/31": "🕌 روز جهانی مسجد",
    "7/1": "📚 آغاز سال تحصیلی · روز جهانی سالمند", "7/7": "🚒 روز آتش‌نشان و ایمنی", "7/8": "📜 روز بزرگداشت مولوی",
    "7/10": "🧒 روز جهانی کودک", "7/13": "👮 روز نیروی انتظامی", "7/15": "🌾 روز ملی روستا و عشایر",
    "7/16": "🍽 روز جهانی غذا", "7/20": "🍷 روز بزرگداشت حافظ", "7/26": "🏃 روز تربیت بدنی و ورزش",
    "8/13": "🎓 روز دانش‌آموز", "8/15": "📚 روز کتاب و کتاب‌خوانی", "8/24": "📚 روز کتاب و کتاب‌خوانی", "8/26": "🌿 روز هوای پاک",
    "9/1": "⚓️ روز خلیج فارس", "9/3": "🧩 روز جهانی معلولان", "9/5": "🟢 روز بسیج مستضعفین", "9/7": "⚓️ روز نیروی دریایی",
    "9/9": "🏛 روز مجلس شورای اسلامی", "9/16": "🎓 روز دانشجو", "9/25": "🔬 روز پژوهش", "9/30": "🌙 شب یلدا · شب چله",
    "10/1": "🎄 میلاد حضرت مسیح (ع) · سال نو میلادی", "10/5": "✍️ روز بزرگداشت شهریار", "10/9": "🛡 روز بصیرت و میثاق امت با ولایت",
    "10/14": "🌾 روز جهاد کشاورزی", "10/17": "🐄 روز دامپزشکی", "10/22": "🇵🇸 روز غزه", "10/25": "👨‍👩‍👧‍👦 روز خانواده", "10/29": "🌿 روز هوای پاک",
    "11/1": "🚀 روز ملی هوافضا", "11/12": "✈️ ورود امام خمینی (ره) به میهن · آغاز دهه فجر", "11/19": "🗡 جشن بهمنگان",
    "11/22": "🇮🇷 روز پیروزی انقلاب اسلامی ایران", "11/23": "🎖 روز روحانیت مبارز", "11/25": "🎖 روز نیروی هوایی", "11/29": "💪 روز اقتصاد مقاومتی",
    "12/3": "🐅 روز جهانی حیات وحش", "12/5": "🔭 روز بزرگداشت خواجه نصیرالدین طوسی · روز مهندسی", "12/14": "🌹 روز درختکاری",
    "12/15": "🌳 روز درختکاری", "12/25": "✍️ روز بزرگداشت پروین اعتصامی", "12/29": "🛢 روز ملی شدن صنعت نفت ایران · جشن اسفندگان",
  };

  function jalaliMonthLength(jy, jm) {
    if (jm <= 6) return 31;
    if (jm <= 11) return 30;
    return 29;
  }
  function g2d(gy, gm, gd) {
    const div = (a, b) => Math.trunc(a / b), mod = (a, b) => a - Math.trunc(a / b) * b;
    let d = div((gy + div(gm - 8, 6) + 100100) * 1461, 4) + div(153 * mod(gm + 9, 12) + 2, 5) + gd - 34840408;
    d = d - div(div(gy + 100100 + div(gm - 8, 6), 100) * 3, 4) + 752;
    return d;
  }
  const BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178];
  function jalCal(jy) {
    const div = (a, b) => Math.trunc(a / b), mod = (a, b) => a - Math.trunc(a / b) * b;
    const bl = BREAKS.length; let gy = jy + 621, leapJ = -14, jp = BREAKS[0], jm, jump, leapG, march, n;
    for (let i = 1; i < bl; i++) { jm = BREAKS[i]; jump = jm - jp; if (jy < jm) break; leapJ = leapJ + div(jump, 33) * 8 + div(mod(jump, 33), 4); jp = jm; }
    n = jy - jp;
    leapJ = leapJ + div(n, 33) * 8 + div(mod(n, 33) + 3, 4);
    if (mod(jump, 33) === 4 && jump - n === 4) leapJ += 1;
    leapG = div(gy, 4) - div((div(gy, 100) + 1) * 3, 4) - 150;
    march = 20 + leapJ - leapG;
    return { gy, march };
  }
  function j2d(jy, jm, jd) {
    const div = (a, b) => Math.trunc(a / b);
    const r = jalCal(jy);
    return g2d(r.gy, 3, r.march) + (jm - 1) * 31 - div(jm, 7) * (jm - 7) + jd - 1;
  }
  function d2g(jdn) {
    const div = (a, b) => Math.trunc(a / b), mod = (a, b) => a - Math.trunc(a / b) * b;
    let j = 4 * jdn + 139361631;
    j = j + div(div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908;
    const i = div(mod(j, 1461), 4) * 5 + 308;
    const gd = div(mod(i, 153), 5) + 1;
    const gm = mod(div(i, 153), 12) + 1;
    const gy = div(j, 1461) - 100100 + div(8 - gm, 6);
    return { gy, gm, gd };
  }
  function gregorianToJalali(gy, gm, gd) {
    const div = (a, b) => Math.trunc(a / b), mod = (a, b) => a - Math.trunc(a / b) * b;
    const jdn = g2d(gy, gm, gd);
    const gy2 = d2g(jdn).gy;
    let jy = gy2 - 621;
    const r = jalCal(jy);
    const jdn1f = g2d(gy2, 3, r.march);
    let k = jdn - jdn1f;
    if (k >= 0) {
      if (k <= 185) { return { jy, jm: 1 + div(k, 31), jd: mod(k, 31) + 1 }; }
      k -= 186;
    } else {
      jy -= 1; k += 179; if (r.leap === 1) k += 1;
    }
    return { jy, jm: 7 + div(k, 30), jd: mod(k, 30) + 1 };
  }
  function jalaliToGregorian(jy, jm, jd) {
    const r = d2g(j2d(jy, jm, jd));
    return r;
  }
  function occFor(jy, jm, jd) {
    const list = [];
    const key = jm + "/" + jd;
    if (CAL_OCCASIONS[key]) list.push(CAL_OCCASIONS[key]);
    return list;
  }

  let calState = null;
  function renderCalendar() {
    const grid = $("#calGrid"); if (!grid) return;
    const now = new Date();
    const today = gregorianToJalali(now.getFullYear(), now.getMonth() + 1, now.getDate());
    if (!calState) calState = { jy: today.jy, jm: today.jm };
    const { jy, jm } = calState;
    $("#calMonthTitle").textContent = `${JALALI_MONTHS_FA[jm - 1]} ${jy}`;
    // امروز
    $("#calTodayDay").textContent = today.jd;
    $("#calTodayMonthYear").textContent = `${JALALI_MONTHS_FA[today.jm - 1]} ${today.jy} · ${JALALI_WEEKDAYS_FA[(now.getDay() + 1) % 7]}`;
    const gToday = jalaliToGregorian(today.jy, today.jm, today.jd);
    const gNames = GREGORIAN_MONTHS_FA;
    $("#calTodayGregorian").textContent = `${fa.format(gToday.gd)} ${gNames[gToday.gm - 1]} ${fa.format(gToday.gy)}`;
    // مناسبت امروز
    const occPanel = $("#calTodayOccasions");
    occPanel.replaceChildren();
    const todayOcc = occFor(today.jy, today.jm, today.jd);
    todayOcc.forEach(o => { const s = document.createElement("span"); s.textContent = o; occPanel.appendChild(s); });
    // شبکه ماه
    const first = jalaliToGregorian(jy, jm, 1);
    let firstDow = new Date(first.gy, first.gm - 1, first.gd).getDay(); // 0=Sun..6=Sat
    const saturdayFirst = (firstDow + 1) % 7; // شنبه=0
    const len = jalaliMonthLength(jy, jm);
    const prevM = jm === 1 ? 12 : jm - 1, prevY = jm === 1 ? jy - 1 : jy;
    const nextM = jm === 12 ? 1 : jm + 1, nextY = jm === 12 ? jy + 1 : jy;
    const prevLen = jalaliMonthLength(prevY, prevM);
    grid.replaceChildren();
    let selected = null;
    for (let i = 0; i < saturdayFirst; i++) {
      const el = document.createElement("div");
      el.className = "cal-day other"; el.textContent = prevLen - saturdayFirst + i + 1;
      grid.appendChild(el);
    }
    for (let d = 1; d <= len; d++) {
      const el = document.createElement("div");
      el.className = "cal-day";
      const isToday = d === today.jd && jm === today.jm && jy === today.jy;
      const occ = occFor(jy, jm, d);
      if (isToday) el.classList.add("today");
      if (occ.length) { el.classList.add("occ"); const dot = document.createElement("i"); dot.className = "occ-dot"; el.appendChild(dot); }
      el.textContent = d;
      el.addEventListener("click", () => {
        if (selected) selected.classList.remove("selected");
        el.classList.add("selected"); selected = el;
        showDayOccasions(jy, jm, d, occ);
      });
      grid.appendChild(el);
    }
    let fill = (saturdayFirst + len) % 7; let day = 1;
    while (fill !== 0) {
      const el = document.createElement("div");
      el.className = "cal-day other"; el.textContent = day++;
      grid.appendChild(el);
      fill = (fill + 1) % 7;
    }
    // پنل مناسبت‌های ماه
    const panel = $("#calOccasionsPanel");
    panel.replaceChildren();
    const heading = document.createElement("div");
    heading.className = "section-heading compact";
    heading.innerHTML = `<div><span>رویدادها</span><h2>مناسبت‌های ${JALALI_MONTHS_FA[jm - 1]}</h2></div>`;
    panel.appendChild(heading);
    let any = false;
    for (let d = 1; d <= len; d++) {
      const occ = occFor(jy, jm, d);
      if (occ.length) {
        any = true;
        const row = document.createElement("div");
        row.className = "cal-occasion-row";
        row.innerHTML = `<b>${d} ${JALALI_MONTHS_FA[jm - 1]}</b> ${escapeHtml(occ[0])}`;
        panel.appendChild(row);
      }
    }
    if (!any) { const p = document.createElement("p"); p.textContent = "در این ماه مناسبت خاصی ثبت نشده."; p.style.color = "#8a93a6"; p.style.fontSize = "12px"; panel.appendChild(p); }
  }
  function showDayOccasions(jy, jm, jd, occ) {
    if (!occ.length) return;
    const panel = $("#calOccasionsPanel");
    panel.replaceChildren();
    const row = document.createElement("div");
    row.className = "cal-occasion-row";
    row.innerHTML = `<b>${jd} ${JALALI_MONTHS_FA[jm - 1]} ${jy}</b> ${occ.map(o => escapeHtml(o)).join(" · ")}`;
    panel.prepend(row);
  }
  function setupCalendar() {
    $("#calPrevBtn")?.addEventListener("click", () => {
      if (!calState) return;
      calState.jm -= 1;
      if (calState.jm < 1) { calState.jm = 12; calState.jy -= 1; }
      renderCalendar();
    });
    $("#calNextBtn")?.addEventListener("click", () => {
      if (!calState) return;
      calState.jm += 1;
      if (calState.jm > 12) { calState.jm = 1; calState.jy += 1; }
      renderCalendar();
    });
  }

  function setupTelegramLinks() {
    $$('[data-telegram-link]').forEach(link => link.addEventListener("click", event => {
      if (!tg) return;
      event.preventDefault();
      tg.openTelegramLink(link.href);
    }));
  }

  function tehranGregorianParts(date = new Date()) {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "Asia/Tehran", year: "numeric", month: "numeric", day: "numeric"
    }).formatToParts(date);
    return {
      year: Number(parts.find(part => part.type === "year")?.value),
      month: Number(parts.find(part => part.type === "month")?.value),
      day: Number(parts.find(part => part.type === "day")?.value),
    };
  }

  function updateDailyContext() {
    const now = new Date();
    const dateOutput = $("#persianDate");
    const clockOutput = $("#tehranClock");
    const eventOutput = $("#worldOccasion");
    if (dateOutput) {
      dateOutput.textContent = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
        timeZone: "Asia/Tehran", weekday: "long", day: "numeric", month: "long", year: "numeric"
      }).format(now);
    }
    if (clockOutput) {
      clockOutput.textContent = new Intl.DateTimeFormat("fa-IR", {
        timeZone: "Asia/Tehran", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false
      }).format(now);
    }
    if (eventOutput) {
      const { year, month, day } = tehranGregorianParts(now);
      const dateKey = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      // API تقویم مرجع زمان تهران است؛ حتی اگر ساعت دستگاه کاربر متفاوت باشد،
      // مناسبت فارسی برگشتی از سرور را نمایش بده و به fallback خالی نرو.
      const serverOccasion = serverOccasionState?.primary ? translateOccasionTitle(serverOccasionState.primary) : "";
      const localOccasion = translateOccasionTitle(WORLD_DAYS[`${month}-${day}`]);
      const occasion = serverOccasion || localOccasion;
      eventOutput.textContent = `${fa.format(day)} ${GREGORIAN_MONTHS_FA[month - 1]} · ${occasion}`;
      if (serverOccasionState?.items?.length) {
        eventOutput.title = serverOccasionState.items.map(item => translateOccasionTitle(item.title)).join(" · ");
      }
    }
  }

  async function loadDailyOccasion() {
    try {
      const response = await fetch(`/api/occasion?t=${Date.now()}`, { headers: { "Accept": "application/json" } });
      if (!response.ok) throw new Error(`occasion ${response.status}`);
      serverOccasionState = await response.json();
      updateDailyContext();
    } catch (error) {
      console.warn("Daily occasion unavailable; using local calendar", error);
    }
  }

  function setupDailyContext() {
    updateDailyContext();
    loadDailyOccasion();
    setInterval(updateDailyContext, 1000);
    setInterval(loadDailyOccasion, 15 * 60 * 1000);
  }

  function setupCountdown() {
    let remaining = 14 * 3600 + 32 * 60 + 8;
    const output = $("#countdown");
    const tick = () => {
      remaining = Math.max(0, remaining - 1);
      const h = Math.floor(remaining / 3600).toString().padStart(2, "0");
      const m = Math.floor((remaining % 3600) / 60).toString().padStart(2, "0");
      const s = (remaining % 60).toString().padStart(2, "0");
      output.textContent = `${h}:${m}:${s}`.replace(/\d/g, digit => "۰۱۲۳۴۵۶۷۸۹"[digit]);
    };
    tick();
    setInterval(tick, 1000);
  }

  const modal = $("#gameModal");
  const stage = $("#gameStage");
  const actions = $("#modalActions");
  const modalTitle = $("#modalTitle");
  const modalDescription = $("#modalDescription");

  function setModal(title, description) {
    modalTitle.textContent = title;
    modalDescription.textContent = description;
    stage.className = "game-stage";
    actions.innerHTML = "";
    clearTimeout(gameTimer);
  }

  function openModal(game) {
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    haptic("medium");
    if (game === "reflex") renderReflex();
    else if (game === "emoji") renderEmoji();
    else if (game === "cap") renderFact();
    else if (game === "memory") renderMemory();
    else if (game === "tap") renderTapStorm();
    else if (game === "reverse") renderReverse();
    else renderLaugh();
    setTimeout(() => $(".modal-close").focus(), 80);
  }

  function closeModal() {
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    clearTimeout(gameTimer);
    reactionReady = false;
  }

  function renderReflex() {
    setModal("شکارِ لحظه", "وقتی صفحه سبز شد، سریع بزن؛ زودتر نه!");
    stage.innerHTML = '<div class="stage-icon">⚡</div><div class="stage-copy">رکورد امروز ۲۸۴ میلی‌ثانیه‌ست. آماده‌ای شکستش بدی؟</div>';
    actions.innerHTML = '<button class="start-game" type="button">آماده‌ام!</button>';
    $(".start-game", actions).addEventListener("click", startReflex);
  }

  function startReflex() {
    actions.innerHTML = "";
    stage.className = "game-stage waiting";
    stage.innerHTML = '<div class="reaction-copy">صبر کن...</div><div class="reaction-sub">الان نزن، خیلی زوده!</div>';
    reactionReady = false;
    stage.onclick = () => {
      if (!reactionReady) {
        clearTimeout(gameTimer);
        haptic("error");
        stage.className = "game-stage too-soon";
        stage.innerHTML = '<div class="reaction-copy">زود زدی! 😅</div><div class="reaction-sub">تمرکز کن؛ سبز که شد بزن.</div>';
        actions.innerHTML = '<button class="btn btn-outline" type="button">دوباره</button>';
        $("button", actions).onclick = startReflex;
        stage.onclick = null;
      }
    };
    gameTimer = setTimeout(() => {
      reactionReady = true;
      reactionStart = performance.now();
      stage.className = "game-stage ready";
      stage.innerHTML = '<div class="reaction-copy">حالا بزن!</div><div class="reaction-sub">هر جای صفحه</div>';
      stage.onclick = finishReflex;
      haptic("light");
    }, 1200 + Math.random() * 2100);
  }

  function finishReflex() {
    if (!reactionReady) return;
    const result = Math.max(90, Math.round(performance.now() - reactionStart));
    reactionReady = false;
    stage.onclick = null;
    stage.className = "game-stage";
    stage.innerHTML = `<div class="result-score">${fa.format(result)} ms</div><div class="result-label">${result < 300 ? "هیولا! رکوردت فوق‌العاده‌ست 🚀" : result < 500 ? "سریع بودی! یه بار دیگه رکورد می‌زنی؟" : "گرم شدی؛ دور بعد سریع‌تر می‌شی!"}</div>`;
    actions.innerHTML = '<button class="btn btn-outline" type="button" data-retry>دوباره</button><button class="btn btn-cyan" type="button" data-result-share><svg><use href="#i-share"/></svg> اشتراک رکورد</button>';
    $("[data-retry]", actions).onclick = startReflex;
    $("[data-result-share]", actions).onclick = () => share(`رکورد شکار لحظه من ${result}ms شد! می‌تونی شکستش بدی؟`);
    const earned = result < 300 ? 120 : result < 500 ? 80 : 40;
    addPoints(earned);
    syncGameReward("reflex", result);
    haptic("success");
    if (result < 500) burstConfetti();
  }

  function renderEmoji(round = 0, score = 0, rounds = null) {
    rounds = rounds || [...EMOJI_ROUNDS].sort(() => Math.random() - .5);
    if (round >= rounds.length) {
      const xp = 60 + score * 18;
      setModal("ایموجی‌بازی · پایان", "همه ۱۲ راند رو تموم کردی!");
      stage.innerHTML = `<div class="result-score">${fa.format(score)} / ${fa.format(rounds.length)}</div><div class="result-label">${score >= 10 ? "استاد ایموجی! 🏆" : score >= 7 ? "خیلی خوب بود! 🔥" : "دور بعد بهتر می‌زنی!"} +${fa.format(xp)} XP</div>`;
      actions.innerHTML = '<button class="btn btn-outline" data-emoji-retry>از اول</button><button class="btn btn-cyan" data-result-share><svg><use href="#i-share"/></svg> اشتراک</button>';
      $('[data-emoji-retry]', actions).onclick = () => renderEmoji();
      $('[data-result-share]', actions).onclick = () => share(`ایموجی‌بازی رو با امتیاز ${score} از ${rounds.length} تموم کردم! 😎`);
      addPoints(xp); syncGameReward("emoji", score); if (score >= 7) burstConfetti(150); haptic("success");
      return;
    }
    const item = rounds[round];
    setModal(`ایموجی‌بازی · راند ${fa.format(round + 1)}`, `امتیاز ${fa.format(score)} · از روی ایموجی‌ها حدس بزن.`);
    const options = [...item.options].sort(() => Math.random() - .5);
    stage.innerHTML = `<div class="quiz-emojis">${item.emoji}</div><div class="quiz-options">${options.map(option => `<button ${option === item.answer ? "data-correct" : ""}>${escapeHTML(option)}</button>`).join("")}</div>`;
    $$(".quiz-options button", stage).forEach(button => button.onclick = () => {
      const correct = button.hasAttribute("data-correct");
      button.classList.add(correct ? "correct" : "wrong");
      $$(".quiz-options button", stage).forEach(choice => choice.disabled = true);
      if (!correct) $('[data-correct]', stage)?.classList.add("correct");
      modalDescription.textContent = correct ? "درست گفتی! 🔥" : `جواب درست: ${item.answer}`;
      haptic(correct ? "success" : "error");
      actions.innerHTML = `<button class="btn btn-cyan" data-emoji-next>${round + 1 === rounds.length ? "نتیجه نهایی" : "راند بعدی"}</button>`;
      $('[data-emoji-next]', actions).onclick = () => renderEmoji(round + 1, score + (correct ? 1 : 0), rounds);
    });
  }

  function renderFact(round = 0, score = 0, rounds = null) {
    rounds = rounds || [...FACT_ROUNDS].sort(() => Math.random() - .5);
    if (round >= rounds.length) {
      const xp = 50 + score * 16;
      setModal("فکت یا کپ؟ · پایان", "۱۲ راند تموم شد؛ ببین چقدر گول نخوردی!");
      stage.innerHTML = `<div class="result-score">${fa.format(score)} / ${fa.format(rounds.length)}</div><div class="result-label">${score >= 10 ? "فکت‌چکر حرفه‌ای! 🎯" : score >= 7 ? "حواست خیلی جمعه!" : "اینترنت امروز گولت زد!"} +${fa.format(xp)} XP</div>`;
      actions.innerHTML = '<button class="btn btn-outline" data-fact-retry>از اول</button><button class="btn btn-cyan" data-result-share><svg><use href="#i-share"/></svg> اشتراک</button>';
      $('[data-fact-retry]', actions).onclick = () => renderFact();
      $('[data-result-share]', actions).onclick = () => share(`فکت یا کپ رو با امتیاز ${score} از ${rounds.length} تموم کردم! 🎯`);
      addPoints(xp); syncGameReward("fact", score); if (score >= 7) burstConfetti(150); haptic("success");
      return;
    }
    const item = rounds[round];
    setModal(`فکت یا کپ؟ · راند ${fa.format(round + 1)}`, `امتیاز ${fa.format(score)} · واقعیه یا الکی؟`);
    stage.innerHTML = `<div class="fact-copy">${escapeHTML(item.text)}</div><div class="fact-vote"><button data-vote="fact">فکته! ✅</button><button data-vote="cap">کپه! 🧢</button></div>`;
    $$('[data-vote]', stage).forEach(button => button.onclick = () => {
      const correct = (button.dataset.vote === "fact") === item.fact;
      stage.innerHTML = `<div class="stage-icon">${escapeHTML(item.emoji)}</div><div class="fact-copy"><b>${correct ? "درست گفتی!" : "این یکی رو گولت زد!"}</b><br>${escapeHTML(item.note)}</div>`;
      actions.innerHTML = `<button class="btn btn-cyan" data-fact-next>${round + 1 === rounds.length ? "نتیجه نهایی" : "راند بعدی"}</button>`;
      $('[data-fact-next]', actions).onclick = () => renderFact(round + 1, score + (correct ? 1 : 0), rounds);
      haptic(correct ? "success" : "error");
    });
  }

  function renderMemory() {
    setModal("حافظه میم", "۶ جفت ایموجی رو با کمترین حرکت پیدا کن.");
    const symbols = ["😂", "🐸", "⚡", "🫠", "👾", "🔥"];
    const deck = [...symbols, ...symbols].sort(() => Math.random() - .5);
    let opened = [];
    let matched = new Set();
    let moves = 0;
    let locked = false;
    const started = performance.now();

    const draw = () => {
      stage.innerHTML = `<div class="game-hud"><span>حرکت: <b>${fa.format(moves)}</b></span><span>جفت: <b>${fa.format(matched.size / 2)}/۶</b></span></div><div class="memory-board">${deck.map((symbol, index) => `<button class="memory-tile ${opened.includes(index) ? "flipped" : ""} ${matched.has(index) ? "matched" : ""}" data-memory-index="${index}" aria-label="کارت ${index + 1}">${opened.includes(index) || matched.has(index) ? symbol : "?"}</button>`).join("")}</div>`;
      $$('[data-memory-index]', stage).forEach(tile => tile.onclick = () => flip(Number(tile.dataset.memoryIndex)));
    };

    const finish = () => {
      const seconds = (performance.now() - started) / 1000;
      const xp = Math.max(60, 190 - moves * 5);
      stage.innerHTML = `<div class="result-score">${fa.format(moves)} حرکت</div><div class="result-label">همه جفت‌ها در ${seconds.toFixed(1)} ثانیه پیدا شد! +${fa.format(xp)} XP</div>`;
      actions.innerHTML = '<button class="btn btn-outline" data-memory-retry>دوباره</button><button class="btn btn-cyan" data-result-share><svg><use href="#i-share"/></svg> اشتراک</button>';
      $('[data-memory-retry]', actions).onclick = renderMemory;
      $('[data-result-share]', actions).onclick = () => share(`حافظه میم رو با ${moves} حرکت تموم کردم! می‌تونی بهتر بزنی؟ 🧠`);
      addPoints(xp); syncGameReward("memory", moves); haptic("success"); burstConfetti(150);
    };

    const flip = index => {
      if (locked || matched.has(index) || opened.includes(index)) return;
      opened.push(index); haptic("light"); draw();
      if (opened.length < 2) return;
      moves += 1;
      const [first, second] = opened;
      if (deck[first] === deck[second]) {
        matched.add(first); matched.add(second); opened = []; draw();
        if (matched.size === deck.length) setTimeout(finish, 260);
      } else {
        locked = true;
        setTimeout(() => { opened = []; locked = false; draw(); }, 650);
      }
    };

    actions.innerHTML = '<button class="btn btn-outline" data-memory-reset>چیدمان جدید</button>';
    $('[data-memory-reset]', actions).onclick = renderMemory;
    draw();
  }

  function renderTapStorm() {
    setModal("طوفان ضربه", "۱۰ ثانیه وقت داری؛ رکورد انگشتت رو بساز!");
    stage.innerHTML = '<div class="stage-icon">👆</div><div class="stage-copy">بیشتر از ۴۰ ضربه یعنی انگشت افسانه‌ای!</div>';
    actions.innerHTML = '<button class="start-game" type="button">شروع طوفان</button>';
    $(".start-game", actions).onclick = () => {
      let score = 0;
      const duration = 10000;
      const started = performance.now();
      actions.innerHTML = "";
      const render = () => {
        const left = Math.max(0, duration - (performance.now() - started));
        stage.innerHTML = `<div class="game-hud"><span>زمان: <b>${(left / 1000).toFixed(1)}</b></span><span>ضربه: <b>${fa.format(score)}</b></span></div><button class="tap-zone" type="button" aria-label="بزن">👆</button>`;
        $(".tap-zone", stage).onclick = () => { score += 1; haptic(score % 10 === 0 ? "medium" : "light"); render(); };
      };
      render();
      gameTimer = setInterval(() => {
        const elapsed = performance.now() - started;
        if (elapsed < duration) { render(); return; }
        clearInterval(gameTimer);
        const xp = Math.min(180, 30 + score * 3);
        const label = score >= 50 ? "فوق‌انسانی! 🚀" : score >= 40 ? "انگشت افسانه‌ای! 🔥" : "خوب بود؛ یه دور دیگه؟";
        stage.innerHTML = `<div class="result-score">${fa.format(score)} ضربه</div><div class="result-label">${label} +${fa.format(xp)} XP</div>`;
        actions.innerHTML = '<button class="btn btn-outline" data-tap-retry>دوباره</button><button class="btn btn-cyan" data-result-share><svg><use href="#i-share"/></svg> اشتراک</button>';
        $('[data-tap-retry]', actions).onclick = renderTapStorm;
        $('[data-result-share]', actions).onclick = () => share(`رکورد طوفان ضربه من ${score} تا در ۱۰ ثانیه شد! 👆⚡`);
        addPoints(xp); syncGameReward("tap", score); haptic("success"); if (score >= 35) burstConfetti();
      }, 120);
    };
  }

  function renderReverse() {
    setModal("تایپ معکوس", "کلمه رو قبل از پایان ۱۲ ثانیه برعکس بنویس.");
    const words = ["MEME", "VIRAL", "TELEGRAM", "GAMER", "CHALLENGE", "LOL", "INTERNET"];
    const word = words[Math.floor(Math.random() * words.length)];
    const answer = [...word].reverse().join("");
    let left = 12;
    stage.innerHTML = `<div class="game-hud"><span>زمان: <b id="reverseTimer">${fa.format(left)}</b></span><span>+۹۰ XP</span></div><div class="reverse-word">${word}</div><input class="reverse-input" id="reverseInput" autocomplete="off" maxlength="20" placeholder="برعکسش رو بنویس..." />`;
    actions.innerHTML = '<button class="btn btn-cyan" id="reverseSubmit">ثبت جواب</button>';
    const input = $("#reverseInput");
    const submit = () => {
      clearInterval(gameTimer);
      const won = input.value.trim().toUpperCase() === answer;
      if (won) {
        const xp = 55 + left * 3;
        stage.innerHTML = `<div class="stage-icon">🧠</div><div class="fact-copy">درست بود! <b dir="ltr">${answer}</b><br>+${fa.format(xp)} XP</div>`;
        addPoints(xp); syncGameReward("reverse", 1); haptic("success"); burstConfetti();
      } else {
        stage.innerHTML = `<div class="stage-icon">🙃</div><div class="fact-copy">جواب درست: <b dir="ltr">${answer}</b></div>`;
        haptic("error");
      }
      actions.innerHTML = '<button class="btn btn-outline" data-reverse-retry>کلمه بعدی</button>';
      $('[data-reverse-retry]', actions).onclick = renderReverse;
    };
    $("#reverseSubmit").onclick = submit;
    input.onkeydown = event => { if (event.key === "Enter") submit(); };
    input.focus();
    gameTimer = setInterval(() => {
      left -= 1;
      const timer = $("#reverseTimer"); if (timer) timer.textContent = fa.format(Math.max(0, left));
      if (left <= 0) submit();
    }, 1000);
  }

  function renderLaugh() {
    setModal("چالش نخندیدن", "۱۰ ثانیه آزمایشی؛ هر اتفاقی افتاد نخند!");
    stage.innerHTML = '<div class="stage-icon">😐</div><div class="stage-copy">صورت جدی‌ات رو آماده کن. تایمر که شروع شد، تسلیم نشو!</div>';
    actions.innerHTML = '<button class="start-game" type="button">شروع ۱۰ ثانیه</button>';
    $(".start-game", actions).onclick = startLaugh;
  }

  function startLaugh() {
    let left = 10;
    const faces = ["😐", "🫣", "🐸", "🤡", "🕺", "🐈", "🫠", "🦆", "🙃", "😂"];
    actions.innerHTML = '<button class="btn btn-outline" type="button" data-laughed>خندیدم، باختم 😂</button>';
    const render = () => {
      stage.innerHTML = `<div class="quiz-emojis">${faces[10 - left]}</div><div class="reaction-copy">${fa.format(left)}</div><div class="reaction-sub">ثانیه مقاومت کن...</div>`;
      if (left <= 0) {
        clearInterval(gameTimer);
        stage.innerHTML = '<div class="result-score">بردی! 🏆</div><div class="result-label">صورت سنگی رسماً فعال شد. +۲۵۰ XP</div>';
        actions.innerHTML = '<button class="btn btn-cyan" data-result-share><svg><use href="#i-share"/></svg> به رخ بکش</button>';
        $('[data-result-share]', actions).onclick = () => share("چالش نخندیدن آجُرپاره رو بردم! صورت سنگی واقعی منم 😐🏆");
        addPoints(250); syncGameReward("laugh", 1); haptic("success"); burstConfetti(170);
        return;
      }
      left -= 1;
    };
    render();
    gameTimer = setInterval(render, 1000);
    $('[data-laughed]', actions).onclick = () => {
      clearInterval(gameTimer);
      stage.innerHTML = '<div class="stage-icon">😂</div><div class="fact-copy">خب... حداقل صادق بودی! دوباره امتحان کن.</div>';
      actions.innerHTML = '<button class="btn btn-outline" data-retry>دوباره</button>';
      $('[data-retry]', actions).onclick = startLaugh;
      haptic("error");
    };
  }

  function escapeHTML(value = "") {
    return String(value).replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
  }

  function relativeTime(dateValue) {
    if (!dateValue) return "تازه";
    const diff = Math.max(0, Date.now() - new Date(dateValue).getTime());
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return "همین الان";
    if (minutes < 60) return `${fa.format(minutes)} دقیقه پیش`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${fa.format(hours)} ساعت پیش`;
    return `${fa.format(Math.floor(hours / 24))} روز پیش`;
  }

  function renderNews() {
    const grid = $("#newsGrid");
    const empty = $("#newsEmpty");
    if (!grid || !empty) return;
    const filtered = activeNewsFilter === "all" ? newsItems : newsItems.filter(item => item.category === activeNewsFilter);
    empty.hidden = filtered.length > 0;
    grid.hidden = filtered.length === 0;
    grid.innerHTML = filtered.map(item => {
      const url = /^https?:\/\//.test(item.url || "") ? item.url : "#";
      return `<article class="news-card" data-category="${escapeHTML(item.category)}">
        <div class="news-card-visual"><span>${escapeHTML(item.icon || "🗞")}</span><i>${escapeHTML(item.category === "tech" ? "TECH" : item.category === "iran" ? "IRAN" : "WORLD")}</i></div>
        <div class="news-card-body">
          <div class="news-source"><span>${escapeHTML(item.source)}</span><time>${escapeHTML(relativeTime(item.published_at))}</time></div>
          <h2>${escapeHTML(item.title)}</h2>
          <p>${escapeHTML(item.summary || "برای خواندن جزئیات، خبر کامل را از منبع باز کن.")}</p>
          <a href="${escapeHTML(url)}" target="_blank" rel="noopener noreferrer" data-news-link>ادامه در منبع <svg><use href="#i-external"/></svg></a>
        </div>
      </article>`;
    }).join("");
    $$('[data-news-link]', grid).forEach(link => link.onclick = event => {
      if (!tg || !tg.openLink) return;
      event.preventDefault(); tg.openLink(link.href);
    });
  }

  async function loadNews(force = false) {
    const grid = $("#newsGrid");
    const refresh = $("#newsRefresh");
    if (!grid || (newsLoaded && !force)) return;
    refresh?.classList.add("loading");
    try {
      const response = await fetch(`/api/news${force ? "?refresh=1" : ""}`, { headers: { "Accept": "application/json" } });
      if (!response.ok) throw new Error(`news ${response.status}`);
      const data = await response.json();
      newsItems = Array.isArray(data.items) ? data.items : [];
      newsLoaded = newsItems.length > 0;
      renderNews();
      const updated = $("#newsUpdated");
      if (updated) updated.textContent = data.updated_at ? `بروزرسانی ${relativeTime(data.updated_at)} · ${fa.format(newsItems.length)} خبر` : "خبرها آماده‌ان";
      if (force) showToast("خبرها تازه شد", `${fa.format(newsItems.length)} خبر جدید بررسی شد.`);
    } catch (error) {
      console.warn("News feed unavailable", error);
      grid.innerHTML = "";
      $("#newsEmpty").hidden = false;
      const updated = $("#newsUpdated"); if (updated) updated.textContent = "ارتباط خبرها موقتاً قطع شده";
    } finally {
      refresh?.classList.remove("loading");
    }
  }

  function getGuestId() {
    const telegramId = tg?.initDataUnsafe?.user?.id;
    if (telegramId) return telegramId;
    let id = localStorage.getItem("ajor_guest_id");
    if (!id) { id = Math.random().toString(36).slice(2, 10); localStorage.setItem("ajor_guest_id", id); }
    return id;
  }

  async function loadJoke(fresh = false) {
    const output = $("#jokeText");
    const button = $("#newJoke");
    if (!output) return;
    button?.classList.add("loading");
    try {
      const params = new URLSearchParams({ user: getGuestId() });
      if (fresh) params.set("fresh", "1");
      const response = await fetch(`/api/joke?${params}`);
      if (!response.ok) throw new Error("joke unavailable");
      const data = await response.json();
      currentJoke = data.joke || "امروز جوک‌دونی مرخصیه! 😅";
      output.textContent = currentJoke;
      if (fresh) { haptic("light"); output.animate([{ opacity: .2, transform: "translateY(4px)" }, { opacity: 1, transform: "none" }], { duration: 230 }); }
    } catch (_) {
      currentJoke = "اینترنت جوک‌دونی قطع شد؛ ولی خود این اتفاق یه جورایی خنده‌داره! 😅";
      output.textContent = currentJoke;
    } finally { button?.classList.remove("loading"); }
  }

  async function loadChannelPosts() {
    if (channelPostsLoaded) return;
    const container = $("#channelPostList");
    if (!container) return;
    try {
      const response = await fetch("/api/channel-posts", { headers: { "Accept": "application/json" } });
      if (!response.ok) throw new Error(`channel posts ${response.status}`);
      const data = await response.json();
      const posts = Array.isArray(data.items) ? data.items.slice(0, 6) : [];
      if (!posts.length) return;
      const mediaEmoji = { photo: "🖼", video: "🎬", animation: "😂", text: "💬", channel: "🔥" };
      container.innerHTML = posts.map((post, index) => `<a class="trend-item" href="${escapeHTML(post.url)}" target="_blank" rel="noopener" data-live-channel-link>
        <span class="trend-rank">${String(index + 1).padStart(2, "0")}</span>
        <div><span class="tag ${index === 0 ? "hot" : index === 1 ? "" : "cyan"}">${index === 0 ? "🔥 تازه‌ترین" : "از کانال"}</span><h3>${escapeHTML(post.title || post.text || "پست جدید")}</h3><p>@Ajor_pareh ${post.published_at ? `· ${escapeHTML(relativeTime(post.published_at))}` : ""}</p></div>
        <span class="trend-emoji">${mediaEmoji[post.media_type] || "🔥"}</span>
      </a>`).join("");
      $$('[data-live-channel-link]', container).forEach(link => link.onclick = event => {
        if (!tgCandidate?.openTelegramLink) return;
        event.preventDefault(); tgCandidate.openTelegramLink(link.href);
      });
      channelPostsLoaded = true;
    } catch (error) { console.warn("Channel posts unavailable", error); }
  }

  function setupNews() {
    $$('[data-news-filter]').forEach(button => button.addEventListener("click", () => {
      activeNewsFilter = button.dataset.newsFilter;
      $$('[data-news-filter]').forEach(item => item.classList.toggle("active", item === button));
      renderNews(); haptic("light");
    }));
    $("#newsRefresh")?.addEventListener("click", () => loadNews(true));
    $("#newJoke")?.addEventListener("click", () => loadJoke(true));
    $("#shareJoke")?.addEventListener("click", () => share(`${currentJoke}\n\nاز جوک‌دونی Ajorpareh 😂`));
    $$('[data-joke-reaction]').forEach(button => button.addEventListener("click", () => {
      $$('[data-joke-reaction]').forEach(item => item.classList.remove("active"));
      button.classList.add("active");
      const count = $("span", button); if (count) count.textContent = fa.format((Number(count.textContent.replace(/\D/g, "")) || 0) + 1);
      haptic("success");
    }));
    loadJoke(false);
  }

  function setupGames() {
    $$('[data-game]').forEach(card => {
      card.addEventListener("click", event => {
        event.preventDefault();
        openModal(card.dataset.game);
      });
      if (card.getAttribute("role") === "button") card.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openModal(card.dataset.game); }
      });
    });
    $(".modal-close").addEventListener("click", closeModal);
    modal.addEventListener("click", event => { if (event.target === modal) closeModal(); });
    document.addEventListener("keydown", event => { if (event.key === "Escape" && modal.classList.contains("open")) closeModal(); });
  }

  function burstConfetti(count = 110) {
    const canvas = $("#confetti");
    const ctx = canvas.getContext("2d");
    const dpr = Math.min(devicePixelRatio || 1, 2);
    canvas.width = innerWidth * dpr;
    canvas.height = innerHeight * dpr;
    ctx.scale(dpr, dpr);
    const colors = ["#ff5c1a", "#8a3ffc", "#22e6e2", "#f7ee46", "#ff4e91"];
    const pieces = Array.from({ length: count }, () => ({
      x: innerWidth * (.25 + Math.random() * .5),
      y: innerHeight * .25,
      vx: (Math.random() - .5) * 12,
      vy: -4 - Math.random() * 10,
      g: .18 + Math.random() * .12,
      size: 4 + Math.random() * 7,
      rot: Math.random() * Math.PI,
      spin: (Math.random() - .5) * .25,
      color: colors[Math.floor(Math.random() * colors.length)],
      life: 100 + Math.random() * 40
    }));
    function frame() {
      ctx.clearRect(0, 0, innerWidth, innerHeight);
      let alive = false;
      pieces.forEach(p => {
        if (p.life <= 0) return;
        alive = true; p.life -= 1; p.vy += p.g; p.x += p.vx; p.y += p.vy; p.rot += p.spin;
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.rot); ctx.fillStyle = p.color;
        ctx.fillRect(-p.size / 2, -p.size / 3, p.size, p.size * .65); ctx.restore();
      });
      if (alive) requestAnimationFrame(frame); else ctx.clearRect(0, 0, innerWidth, innerHeight);
    }
    requestAnimationFrame(frame);
  }

  async function share(text) {
    const url = "https://t.me/Ajor_pareh";
    const fullText = `${text}\n\nبازی کن: @Ajorparehbot`;
    haptic("light");
    if (tg) {
      tg.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(fullText)}`);
      return;
    }
    if (navigator.share) {
      try { await navigator.share({ title: "Ajorpareh", text: fullText, url }); return; } catch (_) {}
    }
    try {
      await navigator.clipboard.writeText(`${fullText}\n${url}`);
      showToast("کپی شد!", "لینک آماده‌ست؛ برای رفیقت بفرست.");
    } catch (_) {
      showToast("اشتراک آماده‌ست", "کانال رسمی: @Ajor_pareh");
    }
  }

  function setupShares() {
    $$('[data-share]').forEach(button => button.addEventListener("click", event => {
      event.preventDefault();
      const type = button.dataset.share;
      const copy = type === "rank" ? "من تو جدول آجُرپاره رتبه ۱۲۴م؛ بیا رکوردم رو بزن!" : type === "invite" ? "تیم هفتگی آجُرپاره یه بازیکن خفن کم داره؛ میای؟" : "چالش امروز آجُرپاره رو دیدی؟ جرأت داری امتحانش کنی؟";
      share(copy);
    }));
  }

  function setupChallenges() {
    $$('[data-filter]').forEach(button => button.addEventListener("click", () => {
      $$('[data-filter]').forEach(item => item.classList.toggle("active", item === button));
      const filter = button.dataset.filter;
      $$('[data-category]').forEach(card => card.classList.toggle("filtered-out", filter !== "all" && !card.dataset.category.includes(filter)));
      haptic("light");
    }));
    $$('.join-challenge:not([data-game])').forEach(button => button.addEventListener("click", () => {
      const joined = button.dataset.joined === "true";
      button.dataset.joined = String(!joined);
      button.textContent = joined ? "شرکت می‌کنم" : "ثبت شد ✓";
      button.classList.toggle("btn-cyan", !joined);
      button.classList.toggle("btn-outline", joined);
      if (!joined) { addPoints(20); haptic("success"); showToast("وارد چالش شدی!", "قوانین و یادآوری از ربات برات میاد."); }
    }));
  }

  async function loadMainLeaderboard(period = "all") {
    try {
      const response = await fetch(`/api/leaderboard?period=${encodeURIComponent(period)}`);
      if (!response.ok) throw new Error();
      const data = await response.json(); const items = data.items || [];
      const podiumMap = [[".podium-player.first", 0], [".podium-player.second", 1], [".podium-player.third", 2]];
      podiumMap.forEach(([selector, index]) => {
        const player = $(selector); const item = items[index]; if (!player) return;
        $("h3", player).textContent = item?.name || "—";
        $("p", player).textContent = item ? `${fa.format(item.points)} XP` : "۰ XP";
        const avatar = $(".podium-avatar", player); if (avatar) avatar.firstChild.textContent = (item?.name || "؟").trim().charAt(0);
      });
      const list = $("#rankList"); $$('article', list).forEach(article => article.remove());
      items.slice(3, 10).forEach((item, offset) => {
        const article = document.createElement("article");
        const rank = document.createElement("span"); rank.className = "rank-num"; rank.textContent = String(offset + 4).padStart(2, "0");
        const avatar = document.createElement("span"); avatar.className = "rank-avatar purple-avatar"; avatar.textContent = (item.name || "؟").trim().charAt(0);
        const copy = document.createElement("div"); const name = document.createElement("b"); const note = document.createElement("small");
        name.textContent = item.name || "بازیکن"; note.textContent = item.username ? `@${item.username}` : "بازیکن Ajorpareh"; copy.append(name, note);
        const pointsEl = document.createElement("strong"); pointsEl.textContent = fa.format(item.points || 0);
        article.append(rank, avatar, copy, pointsEl); list.appendChild(article);
      });
      $("#podium").animate([{ opacity: .45, transform: "translateY(5px)" }, { opacity: 1, transform: "none" }], { duration: 240 });
    } catch (_) { showToast("جدول لود نشد", "چند لحظه دیگه دوباره امتحان کن.", "error"); }
  }

  function setupLeaderboard() {
    $$('[data-board]').forEach(button => button.addEventListener("click", () => {
      $$('[data-board]').forEach(item => item.classList.toggle("active", item === button));
      loadMainLeaderboard(button.dataset.board); haptic("light");
    }));
    loadMainLeaderboard("all");
  }

  function renderReviews(realItems = [], demoItems = []) {
    const grid = $("#reviewsGrid");
    if (!grid) return;
    grid.replaceChildren();
    const items = [...realItems, ...demoItems];
    if (!items.length) {
      const empty = document.createElement("p"); empty.textContent = "هنوز نظری ثبت نشده."; grid.appendChild(empty); return;
    }
    items.forEach(item => {
      const card = document.createElement("article"); card.className = `review-card${item.demo ? " demo" : " real"}`;
      const head = document.createElement("div"); const name = document.createElement("b"); const stars = document.createElement("span");
      name.textContent = item.name || "کاربر Ajorpareh"; stars.textContent = "⭐".repeat(Math.max(1, Math.min(5, Number(item.rating) || 5))); head.append(name, stars);
      const text = document.createElement("p"); text.textContent = item.text || ""; card.append(head, text);
      if (item.demo) { const label = document.createElement("small"); label.textContent = "نمونه نمایشی"; card.appendChild(label); }
      else { const label = document.createElement("small"); label.textContent = "نظر تأییدشده"; card.appendChild(label); }
      grid.appendChild(card);
    });
  }

  async function loadReviews() {
    try {
      const response = await fetch("/api/reviews", { headers: { "Accept": "application/json" } });
      if (!response.ok) throw new Error();
      const data = await response.json(); renderReviews(data.items || [], data.demo_items || []);
    } catch (_) { renderReviews([], []); }
  }

  async function submitReview(event) {
    event.preventDefault();
    const form = event.currentTarget; const button = $('button[type="submit"]', form);
    const text = $("#reviewText").value.trim(); const rating = Number($("#reviewRating").value || 5);
    button.disabled = true;
    try {
      await apiRequest("/api/reviews", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, rating }),
      });
      form.reset(); haptic("success"); showToast("نظر ثبت شد", "بعد از بررسی در بخش نظرها منتشر می‌شه.");
    } catch (error) { showToast("نظر ثبت نشد", error.message, "error"); }
    finally { button.disabled = false; }
  }

  function setupSupport() {
    loadReviews();
    $("#reviewForm")?.addEventListener("submit", submitReview);
    $$('.faq-item button').forEach(button => button.addEventListener("click", () => {
      const item = button.closest(".faq-item");
      const isOpen = item.classList.contains("open");
      $$('.faq-item').forEach(faq => { faq.classList.remove("open"); $("button", faq).setAttribute("aria-expanded", "false"); });
      if (!isOpen) { item.classList.add("open"); button.setAttribute("aria-expanded", "true"); }
      haptic("light");
    }));
    $('[data-scroll-form]').addEventListener("click", () => $("#feedbackForm").scrollIntoView({ behavior: "smooth", block: "center" }));
    const textarea = $("#ticketText");
    textarea.addEventListener("input", () => $("#charCount").textContent = fa.format(textarea.value.length));
    $("#ticketForm").addEventListener("submit", async event => {
      event.preventDefault();
      if (!event.currentTarget.reportValidity()) return;
      const form = event.currentTarget;
      const button = $('button[type="submit"]', form);
      const typeLabel = $("#ticketType").selectedOptions[0].textContent;
      const messageText = $("#ticketText").value.trim();
      button.disabled = true;
      try {
        if (tgCandidate?.initData) {
          const response = await fetch("/api/support", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": tgCandidate.initData },
            body: JSON.stringify({ type: typeLabel, text: messageText }),
          });
          if (!response.ok) throw new Error(await response.text());
          const data = await response.json();
          haptic("success");
          showToast(`تیکت #${data.ticket_id} ثبت شد`, "پیام همراه آیدی تلگرامت مستقیم برای مدیر رفت.");
          form.reset(); $("#charCount").textContent = "۰";
        } else {
          try { await navigator.clipboard.writeText(`${typeLabel}\n\n${messageText}`); } catch (_) {}
          showToast("متن گزارش آماده شد", "داخل ربات Paste و ارسالش کن.");
          setTimeout(() => window.open("https://t.me/Ajorparehbot?start=support", "_blank"), 500);
        }
      } catch (error) {
        console.error("Support ticket failed", error);
        showToast("ارسال نشد", "دوباره تلاش کن یا مستقیماً به ربات پیام بده.", "error");
      } finally { button.disabled = false; }
    });
  }

  async function apiRequest(path, options = {}, timeoutMs = 45000) {
    if (!tgCandidate?.initData) throw new Error("Mini App را از داخل ربات رسمی باز کن");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const headers = { ...(options.headers || {}), "X-Telegram-Init-Data": tgCandidate.initData };
      const response = await fetch(path, { ...options, headers, signal: controller.signal });
      if (!response.ok) {
        let message = await response.text();
        try { message = JSON.parse(message).message || message; } catch (_) {}
        throw new Error(message || `HTTP ${response.status}`);
      }
      return response;
    } finally { clearTimeout(timer); }
  }

  async function submitMediaJob(event, mode, inputSelector) {
    event.preventDefault();
    const input = $(inputSelector); const url = input.value.trim();
    const button = $('button[type="submit"]', event.currentTarget); button.disabled = true;
    try {
      const response = await apiRequest("/api/media/jobs", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url, mode }),
      }, 30000);
      const data = await response.json(); input.value = "";
      showToast("در صف قرار گرفت", `شناسه ${data.job_id}؛ نتیجه داخل چت ربات ارسال می‌شه.`);
    } catch (error) { showToast("ثبت نشد", error.message, "error"); }
    finally { button.disabled = false; }
  }

  async function extractInstagramComment(event) {
    event.preventDefault();
    const input = $("#instagramCommentUrl");
    const button = $('button[type="submit"]', event.currentTarget);
    const result = $("#instagramCommentResult");
    button.disabled = true;
    result.hidden = true;
    try {
      const response = await apiRequest("/api/instagram/comment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: input.value.trim() }),
      }, 70000);
      const data = await response.json();
      const comment = data.comment;
      result.replaceChildren();
      const title = document.createElement("b");
      title.textContent = `💬 متن کامنت${comment.author ? ` · @${comment.author.replace(/^@/, "")}` : ""}`;
      const body = document.createElement("pre");
      body.textContent = comment.text || "";
      body.style.whiteSpace = "pre-wrap";
      body.style.direction = "auto";
      const copy = document.createElement("button");
      copy.type = "button"; copy.className = "btn btn-mini btn-accent"; copy.textContent = "📋 کپی متن";
      copy.addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(comment.text || ""); showToast("کپی شد", "متن کامنت در کلیپ‌بورد قرار گرفت."); }
        catch (_) { showToast("کپی نشد", "متن را دستی انتخاب کن.", "error"); }
      });
      result.append(title, body, copy);
      result.hidden = false;
    } catch (error) { showToast("استخراج نشد", error.message, "error"); }
    finally { button.disabled = false; }
  }

  async function inspectMediaLink(event) {
    event.preventDefault(); const input = $("#linkInspectUrl"); const button = $('button[type="submit"]', event.currentTarget); button.disabled = true;
    try {
      const response = await apiRequest("/api/link/inspect", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: input.value.trim() }) });
      const data = await response.json(); const report = data.report; const result = $("#linkInspectionResult"); result.hidden = false; result.className = `link-inspection-result ${report.risk_level === "کم" ? "low" : report.risk_level === "متوسط" ? "medium" : "high"}`;
      result.replaceChildren(); const head = document.createElement("b"); head.textContent = `ریسک ${report.risk_level} · ${fa.format(report.risk_score)}/۱۰۰`;
      const domain = document.createElement("p"); domain.textContent = `دامنه: ${report.host} · HTTPS: ${report.scheme === "https" ? "بله" : "خیر"}`; result.append(head, domain);
      report.signals.forEach(signal => { const line = document.createElement("p"); line.textContent = `• ${signal}`; result.appendChild(line); });
    } catch (error) { showToast("بررسی نشد", error.message, "error"); }
    finally { button.disabled = false; }
  }

  function renderMusicItems(items, targetSel) {
    const container = targetSel ? $(targetSel) : $("#musicResults"); if (!container) return;
    container.replaceChildren();
    if (!items || !items.length) { container.innerHTML = "<p>آهنگی پیدا نشد؛ نام دیگری را امتحان کن.</p>"; return; }
    items.slice(0, 8).forEach(item => {
      const card = document.createElement("div");
      card.className = "music-item";
      const dur = item.duration ? `${Math.floor(item.duration / 60)}:${String(item.duration % 60).padStart(2, "0")}` : "";
      const badge = item.badge || (item.source === "audius" ? "🎧 آدیوس" : "▶️ یوتیوب");
      const meta = document.createElement("p");
      meta.innerHTML = `<b>${escapeHtml(item.title || "")}</b><br><small>${escapeHtml(item.artist || "")}${dur ? " · " + dur : ""} · ${escapeHtml(badge)}${item.is_preview ? " · پیش‌نمایش ۳۰ ثانیه" : ""}</small>`;
      card.appendChild(meta);
      if (item.stream_url) {
        const audio = document.createElement("audio");
        audio.controls = true; audio.preload = "none";
        audio.src = item.stream_url;
        card.appendChild(audio);
        const tip = document.createElement("small");
        tip.textContent = item.is_preview ? "پیش‌نمایش رسمی ۳۰ ثانیه‌ای — نسخهٔ کامل از داخل ربات دانلود می‌شود." : "پخش مستقیم نسخهٔ کامل.";
        tip.style.opacity = "0.7";
        card.appendChild(tip);
      }
      const link = document.createElement("a");
      link.className = "btn btn-accent btn-mini";
      link.target = "_blank";
      link.href = `https://t.me/Ajorparehbot?start=song_${encodeURIComponent(item.download_query || item.title || "")}`;
      link.textContent = "⬇ دانلود در ربات";
      card.appendChild(link);
      container.appendChild(card);
    });
  }

  async function loadMusicSearch(query) {
    const container = $("#musicResults"); if (!container) return;
    if (!tgCandidate?.initData) { container.innerHTML = "<p>برای جستجوی واقعی، Mini App را از داخل @Ajorparehbot باز کن.</p>"; return; }
    container.innerHTML = "<p>در حال جستجو...</p>";
    try {
      const response = await apiRequest(`/api/music/search?q=${encodeURIComponent(query)}`);
      const data = await response.json();
      if (!data.ok) throw new Error(data.message || "search failed");
      renderMusicItems(data.items);
    } catch (error) { container.innerHTML = `<p>جستجو ناموفق بود: ${escapeHtml(error.message || "")}</p>`; }
  }

  async function loadMusicTrending() {
    const container = $("#musicResults"); if (!container) return;
    if (!tgCandidate?.initData) { container.innerHTML = "<p>برای مشاهده ترندها، Mini App را از داخل @Ajorparehbot باز کن.</p>"; return; }
    container.innerHTML = "<p>در حال دریافت ترندها...</p>";
    try {
      const response = await apiRequest("/api/music/trending");
      const data = await response.json();
      if (!data.ok) throw new Error(data.message || "trending failed");
      renderMusicItems(data.items);
    } catch (error) { container.innerHTML = `<p>دریافت ترندها ناموفق بود: ${escapeHtml(error.message || "")}</p>`; }
  }

  async function loadMusicRegion(region, containerSel = "#musicTrendingResults") {
    const container = $(containerSel); if (!container) return;
    if (!tgCandidate?.initData) { container.innerHTML = "<p>برای مشاهدهٔ موسیقی ایرانی، Mini App را از داخل @Ajorparehbot باز کن.</p>"; return; }
    container.innerHTML = "<p>در حال دریافت موزیک ایرانی...</p>";
    try {
      const response = await apiRequest(`/api/music/trending?region=${encodeURIComponent(region)}`);
      const data = await response.json();
      if (!data.ok) throw new Error(data.message || "iranian music failed");
      renderMusicItems(data.items, containerSel);
    } catch (error) { container.innerHTML = `<p>دریافت موسیقی ایرانی ناموفق بود: ${escapeHtml(error.message || "")}</p>`; }
  }

  async function loadMusicListen() {
    const container = $("#musicResults"); if (!container) return;
    if (!tgCandidate?.initData) { container.innerHTML = "<p>برای گوش دادن آنلاین، Mini App را از داخل @Ajorparehbot باز کن.</p>"; return; }
    container.innerHTML = "<p>در حال دریافت ترندها برای پخش آنلاین…</p>";
    try {
      const response = await apiRequest("/api/music/trending");
      const data = await response.json();
      if (!data.ok) throw new Error(data.message || "trending failed");
      const items = (data.items || []).filter(i => i.stream_url);
      if (!items.length) { container.innerHTML = "<p>آهنگ قابل پخشی پیدا نشد؛ دوباره تلاش کن.</p>"; return; }
      container.replaceChildren();
      const title = document.createElement("p");
      title.className = "music-listen-title";
      title.textContent = "🎧 آهنگ‌های ترند — همین حالا گوش کن:";
      container.appendChild(title);
      items.slice(0, 6).forEach((item, index) => {
        const card = document.createElement("div");
        card.className = "music-item";
        const meta = document.createElement("p");
        meta.innerHTML = `<b>${index + 1}. ${escapeHtml(item.title || "")}</b><br><small>${escapeHtml(item.artist || "")}${item.is_preview ? " · پیش‌نمایش ۳۰ ثانیه" : ""} · ${escapeHtml(item.badge || "")}</small>`;
        card.appendChild(meta);
        const audio = document.createElement("audio");
        audio.controls = true; audio.preload = "none";
        audio.src = item.stream_url;
        card.appendChild(audio);
        if (item.download_query) {
          const link = document.createElement("a");
          link.className = "btn btn-accent btn-mini";
          link.target = "_blank";
          link.href = `https://t.me/Ajorparehbot?start=song_${encodeURIComponent(item.download_query)}`;
          link.textContent = "⬇ دانلود در ربات";
          card.appendChild(link);
        }
        container.appendChild(card);
      });
    } catch (error) { container.innerHTML = `<p>دریافت ترندها ناموفق بود: ${escapeHtml(error.message || "")}</p>`; }
  }

  function loadMusicTrendingInto(containerSel) {
    const container = $(containerSel); if (!container) return;
    if (!tgCandidate?.initData) { container.innerHTML = "<p>برای مشاهده ترندها، Mini App را از داخل @Ajorparehbot باز کن.</p>"; return; }
    container.innerHTML = "<p>در حال دریافت ترندها...</p>";
    apiRequest("/api/music/trending").then(r => r.json()).then(data => {
      if (!data.ok) throw new Error(data.message || "trending failed");
      renderMusicItems(data.items, containerSel);
    }).catch(error => { container.innerHTML = `<p>دریافت ترندها ناموفق بود: ${escapeHtml(error.message || "")}</p>`; });
  }
  function renderMusicItemsInto(items, containerSel) {
    const container = $(containerSel); if (!container) return;
    container.replaceChildren();
    if (!items || !items.length) { container.innerHTML = "<p>آهنگی پیدا نشد.</p>"; return; }
    items.slice(0, 8).forEach(item => {
      const card = document.createElement("div");
      card.className = "music-item";
      const dur = item.duration ? `${Math.floor(item.duration / 60)}:${String(item.duration % 60).padStart(2, "0")}` : "";
      const badge = item.badge || (item.source === "audius" ? "🎧 آدیوس" : "▶️ یوتیوب");
      const meta = document.createElement("p");
      meta.innerHTML = `<b>${escapeHtml(item.title || "")}</b><br><small>${escapeHtml(item.artist || "")}${dur ? " · " + dur : ""} · ${escapeHtml(badge)}${item.is_preview ? " · پیش‌نمایش ۳۰ ثانیه" : ""}</small>`;
      card.appendChild(meta);
      if (item.stream_url) {
        const audio = document.createElement("audio");
        audio.controls = true; audio.preload = "none"; audio.src = item.stream_url;
        card.appendChild(audio);
      }
      if (item.download_query) {
        const link = document.createElement("a");
        link.className = "btn btn-accent btn-mini"; link.target = "_blank";
        link.href = `https://t.me/Ajorparehbot?start=song_${encodeURIComponent(item.download_query)}`;
        link.textContent = "⬇ دانلود در ربات";
        card.appendChild(link);
      }
      container.appendChild(card);
    });
  }
  function setupMusicTabs() {
    $$(".music-tab").forEach(tab => tab.addEventListener("click", () => {
      $$(".music-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      const target = tab.dataset.mtab;
      $("#musicTabSearch").hidden = target !== "search";
      $("#musicTabTrending").hidden = target !== "trending";
      $("#musicTabListen").hidden = target !== "listen";
    }));
    // فرم جستجو (هم‌نام با صفحه رسانه — یکی کافیه)
    $("#musicSearchForm")?.addEventListener("submit", event => {
      event.preventDefault();
      const input = $("#musicSearchInput");
      const query = (input?.value || "").trim();
      if (query.length >= 2) loadMusicSearch(query);
    });
    $("#musicTrendingBtn2")?.addEventListener("click", () => loadMusicTrendingInto("#musicTrendingResults"));
    $("#musicListenBtn2")?.addEventListener("click", () => loadMusicListen());
    $("#musicIranianTrendBtn")?.addEventListener("click", () => {
      $("#musicTabSearch").hidden = true; $("#musicTabListen").hidden = true; $("#musicTabTrending").hidden = false;
      $$(".music-tab").forEach(t => t.classList.toggle("active", t.dataset.mtab === "trending"));
      loadMusicRegion("iranian");
    });
    $("#musicIranianRemixBtn")?.addEventListener("click", () => {
      $("#musicTabSearch").hidden = true; $("#musicTabListen").hidden = true; $("#musicTabTrending").hidden = false;
      $$(".music-tab").forEach(t => t.classList.toggle("active", t.dataset.mtab === "trending"));
      loadMusicRegion("remix");
    });
  }
  function setupMusicCenter() {
    $("#musicTrendingBtn")?.addEventListener("click", loadMusicTrending);
    $("#musicListenBtn")?.addEventListener("click", loadMusicListen);
  }

  function setupMediaCenter() {
    $("#socialDownloadForm")?.addEventListener("submit", event => submitMediaJob(event, "social", "#socialDownloadUrl"));
    $("#instagramCommentForm")?.addEventListener("submit", extractInstagramComment);
    $("#urlUploadForm")?.addEventListener("submit", event => submitMediaJob(event, "direct", "#urlUploadInput"));
    $("#linkInspectForm")?.addEventListener("submit", inspectMediaLink);
    setupMusicCenter();
  }

  function renderAIStatus() {
    if (!aiStatus) return;
    const providers = (aiStatus.providers || []).map(item => ({ gemini: "Gemini", groq: "Groq", cerebras: "Cerebras", openrouter: "OpenRouter" }[item] || item));
    $("#aiProviderLine span").textContent = providers.length ? `فعال: ${providers.join(" ← ")}` : "سرویس متنی در دسترس نیست";
    const quota = aiStatus.quota || {};
    $("#aiTextQuota").textContent = quota.unlimited
      ? "نامحدود"
      : `${fa.format(quota.text_remaining || 0)} پیام باقی‌مانده${quota.text_bonus ? ` · +${fa.format(quota.text_bonus)} هدیه` : ""}`;
    $("#aiImageQuota").textContent = quota.unlimited
      ? "سهمیه مدیریت: نامحدود"
      : `${fa.format(quota.image_remaining || 0)} تصویر از ${fa.format(quota.image_limit || 0)} باقی‌مانده${quota.image_bonus ? ` · +${fa.format(quota.image_bonus)} هدیه` : ""}`;
  }

  async function loadAIStatus() {
    if (!tgCandidate?.initData) {
      $("#aiProviderLine span").textContent = "برای استفاده، Mini App را از داخل @Ajorparehbot باز کن";
      return;
    }
    try {
      const response = await apiRequest("/api/ai/status");
      const data = await response.json(); aiStatus = data.ai; renderAIStatus();
    } catch (error) { $("#aiProviderLine span").textContent = "وضعیت سرویس‌ها دریافت نشد"; }
  }

  async function submitAIText(event) {
    event.preventDefault();
    const prompt = $("#aiPrompt").value.trim();
    if (prompt.length < 2) return;
    const button = $("#aiSubmit");
    button.disabled = true; button.textContent = "در حال فکر کردن...";
    try {
      const response = await apiRequest("/api/ai/text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: aiMode, prompt, history: aiMode === "chat" ? aiHistory : [] }),
      }, 75000);
      const data = await response.json();
      $("#aiOutput").hidden = false;
      $("#aiOutputText").textContent = data.text;
      $("#aiOutputMeta").textContent = `${data.provider || "AI"} · ${fa.format(data.latency_ms || 0)} میلی‌ثانیه`;
      if (aiMode === "chat") {
        aiHistory.push({ role: "user", content: prompt }, { role: "assistant", content: data.text });
        aiHistory = aiHistory.slice(-8);
      }
      haptic("success"); loadAIStatus();
    } catch (error) {
      showToast("پاسخ دریافت نشد", error.name === "AbortError" ? "زمان پاسخ‌گویی تمام شد؛ دوباره تلاش کن." : error.message, "error");
    } finally { button.disabled = false; button.innerHTML = 'ارسال به هوش مصنوعی <svg><use href="#i-send"/></svg>'; }
  }

  async function generateAIImage() {
    const prompt = $("#aiImagePrompt").value.trim();
    if (prompt.length < 3) return showToast("توضیح کوتاهه", "تصویر را کمی دقیق‌تر توصیف کن.", "error");
    const button = $("#aiImageButton"); button.disabled = true; button.textContent = "در حال تصویرسازی...";
    try {
      const response = await apiRequest("/api/ai/image", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt }),
      }, 150000);
      const blob = await response.blob();
      if (!blob.type.startsWith("image/")) throw new Error("خروجی تصویر معتبر نیست");
      if (aiImageObjectUrl) URL.revokeObjectURL(aiImageObjectUrl);
      aiImageObjectUrl = URL.createObjectURL(blob);
      $("#aiGeneratedImage").src = aiImageObjectUrl;
      $("#aiImageDownload").href = aiImageObjectUrl;
      $("#aiImageResult").hidden = false;
      haptic("success"); loadAIStatus();
    } catch (error) { showToast("تصویر ساخته نشد", error.name === "AbortError" ? "صف تصویر شلوغه؛ دوباره تلاش کن." : error.message, "error"); }
    finally { button.disabled = false; button.textContent = "🎨 ساخت تصویر"; }
  }

  function clearAIConversation() {
    aiHistory = [];
    $("#aiPrompt").value = "";
    $("#aiOutputText").textContent = "";
    $("#aiOutput").hidden = true;
    showToast("گفتگو پاک شد", "حافظه همین نشست حذف شد.");
  }

  async function loadReminders() {
    const list = $("#reminderList");
    if (!tgCandidate?.initData) { list.textContent = "برای یادآور واقعی، Mini App را از داخل ربات باز کن."; return; }
    try {
      const response = await apiRequest("/api/reminders");
      const data = await response.json();
      list.replaceChildren();
      if (!data.items.length) { const p = document.createElement("p"); p.textContent = "یادآور فعالی نداری."; list.appendChild(p); return; }
      data.items.forEach(item => {
        const row = document.createElement("article"); row.className = "reminder-item";
        const copy = document.createElement("div"); const title = document.createElement("b"); const time = document.createElement("small");
        title.textContent = item.text; time.textContent = `🕒 ${item.display_time}`; copy.append(title, time);
        const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "حذف";
        remove.addEventListener("click", async () => { remove.disabled = true; try { await apiRequest(`/api/reminders/${encodeURIComponent(item.id)}`, { method: "DELETE" }); row.remove(); showToast("حذف شد", "یادآور لغو شد."); } catch (error) { remove.disabled = false; showToast("حذف نشد", error.message, "error"); } });
        row.append(copy, remove); list.appendChild(row);
      });
    } catch (error) { list.textContent = "یادآورها فعلاً در دسترس نیستند."; }
  }

  async function submitReminder(event) {
    event.preventDefault();
    const text = $("#reminderText").value.trim(); const scheduledAt = $("#reminderTime").value;
    const button = $('button[type="submit"]', event.currentTarget); button.disabled = true;
    try {
      await apiRequest("/api/reminders", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, scheduled_at: scheduledAt }) });
      event.currentTarget.reset(); setReminderMinimum(); await loadReminders(); haptic("success"); showToast("یادآور ثبت شد", "در زمان انتخاب‌شده از ربات پیام می‌گیری.");
    } catch (error) { showToast("ثبت نشد", error.message, "error"); }
    finally { button.disabled = false; }
  }

  function setReminderMinimum() {
    const input = $("#reminderTime"); if (!input) return;
    const date = new Date(Date.now() + 2 * 60 * 1000); const pad = value => String(value).padStart(2, "0");
    const localValue = `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
    input.min = localValue; if (!input.value) input.value = localValue;
  }

  function setupAI() {
    $$('[data-ai-mode]').forEach(button => button.addEventListener("click", () => {
      aiMode = button.dataset.aiMode; $$('[data-ai-mode]').forEach(item => item.classList.toggle("active", item === button));
      if (aiMode !== "chat") aiHistory = [];
      haptic("light");
    }));
    $("#aiTextForm")?.addEventListener("submit", submitAIText);
    $("#aiClear")?.addEventListener("click", clearAIConversation);
    $("#aiCopy")?.addEventListener("click", async () => { try { await navigator.clipboard.writeText($("#aiOutputText").textContent); showToast("کپی شد", "پاسخ در کلیپ‌بورد قرار گرفت."); } catch (_) { showToast("کپی نشد", "متن را دستی انتخاب کن.", "error"); } });
    $("#aiImageButton")?.addEventListener("click", generateAIImage);
    $("#reminderForm")?.addEventListener("submit", submitReminder);
    setReminderMinimum(); loadAIStatus(); loadReminders();
  }

  function telegramProfileDefaults() {
    const user = tgCandidate?.initDataUnsafe?.user;
    const fullName = [user?.first_name, user?.last_name].filter(Boolean).join(" ").trim();
    return {
      user_id: user?.id || null,
      display_name: fullName || "میم‌بازِ ناشناس",
      username: user?.username || null,
      bio: "میم‌باز رسمی Ajorpareh ⚡",
      avatar: user?.photo_url || "assets/ajor-mascot.png",
      has_custom_avatar: false,
    };
  }

  function profileStorageKey() {
    return `ajor_profile_${telegramProfileDefaults().user_id || "guest"}`;
  }

  function applyProfile(profile) {
    profileState = { ...telegramProfileDefaults(), ...profile };
    const avatar = profileState.avatar || "assets/ajor-mascot.png";
    $("#profile-title").textContent = profileState.display_name;
    $("#profileUsername").textContent = profileState.username ? `@${profileState.username}` : "کاربر تلگرام";
    $("#profileBio").textContent = profileState.bio || "میم‌باز رسمی Ajorpareh ⚡";
    $("#profileAvatarImage").src = avatar;
    $("#profileAvatarWrap").classList.toggle("custom-avatar", avatar !== "assets/ajor-mascot.png");
    try { localStorage.setItem(profileStorageKey(), JSON.stringify(profileState)); } catch (_) {}
  }

  async function loadProfile() {
    const defaults = telegramProfileDefaults();
    try {
      const cached = JSON.parse(localStorage.getItem(profileStorageKey()) || "null");
      applyProfile(cached ? { ...defaults, ...cached, username: defaults.username || cached.username } : defaults);
    } catch (_) { applyProfile(defaults); }
    if (!tgCandidate?.initData) return;
    try {
      const response = await fetch("/api/profile", { headers: { "X-Telegram-Init-Data": tgCandidate.initData } });
      if (!response.ok) throw new Error(`profile ${response.status}`);
      const data = await response.json();
      if (data.profile) applyProfile(data.profile);
    } catch (error) { console.warn("Profile sync unavailable", error); }
  }

  function openProfileEditor() {
    const modal = $("#profileEditModal");
    const defaults = telegramProfileDefaults();
    pendingAvatarData = null;
    resetAvatarRequested = false;
    $("#profileNameInput").value = profileState?.display_name || defaults.display_name;
    $("#profileBioInput").value = profileState?.bio || defaults.bio;
    $("#profileBioCount").textContent = fa.format($("#profileBioInput").value.length);
    $("#avatarPreview").src = profileState?.avatar || defaults.avatar;
    $("#profileSyncStatus").textContent = tgCandidate?.initData ? "پروفایل با حساب تلگرام Mini App همگام می‌شود." : "در مرورگر ذخیره می‌شود؛ داخل تلگرام همگام‌سازی کامل فعال است.";
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function closeProfileEditor() {
    const modal = $("#profileEditModal");
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  function resizeAvatar(file) {
    return new Promise((resolve, reject) => {
      if (!file.type.match(/^image\/(png|jpeg|webp)$/) || file.size > 4 * 1024 * 1024) {
        reject(new Error("فقط تصویر PNG، JPG یا WebP تا ۴ مگابایت مجاز است.")); return;
      }
      const reader = new FileReader();
      reader.onerror = () => reject(new Error("خواندن تصویر ممکن نشد."));
      reader.onload = () => {
        const image = new Image();
        image.onerror = () => reject(new Error("تصویر معتبر نیست."));
        image.onload = () => {
          const size = 256;
          const canvas = document.createElement("canvas"); canvas.width = size; canvas.height = size;
          const context = canvas.getContext("2d");
          const crop = Math.min(image.width, image.height);
          const sx = (image.width - crop) / 2; const sy = (image.height - crop) / 2;
          context.drawImage(image, sx, sy, crop, crop, 0, 0, size, size);
          resolve(canvas.toDataURL("image/jpeg", .82));
        };
        image.src = reader.result;
      };
      reader.readAsDataURL(file);
    });
  }

  async function saveProfile(event) {
    event.preventDefault();
    const button = $('button[type="submit"]', event.currentTarget);
    const displayName = $("#profileNameInput").value.trim();
    const bio = $("#profileBioInput").value.trim();
    if (!displayName) return;
    button.disabled = true; button.textContent = "در حال ذخیره...";
    const localProfile = {
      ...profileState,
      display_name: displayName.slice(0, 50),
      bio: bio.slice(0, 120),
      avatar: resetAvatarRequested ? telegramProfileDefaults().avatar : (pendingAvatarData || profileState?.avatar),
      has_custom_avatar: resetAvatarRequested ? false : Boolean(pendingAvatarData || profileState?.has_custom_avatar),
    };
    try {
      if (tgCandidate?.initData) {
        const payload = { display_name: localProfile.display_name, bio: localProfile.bio, reset_avatar: resetAvatarRequested };
        if (pendingAvatarData) payload.avatar_data = pendingAvatarData;
        const response = await fetch("/api/profile", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": tgCandidate.initData },
          body: JSON.stringify(payload),
        });
        if (!response.ok) throw new Error(await response.text());
        const data = await response.json(); applyProfile(data.profile || localProfile);
      } else applyProfile(localProfile);
      haptic("success"); showToast("پروفایل ذخیره شد", "اسم، بیو و تصویرت بروزرسانی شد."); closeProfileEditor();
    } catch (error) {
      console.error("Profile save failed", error);
      showToast("ذخیره نشد", "ارتباط با سرور برقرار نشد؛ دوباره تلاش کن.", "error");
    } finally { button.disabled = false; button.innerHTML = 'ذخیره پروفایل <svg><use href="#i-check"/></svg>'; }
  }

  function renderWallet() {
    if (!walletState) return;
    points = walletState.points;
    $("#walletPoints").textContent = fa.format(walletState.points);
    $("#walletCoins").textContent = fa.format(walletState.coins || 0);
    $("#profilePoints").textContent = fa.format(walletState.points);
    $("#profileLevel").textContent = `LV.${fa.format(walletState.level || 1)}`;
    $("#profileGames").textContent = fa.format(walletState.games_played || 0);
    $("#profileWinRate").textContent = `${fa.format(walletState.win_rate || 0)}٪`;
    $("#profileStreak").textContent = fa.format(walletState.streak || 0);
    $("#profileRank").textContent = `#${fa.format(walletState.rank || 1)}`;
    $("#heroLevel").textContent = fa.format(walletState.level || 1);
    $("#heroPoints").textContent = `${fa.format(walletState.points)} XP`;
    $("#heroStreak").textContent = `${fa.format(walletState.streak || 0)} روز`;
    $("#heroRank").textContent = `#${fa.format(walletState.rank || 1)}`;
    $("#heroWinRate").textContent = `${fa.format(walletState.win_rate || 0)}٪`;
    $("#boardMyRank").textContent = `#${fa.format(walletState.rank || 1)}`;
    $("#boardMyPoints").textContent = `${fa.format(walletState.points)} XP`;
    const levelProgress = walletState.points % 500;
    $("#heroProgress").style.width = `${Math.min(100, levelProgress / 5)}%`;
    $("#heroNextLevel").textContent = `تا لِول بعد: ${fa.format(500 - levelProgress)}`;
    $("#profilePointsNote").textContent = walletState.points >= walletState.min_convert_points ? "آماده تبدیل به تومان" : `${fa.format(walletState.min_convert_points - walletState.points)} امتیاز تا امکان تبدیل`;
    $("#walletToman").textContent = fa.format(walletState.wallet_toman);
    $("#walletReferrals").textContent = fa.format(walletState.referral_count);
    $("#conversionInfo").textContent = `حداقل ${fa.format(walletState.min_convert_points)} امتیاز؛ هر امتیاز ${fa.format(walletState.point_toman_rate)} تومان.`;
    $("#convertPoints").min = walletState.min_convert_points;
    if (Number($("#convertPoints").value) < walletState.min_convert_points) $("#convertPoints").value = walletState.min_convert_points;
    $("#withdrawAmount").min = walletState.min_withdraw_toman;
    $("#withdrawAmount").placeholder = `حداقل ${fa.format(walletState.min_withdraw_toman)}`;
    $("#referralLink").textContent = walletState.invite_url;
    const pending = $("#pendingWithdrawals");
    if (walletState.pending?.length) {
      pending.hidden = false;
      pending.innerHTML = `<b>⏳ درخواست‌های در انتظار</b><br>${walletState.pending.map(item => `#${escapeHTML(item.id)} · ${fa.format(item.amount_toman)} تومان · ${item.method === "usdt" ? "USDT" : "کارت"}`).join("<br>")}`;
    } else pending.hidden = true;
    updateConversionPreview(); updateUsdtPreview();
    $$('[data-points]').forEach(el => el.textContent = fa.format(walletState.points));
  }

  function updateConversionPreview() {
    if (!walletState) return;
    const points = Math.max(0, Number($("#convertPoints")?.value || 0));
    $("#conversionPreview").textContent = `${fa.format(points * walletState.point_toman_rate)} تومان`;
  }

  function updateUsdtPreview() {
    if (!walletState) return;
    const amount = Math.max(0, Number($("#withdrawAmount")?.value || 0));
    $("#usdtPreview").textContent = walletState.usdt_toman_rate > 0 ? `${(amount / walletState.usdt_toman_rate).toFixed(2)} USDT` : "نرخ تتر هنوز تنظیم نشده";
  }

  async function loadWallet() {
    const guest = $("#walletGuest");
    if (!tgCandidate?.initData) { guest.hidden = false; return; }
    guest.hidden = true;
    try {
      const response = await fetch("/api/wallet", { headers: { "X-Telegram-Init-Data": tgCandidate.initData } });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json(); walletState = data.wallet; renderWallet(); if (clubState) { clubState.coins = walletState.coins || 0; renderRewardsClub(); }
    } catch (error) { console.error("Wallet load failed", error); showToast("کیف پول لود نشد", "دوباره تلاش کن.", "error"); }
  }

  async function convertWalletPoints() {
    if (!walletState || !tgCandidate?.initData) return showToast("داخل تلگرام باز کن", "تبدیل امتیاز فقط داخل Mini App فعال است.", "error");
    const points = Number($("#convertPoints").value || 0);
    try {
      const response = await fetch("/api/wallet/convert", { method: "POST", headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": tgCandidate.initData }, body: JSON.stringify({ points }) });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json(); walletState = data.wallet; renderWallet(); haptic("success"); burstConfetti(); showToast("تبدیل انجام شد", `${fa.format(data.amount_toman)} تومان به کیف پول اضافه شد.`);
    } catch (error) { showToast("تبدیل انجام نشد", String(error.message).includes("enough") ? "امتیاز کافی نداری." : "مقدار را بررسی کن.", "error"); }
  }

  async function submitWithdrawal(event) {
    event.preventDefault();
    if (!walletState || !tgCandidate?.initData) return showToast("داخل تلگرام باز کن", "برداشت فقط داخل Mini App فعال است.", "error");
    const method = $("#withdrawMethod").value;
    const payload = { method, amount_toman: Number($("#withdrawAmount").value || 0), card_holder: $("#cardHolder").value, card_number: $("#cardNumber").value, wallet_address: $("#walletAddress").value };
    const button = $('button[type="submit"]', event.currentTarget); button.disabled = true;
    try {
      const response = await fetch("/api/wallet/withdraw", { method: "POST", headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": tgCandidate.initData }, body: JSON.stringify(payload) });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json(); walletState = data.wallet; renderWallet(); event.currentTarget.reset(); $("#usdtFields").hidden = true; $("#cardFields").hidden = false; haptic("success"); showToast(`درخواست #${data.withdrawal_id} ثبت شد`, data.message);
    } catch (error) { console.error(error); showToast("برداشت ثبت نشد", "موجودی، مبلغ یا اطلاعات مقصد را بررسی کن.", "error"); }
    finally { button.disabled = false; }
  }

  function setupWallet() {
    $("#walletRefresh")?.addEventListener("click", loadWallet);
    $("#convertPoints")?.addEventListener("input", updateConversionPreview);
    $("#convertPointsButton")?.addEventListener("click", convertWalletPoints);
    $("#withdrawAmount")?.addEventListener("input", updateUsdtPreview);
    $("#withdrawMethod")?.addEventListener("change", event => { const usdt = event.target.value === "usdt"; $("#cardFields").hidden = usdt; $("#usdtFields").hidden = !usdt; updateUsdtPreview(); });
    $("#withdrawForm")?.addEventListener("submit", submitWithdrawal);
    $("#copyReferral")?.addEventListener("click", async () => { if (!walletState) return; try { await navigator.clipboard.writeText(walletState.invite_url); } catch (_) {} showToast("کپی شد", "لینک دعوت آماده ارسال است."); });
    $("#shareReferral")?.addEventListener("click", () => { if (walletState) share(`با لینک من وارد Ajorpareh شو و بازی کن!\n${walletState.invite_url}`); });
    loadWallet();
  }

  function requestId(prefix) {
    const value = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    return `${prefix}-${value}`;
  }

  async function economyPost(path, payload) {
    if (!tgCandidate?.initData) throw new Error("Mini App را از داخل ربات باز کن");
    const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": tgCandidate.initData }, body: JSON.stringify(payload) });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  }

  function renderMissions() {
    const container = $("#missionList");
    if (!container || !clubState) return;
    container.replaceChildren();
    const missions = clubState.missions || [];
    const completedCount = missions.filter(item => item.completed).length;
    if ($("#heroMissionSummary")) $("#heroMissionSummary").textContent = missions.length ? `${fa.format(completedCount)} از ${fa.format(missions.length)} کامل` : "فعلاً مأموریتی نیست";
    if (!missions.length) { const p = document.createElement("p"); p.textContent = "فعلاً مأموریتی فعال نیست."; container.appendChild(p); return; }
    missions.forEach(item => {
      const card = document.createElement("article"); card.className = `mission-card${item.completed ? " done" : ""}${item.claimed ? " claimed" : ""}`;
      const head = document.createElement("div"); const title = document.createElement("h3"); const reward = document.createElement("span");
      title.textContent = item.title; reward.className = "mission-reward"; reward.textContent = `${fa.format(item.points)} XP${item.coins ? ` + ${fa.format(item.coins)} سکه` : ""}`; head.append(title, reward);
      const description = document.createElement("p"); description.textContent = item.description || "";
      const progress = document.createElement("div"); progress.className = "mission-progress"; const bar = document.createElement("i"); bar.style.width = `${Math.min(100, (item.progress / Math.max(1,item.target))*100)}%`; progress.appendChild(bar);
      const foot = document.createElement("div"); foot.className = "mission-foot"; const count = document.createElement("small"); count.textContent = `${fa.format(item.progress)} از ${fa.format(item.target)}`;
      const claim = document.createElement("button"); claim.type = "button"; claim.textContent = item.claimed ? "گرفته شد" : item.completed ? "دریافت جایزه" : "هنوز کامل نشده"; claim.disabled = item.claimed || !item.completed;
      claim.addEventListener("click", async () => { claim.disabled = true; try { const data = await economyPost("/api/mission/claim", { mission_id: item.id }); clubState.missions = data.missions; clubState.coins = data.coin_balance; renderRewardsClub(); showToast("جایزه مأموریت", `+${fa.format(data.points)} XP و +${fa.format(data.coins)} سکه`); haptic("success"); } catch (error) { claim.disabled = false; showToast("جایزه دریافت نشد", "پیشرفت مأموریت را بروزرسانی کن.", "error"); } });
      foot.append(count, claim); card.append(head, description, progress, foot); container.appendChild(card);
    });
  }

  function renderRewardsClub() {
    if (!clubState) return;
    $("#clubCoins").textContent = fa.format(clubState.coins);
    $("#economyMultiplier").textContent = `ضریب اقتصاد: ${clubState.reward_multiplier}×`;
    $("#spinHint").textContent = clubState.free_spin ? "اولین چرخش امروز رایگانه." : `چرخش بعدی ${fa.format(clubState.paid_spin_cost)} سکه هزینه دارد.`;
    renderMissions();
    $("#shopGrid").innerHTML = clubState.shop.map(item => `<article class="shop-item"><span>${escapeHTML(item.emoji)}</span><div><b>${escapeHTML(item.title)}</b><small>${fa.format(item.price)} سکه</small></div><button data-shop-buy="${item.id}" ${item.owned && item.kind === "badge" ? "disabled" : ""}>${item.owned && item.kind === "badge" ? "خریده شده" : "خرید"}</button></article>`).join("");
    $$('[data-shop-buy]').forEach(button => button.onclick = async () => {
      button.disabled = true;
      try { const data = await economyPost("/api/shop/purchase", { item_id: button.dataset.shopBuy, request_id: requestId("shop") }); clubState.coins = data.coins; renderRewardsClub(); showToast("خرید موفق", `${data.item.title} به حسابت اضافه شد.`); haptic("success"); }
      catch (error) { button.disabled = false; showToast("خرید نشد", error.message.includes("enough") ? "سکه کافی نداری." : "دوباره تلاش کن.", "error"); }
    });
    $("#raffleList").innerHTML = clubState.raffles.length ? clubState.raffles.map(item => `<article class="club-entry"><b>🎡 ${escapeHTML(item.title)}</b><p>${fa.format(item.cost)} سکه · ${fa.format(item.entries)} ورودی</p><div class="club-entry-actions"><button data-raffle-join="${item.id}">شرکت</button></div></article>`).join("") : "<p>فعلاً قرعه‌کشی فعالی نیست.</p>";
    $$('[data-raffle-join]').forEach(button => button.onclick = async () => { try { const data = await economyPost("/api/raffle/join", { raffle_id: button.dataset.raffleJoin }); clubState.coins = data.coins; renderRewardsClub(); showToast("ثبت شد", "ورودی قرعه‌کشی خریداری شد."); } catch (error) { showToast("ثبت نشد", "سکه یا ظرفیت را بررسی کن.", "error"); } });
    $("#predictionList").innerHTML = clubState.predictions.length ? clubState.predictions.map(item => `<article class="club-entry"><b>📈 ${escapeHTML(item.question)}</b><p>انتخاب کن؛ مبلغ پیش‌فرض ۲۰ سکه</p><div class="club-entry-actions">${item.options.map((option,index) => `<button data-prediction="${item.id}" data-option="${index}">${escapeHTML(option)}</button>`).join("")}</div></article>`).join("") : "<p>فعلاً پیش‌بینی فعالی نیست.</p>";
    $$('[data-prediction]').forEach(button => button.onclick = async () => { try { const data = await economyPost("/api/prediction/bet", { prediction_id: button.dataset.prediction, option: Number(button.dataset.option), stake: 20 }); clubState.coins = data.coins; renderRewardsClub(); showToast("پیش‌بینی ثبت شد", "اگر درست باشه از استخر جایزه می‌گیری."); } catch (error) { showToast("ثبت نشد", "قبلاً رأی دادی یا سکه کافی نداری.", "error"); } });
  }

  async function loadRewardsClub(force = false) {
    if (clubState && !force) return renderRewardsClub();
    if (!tgCandidate?.initData) { $("#shopGrid").innerHTML = "<p>باشگاه واقعی را از داخل @Ajorparehbot باز کن.</p>"; return; }
    try { const response = await fetch("/api/economy", { headers: { "X-Telegram-Init-Data": tgCandidate.initData } }); if (!response.ok) throw new Error(); const data = await response.json(); clubState = data.economy; renderRewardsClub(); loadLiveLeaderboard(); }
    catch (_) { showToast("باشگاه لود نشد", "دوباره تلاش کن.", "error"); }
  }

  async function spinWheel() {
    const button = $("#spinButton"); button.disabled = true;
    try { const data = await economyPost("/api/spin", { request_id: requestId("spin") }); $("#wheelDisc").style.transform = `rotate(${1440 + Math.random()*720}deg)`; clubState.coins = data.coins; clubState.free_spin = false; setTimeout(() => { renderRewardsClub(); showToast("نتیجه گردونه", data.result.label); if (data.result.coins >= 50) burstConfetti(); }, 2100); }
    catch (error) { showToast("گردونه نچرخید", error.message.includes("enough") ? "سکه کافی نداری." : "دوباره تلاش کن.", "error"); }
    finally { setTimeout(() => { button.disabled = false; }, 2200); }
  }

  async function loadLiveLeaderboard() {
    try { const response = await fetch(`/api/leaderboard?period=${liveBoardPeriod}`); const data = await response.json(); $("#liveLeaderboard").innerHTML = data.items.map((item,index) => `<article><span>${index+1}</span><b>${escapeHTML(item.name)}</b><strong>${fa.format(item.points)}</strong></article>`).join("") || "<p>هنوز رکوردی ثبت نشده.</p>"; }
    catch (_) { $("#liveLeaderboard").innerHTML = "<p>جدول در دسترس نیست.</p>"; }
  }

  async function redeemMiniGift(event) {
    event.preventDefault();
    const code = $("#miniGiftCode").value.trim().toUpperCase();
    if (code.length < 4) return showToast("کد کوتاهه", "کد هدیه معتبر رو وارد کن.", "error");
    const button = $('button[type="submit"]', event.currentTarget); button.disabled = true;
    try {
      const data = await economyPost("/api/gift/redeem", { code });
      if (data.wallet) { walletState = data.wallet; renderWallet(); }
      if (clubState && data.wallet) { clubState.coins = data.wallet.coins || 0; renderRewardsClub(); }
      $("#miniGiftHint").textContent = data.summary;
      event.currentTarget.reset(); haptic("success"); burstConfetti();
      showToast(data.duplicate ? "قبلاً فعال شده" : "هدیه فعال شد!", data.summary);
      loadAIStatus();
    } catch (error) { showToast("کد فعال نشد", "کد نامعتبر، منقضی یا تمام‌شده است.", "error"); }
    finally { button.disabled = false; }
  }

  function setupRewardsClub() {
    $("#spinButton")?.addEventListener("click", spinWheel);
    $("#miniGiftForm")?.addEventListener("submit", redeemMiniGift);
    $("#missionRefresh")?.addEventListener("click", () => loadRewardsClub(true));
    $$('[data-live-board]').forEach(button => button.addEventListener("click", () => { liveBoardPeriod = button.dataset.liveBoard; $$('[data-live-board]').forEach(item => item.classList.toggle("active", item === button)); loadLiveLeaderboard(); }));
    loadRewardsClub();
  }

  function setupProfile() {
    loadProfile();
    $(".edit-profile")?.addEventListener("click", openProfileEditor);
    $(".profile-edit-close")?.addEventListener("click", closeProfileEditor);
    $("#profileEditModal")?.addEventListener("click", event => { if (event.target.id === "profileEditModal") closeProfileEditor(); });
    $("#profileBioInput")?.addEventListener("input", event => $("#profileBioCount").textContent = fa.format(event.target.value.length));
    $("#avatarFile")?.addEventListener("change", async event => {
      const file = event.target.files?.[0]; if (!file) return;
      try { pendingAvatarData = await resizeAvatar(file); resetAvatarRequested = false; $("#avatarPreview").src = pendingAvatarData; }
      catch (error) { showToast("تصویر قبول نشد", error.message, "error"); }
    });
    $("#telegramAvatarReset")?.addEventListener("click", () => {
      pendingAvatarData = null; resetAvatarRequested = true; $("#avatarPreview").src = telegramProfileDefaults().avatar;
    });
    $("#profileEditForm")?.addEventListener("submit", saveProfile);
    document.addEventListener("keydown", event => { if (event.key === "Escape" && $("#profileEditModal")?.classList.contains("open")) closeProfileEditor(); });
  }

  function setupSettings() {
    const hapticsToggle = $("#hapticsToggle");
    if (hapticsToggle) {
      hapticsToggle.checked = hapticsEnabled;
      hapticsToggle.addEventListener("change", () => {
        hapticsEnabled = hapticsToggle.checked;
        try { localStorage.setItem("ajor_haptics", hapticsEnabled ? "on" : "off"); } catch (_) {}
        if (hapticsEnabled) haptic("light");
        showToast("تنظیمات ذخیره شد", hapticsEnabled ? "لرزش روشن شد." : "لرزش خاموش شد.");
      });
    }
    $("#fullscreenButton")?.addEventListener("click", () => {
      if (!tg || typeof tg.requestFullscreen !== "function") return showToast("پشتیبانی نمی‌شود", "تلگرام را به آخرین نسخه بروزرسانی کن.", "error");
      try { tg.requestFullscreen(); } catch (_) { showToast("تمام‌صفحه نشد", "دوباره تلاش کن.", "error"); }
    });
    const homeButton = $("#homeScreenButton");
    homeButton?.addEventListener("click", () => {
      if (!tg || typeof tg.addToHomeScreen !== "function") return showToast("پشتیبانی نمی‌شود", "این نسخه تلگرام میانبر صفحه اصلی ندارد.", "error");
      try { tg.addToHomeScreen(); } catch (_) { showToast("اضافه نشد", "از تنظیمات تلگرام دوباره تلاش کن.", "error"); }
    });
    if (tg && typeof tg.checkHomeScreenStatus === "function") {
      try { tg.checkHomeScreenStatus(status => { const label = $("#homeScreenStatus"); if (label) label.textContent = status === "added" ? "به صفحه اصلی اضافه شده" : "دسترسی سریع بدون بازکردن چت"; }); } catch (_) {}
    }
  }

  function setupCarouselDrag() {
    const carousel = $("#gameCarousel");
    let down = false, dragged = false, startX = 0, startScroll = 0;
    carousel.addEventListener("pointerdown", event => {
      down = true;
      dragged = false;
      startX = event.clientX;
      startScroll = carousel.scrollLeft;
    });
    carousel.addEventListener("pointermove", event => {
      if (!down || Math.abs(event.clientX - startX) <= 6) return;
      dragged = true;
      carousel.scrollLeft = startScroll - (event.clientX - startX);
    });
    carousel.addEventListener("pointerup", () => { down = false; });
    carousel.addEventListener("pointercancel", () => { down = false; dragged = false; });
    carousel.addEventListener("click", event => {
      if (!dragged) return;
      event.preventDefault();
      event.stopPropagation();
      dragged = false;
    }, true);
  }

  function boot() {
    setupTelegram();
    $("#welcomeClose")?.addEventListener("click", closeWelcomePop);
    setupNavigation();
    setupBotActions();
    setupTelegramLinks();
    setupDailyContext();
    setupCountdown();
    loadChannelPosts();
    setupGames();
    setupShares();
    setupChallenges();
    setupNews();
    setupLeaderboard();
    setupSupport();
    setupProfile();
    setupWallet();
    setupRewardsClub();
    setupMediaCenter();
  setupCalendar();
    setupAI();
    setupSettings();
    setupCarouselDrag();

    const preloader = $("#preloader");
    const app = $("#appShell");
    const delay = matchMedia("(prefers-reduced-motion: reduce)").matches ? 80 : 1050;
    setTimeout(() => {
      preloader.classList.add("done");
      app.classList.add("ready");
      setTimeout(showWelcomePop, 180);
    }, delay);
  }

  async function loadShop() {
    const container = $("#shopCatalog");
    if (!container) return;
    container.innerHTML = "<p>در حال بارگذاری سرویس‌ها...</p>";
    try {
      const headers = { Accept: "application/json" };
      if (tgCandidate?.initData) headers["X-Telegram-Init-Data"] = tgCandidate.initData;
      const response = await fetch("/api/shop/services", { headers });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const data = await response.json();
      const rateEl = $("#shopStarRate");
      if (rateEl && data.rate_toman) rateEl.textContent = fa.format(data.rate_toman) + " تومان";
      const services = data.services || [];
      if (!services.length) { container.innerHTML = "<p>فعلاً سرویسی موجود نیست.</p>"; return; }
      container.innerHTML = services.map(service => `
        <section class="club-panel">
          <div class="section-heading compact">
            <div><span>${service.emoji || "🛒"} ${service.title}</span><h2>${service.app || ""}</h2></div>
          </div>
          <div class="service-plans">
            ${service.plans.map(plan => `
              <button class="btn btn-accent service-buy" type="button" data-buy="${service.type}|${plan.months}">
                ${plan.months} ماهه · ${fa.format(plan.stars)} ⭐
              </button>`).join("")}
          </div>
        </section>`).join("");
      $$(".service-buy").forEach(button => button.addEventListener("click", () => buyWithStars(button.dataset.buy)));
    } catch (error) {
      container.innerHTML = "<p>❌ خطا در دریافت سرویس‌ها. دوباره تلاش کن.</p>";
      console.warn("Shop load failed", error);
    }
  }

  async function buyWithStars(key) {
    const [serviceType, months] = key.split("|");
    try {
      const headers = { "Content-Type": "application/json" };
      if (tgCandidate?.initData) headers["X-Telegram-Init-Data"] = tgCandidate.initData;
      const response = await fetch("/api/shop/stars-invoice", {
        method: "POST", headers, body: JSON.stringify({ service_type: serviceType, months: Number(months) })
      });
      if (!response.ok) {
        let detail = "خطا در ساخت فاکتور";
        try { const err = await response.json(); detail = err.error || err.detail || detail; } catch (e) { /* ignore */ }
        showToast("❌ " + detail, "دوباره تلاش کن.", "error");
        return;
      }
      const data = await response.json();
      if (!data.invoice_url) { showToast("❌ لینک پرداخت ساخته نشد", "دوباره تلاش کن.", "error"); return; }
      if (window.Telegram?.WebApp?.openInvoice) {
        window.Telegram.WebApp.openInvoice(data.invoice_url, status => {
          if (status === "paid") {
            showToast("🎉 پرداخت با ستاره موفق شد!", "سفارش در انتظار تحویل توسط مدیر است.");
          } else if (status === "cancelled") {
            showToast("پرداخت لغو شد", "هر وقت خواستی دوباره تلاش کن.", "error");
          } else if (status === "failed") {
            showToast("❌ پرداخت ناموفق بود", "دوباره تلاش کن.", "error");
          }
        });
      } else {
        window.open(data.invoice_url, "_blank");
      }
    } catch (error) {
      showToast("❌ خطا: " + String(error.message || error), "دوباره تلاش کن.", "error");
    }
  }

  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
