# معماری گیمیفیکیشن، Tokenomics و Referral در Ajorpareh

## 1) مدل دو دارایی

- `xp`: امتیاز رتبه‌بندی و دارایی قابل تبدیل به تومان طبق سیاست فعلی پنل.
- `coins`: سکه مصرفی داخل اکوسیستم؛ برای گردونه، فروشگاه، قرعه‌کشی و پیش‌بینی.
- `wallet_toman`: مانده تسویه‌پذیر؛ فقط با تبدیل XP و تراکنش ثبت‌شده زیاد می‌شود.

جداکردن XP و Coin باعث می‌شود هزینه سرگرمی مستقیماً بدهی نقدی نسازد.

## 2) منابع دریافت

### ورود روزانه

چرخه پایه ۷ روزه سکه:

```text
[10, 15, 25, 40, 60, 90, 140]
```

استریک بعد از روز هفتم از روز اول چرخه جدید ادامه پیدا می‌کند. ثبت جایزه با کلید یکتای زیر idempotent است:

```text
daily:{telegram_user_id}:{tehran_date}
```

### بازی‌ها

پاداش بازی در سرور محاسبه می‌شود و کلاینت نمی‌تواند عدد پاداش را تعیین کند. حداکثر پنج پاداش از هر بازی در روز و سقف XP روزانه Mini App برابر ۱۰۰۰ است. Coin بازی نیز به ضریب ضدتورم وابسته است.

### رفرال

پس از تکمیل عضویت اجباری و کپچا:

- دعوت‌کننده: ۱۰۰ XP + ۱۰۰ Coin پایه
- دعوت‌شده: ۲۵ XP + ۲۵ Coin پایه

پاداش با شناسه یکتای زیر فقط یک‌بار ثبت می‌شود:

```text
referral:{inviter_id}:{invited_id}
```

### کانال اسپانسر

برای هر کانال اجباری یک کلید یکتای `sponsor:{channel_id}:{user_id}` ثبت می‌شود. مقدار پایه فعلی ۲۰ Coin و از تنظیمات اقتصاد قابل توسعه است.

### پیش‌بینی ترند

کاربر یکی از گزینه‌ها را با ۱۰، ۲۰، ۵۰ یا ۱۰۰ Coin انتخاب می‌کند. بعد از اعلام گزینه برنده، پرداخت به صورت pari-mutuel انجام می‌شود.

## 3) روش‌های مصرف و Burn

- چرخش اضافه گردونه: ۵۰ Coin
- مدال نئون: ۱۸۰ Coin
- مدال پادشاه میم: ۳۵۰ Coin
- بازی ویژه ۷ روزه: ۵۰۰ Coin
- ابزار Pro مدیریت گروه ۳۰ روزه: ۱۲۰۰ Coin
- ورودی قرعه‌کشی: مبلغ تعریف‌شده توسط مدیر
- پیش‌بینی ترند: Stake انتخابی کاربر

هزینه‌ها در `coin_transactions` با `direction=burn` ثبت می‌شوند.

## 4) فرمول ضدتورم

ضریب پرداخت متغیر:

```text
m = clamp(
  (daily_emission_target + burned_24h) /
  max(minted_24h, daily_emission_target, 1),
  min_reward_multiplier,
  1
)

actual_reward = floor(base_reward × m)
```

مقادیر فعلی:

```text
daily_emission_target = 50,000 Coin
min_reward_multiplier = 0.35
daily_coin_cap_per_user = 500 Coin
```

هرچه Mint روزانه از هدف بالاتر برود، ضریب جایزه جدید کم می‌شود. Burn دوباره ظرفیت انتشار سکه ایجاد می‌کند.

شاخص‌های پیشنهادی مانیتورینگ:

```text
net_issuance_24h = minted_24h - burned_24h
burn_ratio_7d = burned_7d / max(minted_7d, 1)
coin_velocity = spent_7d / max(avg_coin_balance_7d, 1)
```

هدف پایدار: `burn_ratio_7d` بین 0.55 تا 0.85.

## 5) احتمال گردونه

| جایزه | احتمال |
|---|---:|
| پوچ | 40% |
| 5 Coin | 25% |
| 10 Coin | 17% |
| 20 Coin | 10% |
| 50 Coin | 5% |
| 100 Coin | 2% |
| 250 Coin | 0.8% |
| 500 Coin | 0.2% |

امید ریاضی جایزه حدود 12.45 Coin است. چرخش پولی 50 Coin هزینه دارد؛ بنابراین امید خالص آن حدود `-37.55 Coin` و یک Burn مؤثر است. اولین چرخش هر روز رایگان است.

## 6) فرمول پیش‌بینی

```text
winner_payout = stake + floor(
  loser_pool × 0.85 × stake / total_winner_stake
)
```

پانزده درصد استخر بازنده‌ها Burn می‌شود. اگر گزینه برنده هیچ شرطی نداشته باشد، کل استخر Burn باقی می‌ماند.

## 7) قرعه‌کشی

هر ورودی یک سند مستقل است. برنده از بین Entryها انتخاب می‌شود؛ بنابراین کاربر دارای ورودی بیشتر، شانس متناسب بیشتری دارد. هفتاد درصد استخر به برنده Mint و سی درصد Burn می‌شود.

## 8) Anti-Cheat رفرال

کنترل‌های پیاده‌شده:

1. جلوگیری از Self-referral.
2. پاداش فقط برای Telegram ID جدید.
3. تکمیل تمام کانال‌های اجباری.
4. تکمیل مرحله تعامل.
5. کپچای ریاضی با انقضای ۱۰ دقیقه.
6. بررسی Username.
7. بررسی وجود تصویر پروفایل به عنوان Risk Signal.
8. تشخیص تکمیل بسیار سریع.
9. کلید یکتای Referral و تراکنش‌های idempotent.
10. گزارش رفرال‌های پرتعداد ۲۴ ساعت اخیر در پنل مالی.

Telegram Bot API تاریخ ساخت حساب را ارائه نمی‌کند؛ بنابراین «سن حساب» مستقیماً قابل تشخیص نیست. از first-seen، Username، تصویر، سرعت تکمیل، کپچا و الگوهای رفرال به‌عنوان سیگنال جایگزین استفاده می‌شود.

## 9) اعتبارسنجی Telegram Mini App

Mini App مقدار `Telegram.WebApp.initData` را در هدر زیر ارسال می‌کند:

```text
X-Telegram-Init-Data
```

سرور:

1. پارامترها را Parse می‌کند.
2. `hash` را جدا می‌کند.
3. `data_check_string` مرتب‌شده می‌سازد.
4. Secret را با HMAC-SHA256 از `WebAppData` و Bot Token می‌سازد.
5. Hash را با `compare_digest` مقایسه می‌کند.
6. `auth_date` قدیمی‌تر از ۲۴ ساعت را رد می‌کند.
7. User ID را فقط از داده امضاشده می‌پذیرد.

هیچ Endpoint مالی به Telegram ID ارسال‌شده توسط کلاینت اعتماد نمی‌کند.

## 10) کالکشن‌های MongoDB

### users

```javascript
{
  _id: TelegramUserId,
  xp: Number,
  coins: Number,
  wallet_toman: Number,
  streak: Number,
  referral_count: Number,
  referred_by: TelegramUserId,
  referral_rewarded: Boolean,
  wallet_frozen: Boolean,
  entitlements: Object,
  badges: [String]
}
```

### coin_transactions

```javascript
{
  _id: String,           // idempotency key
  user_id: Number,
  amount: Number,
  base_amount: Number,
  direction: "mint" | "burn",
  reason: String,
  metadata: Object,
  status: "pending" | "completed" | "failed",
  created_at: Date
}
```

### score_events

```javascript
{
  _id: String,
  user_id: Number,
  points: Number,
  source: String,
  metadata: Object,
  created_at: Date
}
```

### referral_events

```javascript
{
  _id: "referral:inviter:invited",
  referrer_id: Number,
  referred_user_id: Number,
  risk: [String],
  created_at: Date
}
```

### wheel_spins / shop_purchases / raffles / raffle_entries
### trend_predictions / prediction_bets
### wallet_transactions / withdrawals

تمام عملیات دارای کلید یکتا یا شرط Atomic هستند.

## 11) Leaderboard

- Weekly: از ابتدای دوشنبه UTC در `score_events`.
- Monthly: از ابتدای ماه UTC.
- All-time: از `users.xp`.
- فقط ۲۰ نفر اول در API عمومی برگردانده می‌شوند.

برای مقیاس بزرگ‌تر، Snapshot دوره‌ای Leaderboard و Redis Sorted Set پیشنهاد می‌شود.

## 12) Endpointها

```text
GET  /api/economy
POST /api/spin
POST /api/shop/purchase
POST /api/raffle/join
POST /api/prediction/bet
GET  /api/leaderboard?period=weekly|monthly|all
POST /api/game/reward
GET  /api/wallet
POST /api/wallet/convert
POST /api/wallet/withdraw
```

## 13) نقش‌های چندگانه مدیر

هر مدیر دارای آرایه `roles` است و می‌تواند هم‌زمان چند نقش داشته باشد:

```javascript
{
  _id: TelegramUserId,
  roles: ["content", "support", "analyst"],
  active: true
}
```

Permissionهای تمام نقش‌ها Union می‌شوند. مالک از پنل می‌تواند هر نقش را مستقل روشن یا خاموش کند. داده‌های قدیمی دارای فیلد `role` در Startup به `roles[]` مهاجرت می‌کنند.

## 14) مسیر توسعه بعدی

- Redis برای Lock و Leaderboard در چند Replica.
- MongoDB Transaction برای اتمیک کامل Ledger و Balance.
- Risk scoring با Device/IP hash در Privacy Policy روشن.
- Snapshot روزانه اقتصاد و هشدار خودکار هنگام `burn_ratio < 0.4`.
- A/B Testing احتمال گردونه و قیمت فروشگاه، بدون تغییر دستی کد.
