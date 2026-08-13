"""Persian (Jalali/Shamsi) calendar + occasions for Ajorpareh.

Implements:
- Gregorian -> Jalali conversion (jalaali-js algorithm, MIT-licensed, well tested)
- Jalali -> Gregorian (for grid building)
- Islamic (tabular Hijri) dates for lunar occasions (approximate ±1 day)
- A large set of Iranian occasions/holidays keyed by (month, day)
- Helpers for building a month grid and "today" info

All pure Python, no external dependencies.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

JALALI_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]
JALALI_WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]

# ============ الگوریتم تبدیل تاریخ (jalaali-js v1.2.6) ============

_BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210,
           1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178]


def _div(a: int, b: int) -> int:
    return int(a / b)


def _mod(a: int, b: int) -> int:
    return a - int(a / b) * b


def _jal_cal_leap(jy: int) -> int:
    bl = len(_BREAKS)
    jp = _BREAKS[0]
    jump = 0
    if jy < jp or jy >= _BREAKS[bl - 1]:
        raise ValueError(f"Invalid Jalaali year {jy}")
    for i in range(1, bl):
        jm = _BREAKS[i]
        jump = jm - jp
        if jy < jm:
            break
        jp = jm
    n = jy - jp
    if jump - n < 6:
        n = n - jump + _div(jump + 4, 33) * 33
    leap = _mod(_mod(n + 1, 33) - 1, 4)
    if leap == -1:
        leap = 4
    return leap


def _jal_cal(jy: int, without_leap: bool = False) -> dict:
    bl = len(_BREAKS)
    gy = jy + 621
    leap_j = -14
    jp = _BREAKS[0]
    jump = 0
    if jy < jp or jy >= _BREAKS[bl - 1]:
        raise ValueError(f"Invalid Jalaali year {jy}")
    for i in range(1, bl):
        jm = _BREAKS[i]
        jump = jm - jp
        if jy < jm:
            break
        leap_j = leap_j + _div(jump, 33) * 8 + _div(_mod(jump, 33), 4)
        jp = jm
    n = jy - jp
    leap_j = leap_j + _div(n, 33) * 8 + _div(_mod(n, 33) + 3, 4)
    if _mod(jump, 33) == 4 and jump - n == 4:
        leap_j += 1
    leap_g = _div(gy, 4) - _div((_div(gy, 100) + 1) * 3, 4) - 150
    march = 20 + leap_j - leap_g
    if without_leap:
        return {"gy": gy, "march": march}
    if jump - n < 6:
        n = n - jump + _div(jump + 4, 33) * 33
    leap = _mod(_mod(n + 1, 33) - 1, 4)
    if leap == -1:
        leap = 4
    return {"leap": leap, "gy": gy, "march": march}


def _g2d(gy: int, gm: int, gd: int) -> int:
    d = _div((gy + _div(gm - 8, 6) + 100100) * 1461, 4) \
        + _div(153 * _mod(gm + 9, 12) + 2, 5) + gd - 34840408
    d = d - _div(_div(gy + 100100 + _div(gm - 8, 6), 100) * 3, 4) + 752
    return d


def _d2g(jdn: int) -> dict:
    j = 4 * jdn + 139361631
    j = j + _div(_div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908
    i = _div(_mod(j, 1461), 4) * 5 + 308
    gd = _div(_mod(i, 153), 5) + 1
    gm = _mod(_div(i, 153), 12) + 1
    gy = _div(j, 1461) - 100100 + _div(8 - gm, 6)
    return {"gy": gy, "gm": gm, "gd": gd}


def _j2d(jy: int, jm: int, jd: int) -> int:
    r = _jal_cal(jy, True)
    return _g2d(r["gy"], 3, r["march"]) + (jm - 1) * 31 - _div(jm, 7) * (jm - 7) + jd - 1


def _d2j(jdn: int) -> tuple[int, int, int]:
    gy = _d2g(jdn)["gy"]
    jy = gy - 621
    r = _jal_cal(jy, False)
    jdn1f = _g2d(gy, 3, r["march"])
    k = jdn - jdn1f
    if k >= 0:
        if k <= 185:
            jm = 1 + _div(k, 31)
            jd = _mod(k, 31) + 1
            return jy, jm, jd
        k -= 186
    else:
        jy -= 1
        k += 179
        if r["leap"] == 1:
            k += 1
    jm = 7 + _div(k, 30)
    jd = _mod(k, 30) + 1
    return jy, jm, jd


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """تبدیل میلادی به شمسی — خروجی (سال، ماه، روز)."""
    return _d2j(_g2d(gy, gm, gd))


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    """تبدیل شمسی به میلادی."""
    r = _d2g(_j2d(jy, jm, jd))
    return r["gy"], r["gm"], r["gd"]


def jalali_month_length(jy: int, jm: int) -> int:
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    if _jal_cal_leap(jy) == 0:
        return 30
    return 29


def is_leap_jalali(jy: int) -> bool:
    return _jal_cal_leap(jy) == 0


# ============ تقویم قمری (تبدیل تقریبی هجری) ============

def _gregorian_to_jdn(gy: int, gm: int, gd: int) -> int:
    a = (14 - gm) // 12
    y = gy + 4800 - a
    m = gm + 12 * a - 3
    jdn = gd + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    return jdn


def _jdn_to_gregorian(jdn: int) -> tuple[int, int, int]:
    a = jdn + 32044
    b = (4 * a + 3) // 146097
    c = a - (146097 * b) // 4
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    gd = e - (153 * m + 2) // 5 + 1
    gm = m + 3 - 12 * (m // 10)
    gy = 100 * b + d - 4800 + m // 10
    return gy, gm, gd


def gregorian_to_islamic(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """تبدیل میلادی به هجری قمری (تقویم جدولی — تقریبی ±۱ روز)."""
    jdn = _gregorian_to_jdn(gy, gm, gd)
    # فرمول جدولی استاندارد
    l = jdn - 1948440 + 10632
    n = (l - 1) // 10631
    l = l - 10631 * n + 354
    j = ((10985 - l) // 5316) * ((50 * l) // 17719) + (l // 5670) * ((43 * l) // 15238)
    l = l - ((30 - j) // 15) * ((17719 * j) // 50) - (j // 16) * ((15238 * j) // 43) + 29
    m = (24 * l) // 709
    d = l - (709 * m) // 24
    y = 30 * n + j - 30
    return y, m, d


ISLAMIC_MONTHS = [
    "محرم", "صفر", "ربیع‌الاول", "ربیع‌الثانی", "جمادی‌الاول", "جمادی‌الثانی",
    "رجب", "شعبان", "رمضان", "شوال", "ذی‌القعده", "ذی‌الحجه",
]

ISLAMIC_OCCASIONS: dict[tuple[int, int], str] = {
    (1, 1): "سال نو قمری · آغاز محرم",
    (1, 9): "تاسوعای حسینی",
    (1, 10): "عاشورای حسینی",
    (2, 20): "اربعین حسینی",
    (3, 17): "میلاد پیامبر اکرم (ص)",
    (7, 13): "ولادت امام علی (ع)",
    (7, 27): "مبعث رسول اکرم (ص)",
    (8, 15): "ولادت حضرت مهدی (عج) · نیمه شعبان",
    (9, 1): "آغاز ماه مبارک رمضان",
    (9, 19): "ضربت خوردن امام علی (ع) · شب قدر",
    (9, 21): "شهادت امام علی (ع) · شب قدر",
    (9, 23): "شب قدر",
    (9, 27): "شب قدر",
    (10, 1): "عید سعید فطر",
    (10, 2): "تعطیل عید فطر",
    (12, 9): "روز عرفه",
    (12, 10): "عید سعید قربان",
    (12, 18): "عید سعید غدیر خم",
}


# ============ مناسبت‌های شمسی ============

JALALI_OCCASIONS: dict[tuple[int, int], str] = {
    # فروردین
    (1, 1): "🎉 عید نوروز · جشن سال نو",
    (1, 2): "🎉 عید نوروز",
    (1, 3): "🎉 عید نوروز",
    (1, 4): "🎉 تعطیل عید نوروز",
    (1, 12): "🌹 روز جمهوری اسلامی ایران",
    (1, 13): "🌳 سیزده‌به‌در · روز طبیعت",
    (1, 15): "🌹 روز بزرگداشت شیخ بهایی",
    (1, 18): "🎖 روز ارتش جمهوری اسلامی ایران",
    (1, 20): "🌍 روز ملی منابع طبیعی و آبخیزداری",
    (1, 25): "🌹 روز بزرگداشت عطار نیشابوری",
    (1, 29): "🚀 روز ملی فناوری هسته‌ای",
    # اردیبهشت
    (2, 1): "✍️ روز بزرگداشت سعدی",
    (2, 2): "🌍 روز زمین پاک",
    (2, 3): "📚 روز بزرگداشت شیخ کلینی",
    (2, 4): "🍞 روز جهانی کارگر",
    (2, 5): "💎 روز بزرگداشت فیض کاشانی",
    (2, 7): "🧠 روز جهانی فشار خون",
    (2, 8): "👨‍🏫 روز جهانی صلیب سرخ و هلال احمر",
    (2, 12): "👩‍🏫 روز معلم",
    (2, 14): "📷 روز اهدای عضو",
    (2, 15): "🏡 روز شیراز و بزرگداشت سعدی",
    (2, 18): "🧭 روز جهانی موزه و میراث فرهنگی",
    (2, 22): "🌹 روز بزرگداشت فردوسی",
    (2, 25): "🌹 روز بزرگداشت حکیم ابوالقاسم فردوسی · روز پاسداشت زبان فارسی",
    (2, 28): "🏖 روز جهانی بدون دخانیات",
    # خرداد
    (3, 1): "📊 روز بهره‌وری و بهبود مدیریت",
    (3, 3): "🌹 روز جهانی محیط زیست",
    (3, 5): "👨‍🦱 روز جهانی اهداکنندگان خون",
    (3, 14): "🌹 رحلت امام خمینی (ره)",
    (3, 15): "📣 قیام ۱۵ خرداد",
    (3, 21): "📖 روز ملی گل و گیاه",
    (3, 25): "🌹 روز بزرگداشت امام موسی صدر",
    (3, 29): "🌹 سالروز درگذشت دکتر مصدق",
    # تیر
    (4, 1): "🗣 روز تبلیغات و اطلاع‌رسانی",
    (4, 5): "🇺🇸 روز افشای حقوق بشر آمریکایی",
    (4, 7): "🗡 روز جهانی مبارزه با کار کودکان",
    (4, 13): "🏵 روز شهدا",
    (4, 14): "✒️ روز قلم",
    (4, 20): "🌹 روز بزرگداشت علامه امینی",
    (4, 22): "🌹 روز جمهوری اسلامی درگذشت دکتر شریعتی",
    (4, 24): "🤝 روز تعاون",
    (4, 26): "🤲 روز بزرگداشت خلیج فارس؟",
    # مرداد
    (5, 1): "💪 روز مقاومت اسلامی",
    (5, 2): "🌹 روز بزرگداشت شیخ شهاب‌الدین سهروردی",
    (5, 3): "❤️ روز اهدای خون",
    (5, 4): "🚧 روز کارآفرینی و آموزش‌های فنی و حرفه‌ای",
    (5, 5): "🌹 روز بزرگداشت نظامی گنجوی",
    (5, 6): "🇺🇸 روز جهانی قدس",
    (5, 7): "🌹 روز بزرگداشت شمس تبریزی",
    (5, 8): "🌹 روز بزرگداشت شیخ بهایی",
    (5, 10): "👨‍👩‍👧 روز ملی خانواده",
    (5, 12): "🤝 روز تشکل‌ها و مشارکت اجتماعی",
    (5, 14): "📜 روز صدور فرمان مشروطیت · روز مشروطه",
    (5, 15): "🗞 روز خبرنگار",
    (5, 17): "🗞 روز خبرنگار (شهادت محمود صارمی)",
    (5, 18): "📦 روز صادرات",
    (5, 20): "🌹 روز جهانی مساجد",
    (5, 26): "🌹 سالروز بازگشت آزادگان سرافراز به میهن",
    (5, 27): "🌹 روز بزرگداشت شهید چمران",
    # شهریور
    (6, 1): "⚕️ روز بزرگداشت ابوعلی سینا · روز پزشک",
    (6, 2): "🌹 روز بزرگداشت ابوریحان بیرونی",
    (6, 4): "🇵🇸 روز همبستگی با مردم فلسطین",
    (6, 5): "💊 روز داروسازی",
    (6, 8): "🛡 روز ملی مبارزه با تروریسم",
    (6, 10): "🌹 روز بزرگداشت آیت‌الله شهید بهشتی",
    (6, 13): "🤝 روز تعاون",
    (6, 17): "📈 روز ملی آمار و برنامه‌ریزی",
    (6, 20): "🏘 روز ملی تعاون مسکن؟",
    (6, 26): "🚦 روز ملی حمل و نقل",
    (6, 27): "🚲 روز ملی جمعیت",
    (6, 31): "🕌 روز جهانی مسجد",
    # مهر
    (7, 1): "📚 آغاز سال تحصیلی · روز جهانی سالمند",
    (7, 5): "🌹 روز جهانی معلم",
    (7, 7): "🚒 روز آتش‌نشان و ایمنی",
    (7, 8): "📜 روز بزرگداشت مولوی",
    (7, 9): "🌹 روز جهانی همبستگی با کودکان فلسطینی",
    (7, 10): "🧒 روز جهانی کودک",
    (7, 11): "👧 روز جهانی دختر",
    (7, 12): "👨‍👩‍👧 روز ملی خانواده",
    (7, 13): "👮 روز نیروی انتظامی",
    (7, 15): "🌾 روز ملی روستا و عشایر",
    (7, 16): "🍽 روز جهانی غذا",
    (7, 17): "📻 روز جهانی پست",
    (7, 20): "🍷 روز بزرگداشت حافظ",
    (7, 24): "🏅 روز ملی پارالمپیک",
    (7, 26): "🏃 روز تربیت بدنی و ورزش",
    # آبان
    (8, 1): "📊 روز آمار و برنامه‌ریزی",
    (8, 3): "👂 روز جهانی ناشنوایان",
    (8, 8): "📖 روز نوجوان",
    (8, 13): "🎓 روز دانش‌آموز",
    (8, 14): "🌹 روز فرهنگ عمومی",
    (8, 15): "📚 روز کتاب و کتاب‌خوانی",
    (8, 16): "🧒 روز نوجوان",
    (8, 17): "🌹 روز جهانی فلسفه",
    (8, 19): "🕌 روز جهانی فلسطین",
    (8, 20): "🏙 روز جهانی شهرسازی",
    (8, 24): "📚 روز کتاب و کتاب‌خوانی",
    (8, 26): "🌿 روز هوای پاک",
    # آذر
    (9, 1): "⚓️ روز خلیج فارس",
    (9, 3): "🧩 روز جهانی معلولان",
    (9, 5): "🟢 روز بسیج مستضعفین",
    (9, 7): "⚓️ روز نیروی دریایی",
    (9, 9): "🏛 روز مجلس شورای اسلامی",
    (9, 10): "🌍 روز جهانی حقوق بشر",
    (9, 12): "🖥 روز جهانی کامپیوتر",
    (9, 16): "🎓 روز دانشجو",
    (9, 25): "🔬 روز پژوهش",
    (9, 30): "🌙 شب یلدا · شب چله",
    # دی
    (10, 1): "🎄 میلاد حضرت مسیح (ع) · آغاز سال نو میلادی",
    (10, 4): "🌹 روز ثبت احوال",
    (10, 5): "✍️ روز بزرگداشت شهریار",
    (10, 7): "🚦 روز حمل و نقل",
    (10, 9): "🛡 روز بصیرت و میثاق امت با ولایت",
    (10, 12): "🌹 روز درگذشت آیت‌الله العظمی بروجردی",
    (10, 14): "🌾 روز جهاد کشاورزی",
    (10, 17): "🐄 روز دامپزشکی",
    (10, 22): "🇵🇸 روز غزه",
    (10, 25): "👨‍👩‍👧‍👦 روز خانواده",
    (10, 27): "🌹 روز بزرگداشت عطار نیشابوری",
    (10, 29): "🌿 روز هوای پاک",
    # بهمن
    (11, 1): "🚀 روز ملی هوافضا",
    (11, 5): "🏆 روز جهانی کارگر؟",
    (11, 7): "🌹 روز ملی ایمنی در برابر زلزله",
    (11, 8): "🍇 روز بزرگداشت ناصرخسرو قبادیانی",
    (11, 12): "✈️ ورود امام خمینی (ره) به میهن · آغاز دهه فجر",
    (11, 14): "🌹 روز ملی فناوری فضایی",
    (11, 15): "🌹 روز درگذشت آیت‌الله طالقانی",
    (11, 19): "🗡 جشن بهمنگان",
    (11, 22): "🇮🇷 روز پیروزی انقلاب اسلامی ایران",
    (11, 23): "🎖 روز روحانیت مبارز",
    (11, 24): "🇮🇷 روز بزرگداشت سیدجمال‌الدین اسدآبادی",
    (11, 25): "🎖 روز نیروی هوایی",
    (11, 26): "🌹 روز اعتکاف؟",
    (11, 29): "💪 روز اقتصاد مقاومتی و کارآفرینی",
    # اسفند
    (12, 1): "✍️ روز بزرگداشت خواجوی کرمانی",
    (12, 3): "🐅 روز جهانی حیات وحش",
    (12, 5): "🔭 روز بزرگداشت خواجه نصیرالدین طوسی · روز مهندسی",
    (12, 9): "🗳 روز ملی شوراها",
    (12, 10): "🏗 روز شوراهای اسلامی کار؟",
    (12, 14): "🌹 روز درختکاری",
    (12, 15): "🌳 روز درختکاری",
    (12, 18): "🕌 روز جهانی پوشش همگانی سلامت",
    (12, 22): "🎏 جشن برپایه؟",
    (12, 25): "✍️ روز بزرگداشت پروین اعتصامی",
    (12, 27): "🌹 روز بزرگداشت کمال‌الملک",
    (12, 28): "🛢 روز ملی شدن صنعت نفت ایران",
    (12, 29): "🧹 روز ملی شدن صنعت نفت · جشن اسفندگان",
}


# ============ توابع عمومی ============

def today_jalali(now: _dt.datetime | None = None) -> tuple[int, int, int]:
    now = now or _dt.datetime.now()
    return gregorian_to_jalali(now.year, now.month, now.day)


def occasions_for(jy: int, jm: int, jd: int) -> list[str]:
    items: list[str] = []
    occ = JALALI_OCCASIONS.get((jm, jd))
    if occ:
        items.append(occ)
    # مناسبت‌های قمری
    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
    iy, im, id_ = gregorian_to_islamic(gy, gm, gd)
    islamic = ISLAMIC_OCCASIONS.get((im, id_))
    if islamic:
        items.append(f"🌙 {islamic} (قمری)")
    return items


def month_grid(jy: int, jm: int) -> dict[str, Any]:
    """شبکه ماه برای نمایش تقویم — با روزهای ماه قبل/بعد برای پر کردن هفته."""
    gy, gm, gd = jalali_to_gregorian(jy, jm, 1)
    first_weekday = _dt.date(gy, gm, gd).weekday()  # 0=Monday ... 6=Sunday
    # شنبه = 0 در تقویم فارسی → تبدیل
    saturday_first = (first_weekday + 1) % 7  # شنبه=0، یکشنبه=1...
    length = jalali_month_length(jy, jm)
    cells: list[dict[str, Any]] = []
    # روزهای قبل (ماه قبل)
    prev_month = jm - 1 if jm > 1 else 12
    prev_year = jy if jm > 1 else jy - 1
    prev_length = jalali_month_length(prev_year, prev_month)
    for i in range(saturday_first):
        day = prev_length - saturday_first + i + 1
        cells.append({"day": day, "month": prev_month, "year": prev_year, "current": False})
    # روزهای ماه
    for d in range(1, length + 1):
        cells.append({"day": d, "month": jm, "year": jy, "current": True})
    # روزهای بعد (ماه بعد)
    while len(cells) % 7 != 0:
        next_month = jm + 1 if jm < 12 else 1
        next_year = jy if jm < 12 else jy + 1
        day = len(cells) - saturday_first - length + 1
        cells.append({"day": day, "month": next_month, "year": next_year, "current": False})
    return {
        "year": jy,
        "month": jm,
        "month_name": JALALI_MONTHS[jm - 1],
        "days": cells,
        "length": length,
        "leap": is_leap_jalali(jy),
    }


def month_occasions(jy: int, jm: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for d in range(1, jalali_month_length(jy, jm) + 1):
        occs = occasions_for(jy, jm, d)
        if occs:
            items.append({"day": d, "occasions": occs})
    return items


def format_jalali_date(jy: int, jm: int, jd: int, with_weekday: bool = True) -> str:
    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
    weekday = JALALI_WEEKDAYS[(_dt.date(gy, gm, gd).weekday() + 2) % 7] if with_weekday else ""
    text = f"{jd} {JALALI_MONTHS[jm - 1]} {jy}"
    if with_weekday:
        text = f"{weekday} {text}"
    return text


def today_info(now: _dt.datetime | None = None) -> dict[str, Any]:
    now = now or _dt.datetime.now()
    jy, jm, jd = gregorian_to_jalali(now.year, now.month, now.day)
    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
    weekday = JALALI_WEEKDAYS[(_dt.date(gy, gm, gd).weekday() + 2) % 7]
    iy, im, id_ = gregorian_to_islamic(gy, gm, gd)
    return {
        "jy": jy, "jm": jm, "jd": jd,
        "month_name": JALALI_MONTHS[jm - 1],
        "weekday": weekday,
        "occasions": occasions_for(jy, jm, jd),
        "gregorian": f"{gd} {_dt.date(gy, gm, gd).strftime('%B %Y')}",
        "islamic": f"{id_} {ISLAMIC_MONTHS[im - 1]} {iy}",
        "leap": is_leap_jalali(jy),
    }
