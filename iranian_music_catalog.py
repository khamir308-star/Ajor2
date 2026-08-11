"""Curated Iranian music metadata used as a local search/index layer.

The catalog contains metadata and public search links only; it does not bundle
copyrighted audio. Live Deezer, iTunes and Piped searches are combined with it
for fresher results and for Iranian rap/pop/traditional remixes.
"""

from urllib.parse import quote


_IRANIAN_TRACKS = (
    ("ابی", "کوه یخ", "پاپ کلاسیک", "classic pop"),
    ("ابی", "شب نیلوفری", "پاپ کلاسیک", "classic pop"),
    ("ابی", "گلپونه", "پاپ کلاسیک", "classic pop"),
    ("ابی", "خلیج فارس", "پاپ کلاسیک", "classic pop"),
    ("ابی", "باغ بلور", "پاپ کلاسیک", "classic pop"),
    ("ابی", "پوست شیر", "پاپ کلاسیک", "classic pop"),
    ("گوگوش", "دو پنجره", "پاپ کلاسیک", "classic pop"),
    ("گوگوش", "من و تو", "پاپ کلاسیک", "classic pop"),
    ("گوگوش", "همسفر", "پاپ کلاسیک", "classic pop"),
    ("گوگوش", "غریب آشنا", "پاپ کلاسیک", "classic pop"),
    ("گوگوش", "قصه عشق", "پاپ کلاسیک", "classic pop"),
    ("داریوش", "دستای تو", "پاپ کلاسیک", "classic pop"),
    ("داریوش", "بچه های ایران", "پاپ کلاسیک", "classic pop"),
    ("داریوش", "زندگی", "پاپ کلاسیک", "classic pop"),
    ("داریوش", "چشم من", "پاپ کلاسیک", "classic pop"),
    ("داریوش", "به من نگو دوستت دارم", "پاپ کلاسیک", "classic pop"),
    ("هایده", "سوغاتی", "پاپ کلاسیک", "classic pop"),
    ("هایده", "گل سرخ", "پاپ کلاسیک", "classic pop"),
    ("هایده", "بزن باران", "پاپ کلاسیک", "classic pop"),
    ("مهستی", "دلم تنگه", "پاپ کلاسیک", "classic pop"),
    ("مهستی", "آسمون", "پاپ کلاسیک", "classic pop"),
    ("ستین", "عزیزجان", "پاپ", "pop"),
    ("شجریان", "مرغ سحر", "سنتی", "traditional"),
    ("محمدرضا شجریان", "ربنا", "سنتی", "traditional"),
    ("محمدرضا شجریان", "زبان آتش", "سنتی", "traditional"),
    ("شهرام ناظری", "اندک اندک", "سنتی", "traditional"),
    ("علیرضا افتخاری", "صیاد", "سنتی", "traditional"),
    ("سالار عقیلی", "وطنم", "سنتی", "traditional"),
    ("همایون شجریان", "چرا رفتی", "سنتی پاپ", "traditional pop"),
    ("همایون شجریان", "با من صنما", "سنتی پاپ", "traditional pop"),
    ("محسن نامجو", "ترنج", "تلفیقی", "fusion"),
    ("محسن نامجو", "گیس", "تلفیقی", "fusion"),
    ("محسن نامجو", "زلف", "تلفیقی", "fusion"),
    ("محسن چاوشی", "کجایی", "پاپ", "pop"),
    ("محسن چاوشی", "سنتوری", "پاپ", "pop"),
    ("محسن چاوشی", "بعد از تو", "پاپ", "pop"),
    ("محسن چاوشی", "همخواب", "پاپ", "pop"),
    ("محسن یگانه", "بهت قول میدم", "پاپ", "pop"),
    ("محسن یگانه", "رگ خواب", "پاپ", "pop"),
    ("محسن یگانه", "نبض احساس", "پاپ", "pop"),
    ("محسن یگانه", "نشکن دلمو", "پاپ", "pop"),
    ("شادمهر عقیلی", "تقدیر", "پاپ", "pop"),
    ("شادمهر عقیلی", "بی احساس", "پاپ", "pop"),
    ("شادمهر عقیلی", "آدم فروش", "پاپ", "pop"),
    ("شادمهر عقیلی", "حالم عوض میشه", "پاپ", "pop"),
    ("سیروان خسروی", "دوست دارم زندگی رو", "پاپ", "pop"),
    ("سیروان خسروی", "بارون پاییزی", "پاپ", "pop"),
    ("سیروان خسروی", "کجایی تو", "پاپ", "pop"),
    ("زانیار خسروی", "رگ خواب", "پاپ", "pop"),
    ("احسان خواجه امیری", "عاشقانه ها", "پاپ", "pop"),
    ("احسان خواجه امیری", "پاییز مسموم", "پاپ", "pop"),
    ("احسان خواجه امیری", "دریا", "پاپ", "pop"),
    ("رضا بهرام", "کجایی", "پاپ", "pop"),
    ("رضا بهرام", "مو به مو", "پاپ", "pop"),
    ("رضا بهرام", "دیوانه", "پاپ", "pop"),
    ("حمید هیراد", "شوخیه مگه", "پاپ", "pop"),
    ("حمید هیراد", "ماه من", "پاپ", "pop"),
    ("حمید هیراد", "دلارام", "پاپ", "pop"),
    ("علی یاسینی", "منو ببخش", "پاپ", "pop"),
    ("علی یاسینی", "نقاب", "پاپ", "pop"),
    ("علی یاسینی", "جنگ", "پاپ", "pop"),
    ("ماکان بند", "دوست دارم", "پاپ", "pop"),
    ("ماکان بند", "هر بار این درو", "پاپ", "pop"),
    ("ماکان بند", "یه لحظه نگام کن", "پاپ", "pop"),
    ("ایوان بند", "عالیجناب عشق", "پاپ", "pop"),
    ("ایوان بند", "عالیجناب", "پاپ", "pop"),
    ("مسیح و آرش", "دریا", "پاپ", "pop"),
    ("مسیح و آرش", "دریا کنارم", "پاپ", "pop"),
    ("مهدی احمدوند", "عشق اول", "پاپ", "pop"),
    ("مهدی احمدوند", "بغض", "پاپ", "pop"),
    ("مهدی یراحی", "حیک", "پاپ", "pop"),
    ("مهدی یراحی", "پاره سنگ", "پاپ", "pop"),
    ("علی عبدالمالکی", "نبض احساس", "پاپ", "pop"),
    ("فرزاد فرزین", "عاشقانه", "پاپ", "pop"),
    ("فرزاد فرزین", "شلیک", "پاپ", "pop"),
    ("هوروش بند", "ماه دلم", "پاپ", "pop"),
    ("هوروش بند", "خنک شد دلت", "پاپ", "pop"),
    ("یاس", "سرکوب", "رپ", "rap"),
    ("یاس", "نامه ای به فرزند", "رپ", "rap"),
    ("یاس", "بغض یعنی", "رپ", "rap"),
    ("هیچکس", "یه روز خوب میاد", "رپ", "rap"),
    ("هیچکس", "دوباره", "رپ", "rap"),
    ("رضا پیشرو", "شهروند", "رپ", "rap"),
    ("رضا پیشرو", "ما با همیم", "رپ", "rap"),
    ("بهرام", "نامه ای به سرباز", "رپ", "rap"),
    ("بهرام", "گوزن", "رپ", "rap"),
    ("شاهین نجفی", "ما مرد نیستیم", "رپ", "rap"),
    ("حصین", "چالیم دو", "رپ", "rap"),
    ("حصین", "جاده", "رپ", "rap"),
    ("تتلو", "من باهات قهرم", "رپ پاپ", "rap pop"),
    ("پوبون", "بهت قول میدم", "رپ پاپ", "rap pop"),
    ("سورنا", "گنجشکک", "رپ", "rap"),
    ("د دان", "پایدار", "رپ", "rap"),
    ("مهراد هیدن", "سیگار", "رپ", "rap"),
    ("کچی بیتز", "تهران", "رپ", "rap"),
    ("سامان جلیلی", "حالم بده", "پاپ", "pop"),
    ("گرشا رضایی", "دلم خواست", "پاپ", "pop"),
    ("گرشا رضایی", "دلم هوس کرده", "پاپ", "pop"),
    ("بابک جهانبخش", "من و بارون", "پاپ", "pop"),
    ("بابک جهانبخش", "اکسیژن", "پاپ", "pop"),
    ("رضا صادقی", "مشکی رنگ عشقه", "پاپ", "pop"),
    ("رضا صادقی", "وایسا دنیا", "پاپ", "pop"),
)


_REMIX_TRACKS = (
    ("ریمیکس رپ و پاپ ایرانی", "تلفیقی", "remix rap pop"),
    ("ریمیکس پاپ و سنتی ایرانی", "تلفیقی", "remix pop traditional"),
    ("ریمیکس رپ، پاپ و سنتی", "تلفیقی", "remix rap pop traditional"),
    ("ریمیکس شبانه ایرانی", "تلفیقی", "night remix"),
    ("ریمیکس شاد ایرانی", "تلفیقی", "party remix"),
    ("ریمیکس غمگین ایرانی", "تلفیقی", "sad remix"),
    ("ریمیکس دیپ هاوس ایرانی", "الکترونیک", "deep house remix"),
    ("ریمیکس سنتی مدرن", "تلفیقی", "modern traditional remix"),
    ("ریمیکس رپ فارسی جدید", "رپ", "new persian rap remix"),
    ("ریمیکس پاپ فارسی جدید", "پاپ", "new persian pop remix"),
)


def _catalog_item(index: int, artist: str, title: str, genre: str, tags: str) -> dict:
    search = quote(f"{artist} {title}")
    return {
        "source": "iranian_catalog",
        "provider": "🇮🇷 کاتالوگ ایرانی",
        "id": f"ir_{index:04d}",
        "title": title[:180],
        "artist": artist[:120],
        "album": "",
        "genre": genre,
        "tags": tags,
        "duration": 0,
        "artwork": None,
        "preview_url": None,
        "downloadable": False,
        "watch_url": f"https://www.youtube.com/results?search_query={search}",
        "permalink": f"https://www.deezer.com/search/{search}",
    }


IRANIAN_MUSIC_CATALOG = [
    _catalog_item(index, artist, title, genre, tags)
    for index, (artist, title, genre, tags) in enumerate(_IRANIAN_TRACKS, 1)
]
IRANIAN_MUSIC_CATALOG.extend(
    _catalog_item(1000 + index, "پیشنهاد جستجوی ایرانی", title, genre, tags)
    for index, (title, genre, tags) in enumerate(_REMIX_TRACKS, 1)
)

IRANIAN_SEARCH_MARKERS = {
    "ایرانی", "ایران", "فارسی", "پاپ", "رپ", "سنتی", "تلفیقی", "ریمیکس", "میکس",
    "persian", "iranian", "remix", "mix",
}
IRANIAN_ARTIST_ALIASES = {
    artist.lower()
    for artist, _title, _genre, _tags in _IRANIAN_TRACKS
} | {
    "ebi", "googoosh", "dariush", "hayedeh", "mahasti", "shajarian", "shajryan",
    "namjoo", "mohsen namjoo", "chavoshi", "mohsen chavoshi", "mohsen yeganeh",
    "shadmehr", "sirvan", "zaniar", "reza bahram", "ehsan khajeh amiri",
    "yas", "hichkas", "bahram", "pishro", "ho3ein", "tataloo", "macan band",
}


__all__ = [
    "IRANIAN_ARTIST_ALIASES",
    "IRANIAN_MUSIC_CATALOG",
    "IRANIAN_SEARCH_MARKERS",
]
