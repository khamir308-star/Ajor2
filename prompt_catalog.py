"""Structured prompt library expansion for the Ajorpareh Telegram bot.

The legacy catalog remains in ``bot.py`` because it is part of the original bot
flow.  This module owns the 400 new prompts requested for the prompt center.
The entries are generated from curated, deterministic recipe matrices rather
than being copied-and-pasted near-duplicates.  Every generated entry has its
own stable id, title, prompt and sample description, so callback data and
weekly ordering remain deterministic across bot restarts.
"""

from itertools import product


REFERENCE_IDENTITY_GUARD = (
    "If a reference image is attached, preserve the person's actual identity, "
    "gender, age range, facial structure, skin tone, hairstyle, beard or hairline, "
    "body proportions and recognizable features. Never feminize, masculinize, "
    "age-swap or turn the person into someone else; change only the requested "
    "scene, lighting, clothing or artistic treatment."
)


IMAGE_SCENES = (
    ("rainy_city", "شهر بارانی شب", "a rain-soaked modern city street at night, reflections on asphalt and believable distant traffic"),
    ("desert_sunrise", "طلوع در کویر", "a quiet desert at sunrise, layered dunes, delicate haze and a low warm sun"),
    ("window_rain", "کنار پنجرهٔ بارانی", "a calm interior beside a rain-covered window, soft daylight and an intimate atmosphere"),
    ("old_bazaar", "بازار تاریخی", "a richly textured historic bazaar, natural crowd depth, warm shop lights and authentic architecture"),
    ("sea_cliff", "صخرهٔ ساحلی", "a dramatic coast with a safe cliffside viewpoint, rolling waves, sea mist and a wide horizon"),
    ("mountain_road", "جادهٔ کوهستانی", "a winding mountain road with layered peaks, clear atmospheric perspective and a sense of journey"),
    ("quiet_library", "کتابخانهٔ آرام", "an elegant old library with wooden shelves, soft window light and subtle floating dust"),
    ("neon_alley", "کوچهٔ نئونی", "a cinematic neon alley in a futuristic city, wet pavement, controlled color contrast and depth"),
    ("luxury_hotel", "هتل لوکس", "a refined luxury hotel lobby with tasteful materials, architectural symmetry and gentle ambient light"),
    ("garden_ceremony", "باغ مراسم", "a graceful garden ceremony setting with flowers, natural greenery and soft late-afternoon light"),
    ("stadium_energy", "استادیوم پرانرژی", "a believable stadium atmosphere with lights, motion in the background and a clear main subject"),
    ("artisan_cafe", "کافهٔ هنری", "a warm artisan cafe with handmade details, natural window light and a relaxed urban mood"),
    ("snowy_village", "روستای برفی", "a peaceful snowy village with textured roofs, footprints, atmospheric frost and soft overcast light"),
    ("persian_architecture", "معماری ایرانی", "a detailed Persian courtyard with tilework, arches, water reflections and historically respectful design"),
    ("tropical_greenhouse", "گلخانهٔ گرمسیری", "a lush tropical greenhouse with layered leaves, filtered sunlight, humidity and realistic depth"),
)


IMAGE_TREATMENTS = (
    ("cinematic_35mm", "سینمایی ۳۵ میلی‌متری", "a cinematic 35mm composition, motivated key light, natural lens falloff and restrained film grain"),
    ("editorial_magazine", "ادیتوریال مجله‌ای", "a premium editorial magazine composition, confident visual hierarchy, polished but believable styling"),
    ("soft_natural", "نور طبیعی نرم", "soft natural daylight, gentle contrast, accurate skin and fabric texture and an unforced documentary feeling"),
    ("low_key", "نور کم‌کلید", "low-key portrait lighting, controlled shadows, a clean separation from the background and no crushed facial detail"),
    ("golden_hour", "ساعت طلایی", "warm golden-hour backlight, subtle rim light, long natural shadows and rich but realistic color"),
    ("neon_noir", "نئونوآر", "neon-noir lighting with carefully separated cyan and amber accents, realistic reflections and cinematic contrast"),
    ("analog_film", "فیلم آنالوگ", "a refined analog-film look, fine grain, gentle halation, natural colors and no artificial plastic skin"),
    ("luxury_commercial", "تبلیغاتی لوکس", "high-end commercial lighting, precise material rendering, clean composition and premium visual restraint"),
    ("monochrome", "تک‌رنگ هنری", "a sophisticated monochrome treatment, rich tonal range, expressive light and detailed midtones"),
    ("hyperreal_detail", "جزئیات فوتورئال", "high-end photorealistic detail, physically plausible light, natural anatomy and a clean professional finish"),
)


EDIT_OPERATIONS = (
    ("background_swap", "تعویض پس‌زمینه", "replace the background with a coherent environment while matching perspective, depth, light direction and contact shadows"),
    ("outfit_change", "تغییر لباس", "change only the outfit to a tasteful, realistic design with correct folds, seams, occlusion and body proportions"),
    ("relight", "نورپردازی دوباره", "re-light the image with a new motivated light source while keeping facial structure, textures and believable shadows intact"),
    ("color_grade", "اصلاح رنگ سینمایی", "apply a controlled professional color grade without clipping highlights, destroying skin tones or changing the subject"),
    ("skin_restore", "ترمیم طبیعی پوست", "restore skin detail and remove temporary blemishes while retaining pores, expression, age and natural texture"),
    ("object_remove", "حذف شیء مزاحم", "remove the specified distracting object and reconstruct the hidden background with consistent texture and perspective"),
    ("portrait_reframe", "کادر‌بندی دوباره", "reframe and crop the portrait for a stronger composition while preserving the face, pose, proportions and important accessories"),
    ("detail_upscale", "افزایش جزئیات", "upscale and enhance fine detail, edges and texture without inventing a different face, changing identity or adding artifacts"),
)


EDIT_FINISHES = (
    ("natural_editorial", "ادیت طبیعی ادیتوریال", "a natural editorial finish with balanced contrast and true-to-life skin"),
    ("teal_orange", "سینمایی فیروزه‌ای و نارنجی", "a restrained teal-and-orange cinematic grade with realistic skin tones"),
    ("warm_film", "فیلم گرم", "a warm analog-film finish with subtle grain and gentle highlight roll-off"),
    ("black_white", "سیاه‌وسفید کلاسیک", "a classic black-and-white finish with rich blacks and detailed midtones"),
    ("studio_clean", "استودیویی تمیز", "a clean studio finish with precise edges, neutral color and commercial clarity"),
    ("pastel_soft", "پاستلی نرم", "a soft pastel finish with controlled saturation and a calm, premium mood"),
    ("night_neon", "شب نئونی", "a night-neon finish with believable colored spill and preserved facial detail"),
    ("vintage_analog", "آنالوگ نوستالژیک", "a tasteful vintage-analog finish with fine grain and no fake scratches over the face"),
    ("ecommerce_white", "سفید تبلیغاتی", "a bright ecommerce-ready finish with clean whites, realistic shadows and accurate materials"),
    ("social_portrait", "پرترهٔ شبکهٔ اجتماعی", "a polished social-media portrait finish optimized for a crisp vertical crop"),
)


CONTENT_TASKS = (
    ("instagram_caption", "کپشن اینستاگرام", "برای موضوع یا محصول داده‌شده یک کپشن فارسی طبیعی بنویس"),
    ("reel_script", "سناریوی ریلز", "برای موضوع داده‌شده یک سناریوی ویدئوی عمودی کوتاه طراحی کن"),
    ("carousel_plan", "اسلایدهای کاروسل", "برای موضوع داده‌شده ساختار یک پست کاروسل آموزشی طراحی کن"),
    ("telegram_post", "پست کانال تلگرام", "برای موضوع داده‌شده یک پست آمادهٔ انتشار در کانال تلگرام بنویس"),
    ("product_copy", "معرفی محصول", "برای محصول داده‌شده متن معرفی متقاعدکننده اما صادقانه بنویس"),
    ("youtube_metadata", "عنوان و توضیحات ویدئو", "برای ویدئوی داده‌شده عنوان، توضیحات و فصل‌بندی مناسب پیشنهاد بده"),
    ("story_interaction", "استوری تعاملی", "برای موضوع داده‌شده یک مجموعه استوری تعاملی با نظرسنجی طراحی کن"),
    ("content_calendar", "تقویم محتوایی", "برای موضوع یا برند داده‌شده یک برنامهٔ محتوایی قابل اجرا پیشنهاد بده"),
)


CONTENT_STYLES = (
    ("conversational", "محاوره‌ای", "با لحن محاوره‌ای، گرم و قابل فهم برای مخاطب عمومی"),
    ("expert", "کارشناسی", "با لحن متخصص، دقیق و بدون ادعای بی‌منبع"),
    ("humorous", "طنز ملایم", "با طنز ملایم و محترمانه، بدون توهین یا کلیشه‌سازی"),
    ("emotional", "احساسی", "با لحن احساسی اما واقعی و دور از اغراق مصنوعی"),
    ("concise", "کوتاه و مستقیم", "کوتاه، مستقیم و مناسب مخاطب کم‌حوصله"),
    ("persuasive", "متقاعدکننده", "متقاعدکننده و نتیجه‌محور، بدون وعدهٔ غیرواقعی"),
    ("gen_z", "جوان‌پسند", "جوان‌پسند و امروزی، اما با فارسی طبیعی و غیرتصنعی"),
    ("premium", "برند لوکس", "با لحن مینیمال، شیک و مناسب برند پریمیوم"),
    ("educational", "آموزشی", "با ساختار آموزشی، مثال کوتاه و نکتهٔ قابل اجرا"),
    ("safe_trend", "ترند مسئولانه", "همسو با ترندهای روز اما دقیق، مسئولانه و بدون اطلاعات ساختگی"),
)


UTILITY_TASKS = (
    ("summarize", "خلاصه‌سازی", "متن زیر را خلاصه و نکات اصلی آن را استخراج کن"),
    ("translate", "ترجمهٔ حرفه‌ای", "متن زیر را به زبان مقصد ترجمه کن و لحن اصلی را حفظ کن"),
    ("study_plan", "برنامهٔ مطالعه", "برای هدف و زمان داده‌شده یک برنامهٔ مطالعهٔ واقع‌بینانه بساز"),
    ("meeting_actions", "اقدام‌های جلسه", "یادداشت جلسه را به تصمیم‌ها، مسئول‌ها و اقدام‌های بعدی تبدیل کن"),
    ("code_review", "بازبینی کد", "کد زیر را از نظر خطا، امنیت، عملکرد و خوانایی بررسی کن"),
)


UTILITY_FORMATS = (
    ("bullets", "بولت‌پوینت", "خروجی را در bulletهای کوتاه و مرتب بده"),
    ("table", "جدول", "نتیجه را در یک جدول خوانا با عنوان ستون‌های روشن ارائه کن"),
    ("steps", "مرحله‌به‌مرحله", "خروجی را به مراحل شماره‌دار و قابل اجرا تقسیم کن"),
    ("brief", "خلاصهٔ خیلی کوتاه", "اول پاسخ کوتاه و مستقیم بده و فقط نکات ضروری را نگه دار"),
    ("beginner", "مناسب مبتدی", "اصطلاحات را ساده توضیح بده و یک مثال قابل فهم اضافه کن"),
    ("senior", "سطح حرفه‌ای", "ریسک‌ها، فرض‌ها و جزئیات مهم را مثل یک متخصص ارشد پوشش بده"),
    ("checklist", "چک‌لیست", "نتیجه را به چک‌لیست قابل علامت‌زدن تبدیل کن"),
    ("comparison", "مقایسه‌ای", "گزینه‌ها را با مزایا، معایب و معیار انتخاب مقایسه کن"),
    ("actionable", "اقدام‌محور", "در پایان یک فهرست اقدام اولویت‌بندی‌شده و زمان تقریبی بده"),
    ("fact_safe", "دقیق و محتاط", "بین واقعیت، فرض و ابهام تفاوت بگذار و چیزی را حدس قطعی نزن"),
)


TREND_CONCEPTS = (
    ("ugc_product", "ویدئوی UGC محصول", "برای معرفی یک محصول در قالب ویدئوی UGC عمودی"),
    ("before_after", "ترند قبل و بعد", "برای نمایش قبل و بعد یک تغییر واقعی و قابل باور"),
    ("street_story", "داستان خیابانی", "برای یک روایت کوتاه خیابانی با شروع کنجکاوکننده"),
    ("visual_hook", "هوک تصویری", "برای ساخت یک محتوای تصویری با هوک سریع و قابل توقف در اسکرول"),
)


TREND_FORMATS = (
    ("six_second", "شش‌ثانیه‌ای", "در ۶ ثانیه با یک هوک فوری و یک پایان واضح"),
    ("fifteen_second", "پانزده‌ثانیه‌ای", "در ۱۵ ثانیه با سه ضرباهنگ و CTA کوتاه"),
    ("loop", "لوپ‌شونده", "طوری که پایان آن به شروع وصل شود و ویدئو لوپ طبیعی داشته باشد"),
    ("comment_bait_safe", "کامنت‌ساز مسئولانه", "با یک سؤال واقعی و محترمانه برای افزایش گفت‌وگو، نه فریب مخاطب"),
    ("bilingual", "دو‌زبانه", "با متن فارسی و یک نسخهٔ کوتاه انگلیسی برای روی تصویر"),
    ("voiceover", "نریشن‌محور", "با نریشن کوتاه، مکث‌ها و پیشنهاد تصویر برای هر جمله"),
    ("text_only", "متن روی تصویر", "بدون وابستگی به گوینده و با متن‌های کوتاه قابل خواندن روی تصویر"),
    ("creator_native", "مناسب سازندهٔ محتوا", "با حس طبیعی و خودمانی، بدون شبیه‌سازی تبلیغ رسمی"),
    ("premium_reel", "ریل پریمیوم", "با قاب‌بندی لوکس، حرکت دوربین کنترل‌شده و موسیقی پیشنهادی"),
    ("trend_safe", "ترند ماندگار", "بر پایهٔ فرمت ترند اما بدون موسیقی یا ادعایی که تاریخ مصرف فوری داشته باشد"),
)

def _build_catalog() -> list[dict]:
    """Build exactly 400 stable, non-placeholder prompt records."""
    entries: list[dict] = []

    for index, (scene, treatment) in enumerate(product(IMAGE_SCENES, IMAGE_TREATMENTS)):
        scene_id, scene_title, scene_description = scene
        treatment_id, treatment_title, treatment_description = treatment
        entries.append(
            {
                "id": f"img_{scene_id}_{treatment_id}",
                "category": "image",
                "title": f"🎨 {scene_title} · {treatment_title}",
                "kind": "تصویر",
                "trend": 92 + ((index * 7) % 9),
                "prompt": (
                    f"Create a production-ready photorealistic image of {scene_description}. "
                    f"Use {treatment_description}. Keep composition intentional, anatomy natural, "
                    "materials physically believable, facial detail clean, no random text, no watermark "
                    f"and no invented logos. {REFERENCE_IDENTITY_GUARD}"
                ),
                "sample": f"نمونه کار: {scene_title} با اجرای {treatment_title}، نور و عمق طبیعی و جزئیات قابل باور.",
            }
        )

    for index, (operation, finish) in enumerate(product(EDIT_OPERATIONS, EDIT_FINISHES)):
        operation_id, operation_title, operation_description = operation
        finish_id, finish_title, finish_description = finish
        entries.append(
            {
                "id": f"edit_{operation_id}_{finish_id}",
                "category": "edit",
                "title": f"🖼 {operation_title} · {finish_title}",
                "kind": "ویرایش تصویر",
                "trend": 91 + ((index * 5) % 10),
                "prompt": (
                    f"Edit the supplied image. {operation_description}. Apply {finish_description}. "
                    "Preserve realistic edges, perspective, lighting continuity and natural texture. "
                    f"{REFERENCE_IDENTITY_GUARD} Do not add text, watermark, extra fingers or artificial facial changes."
                ),
                "sample": f"نمونه کار: {operation_title} با خروجی {finish_title} و بدون تغییر هویت سوژه.",
            }
        )

    for index, (task, style) in enumerate(product(CONTENT_TASKS, CONTENT_STYLES)):
        task_id, task_title, task_instruction = task
        style_id, style_title, style_instruction = style
        entries.append(
            {
                "id": f"content_{task_id}_{style_id}",
                "category": "content",
                "title": f"📣 {task_title} · {style_title}",
                "kind": "تولید محتوا",
                "trend": 90 + ((index * 3) % 11),
                "prompt": (
                    f"{task_instruction}. {style_instruction}. "
                    "مخاطب، هدف، موضوع و محدودیت‌های زیر را در نظر بگیر: [ورودی من]. "
                    "خروجی را آمادهٔ استفاده بده، از کلیشه و ادعای بی‌منبع دوری کن و اگر داده‌ای کم است "
                    "آن را با برچسب «نیازمند اطلاعات» مشخص کن."
                ),
                "sample": f"نمونه خروجی: {task_title} با لحن {style_title}، ساختار آمادهٔ انتشار و جای مشخص برای ورودی کاربر.",
            }
        )

    for index, (task, output_format) in enumerate(product(UTILITY_TASKS, UTILITY_FORMATS)):
        task_id, task_title, task_instruction = task
        format_id, format_title, format_instruction = output_format
        entries.append(
            {
                "id": f"utility_{task_id}_{format_id}",
                "category": "utility",
                "title": f"🧰 {task_title} · {format_title}",
                "kind": "کاربردی",
                "trend": 89 + ((index * 4) % 12),
                "prompt": (
                    f"{task_instruction}. {format_instruction}. "
                    "ورودی کاربر: [متن یا داده]. ابتدا فرض‌های ضروری را کوتاه بنویس، سپس پاسخ را ارائه کن "
                    "و در پایان مواردی را که برای اطمینان بیشتر باید بررسی شوند جدا کن."
                ),
                "sample": f"نمونه خروجی: {task_title} در قالب {format_title} با نتیجهٔ قابل استفاده و نکات بررسی.",
            }
        )

    for index, (concept, format_item) in enumerate(product(TREND_CONCEPTS, TREND_FORMATS)):
        concept_id, concept_title, concept_instruction = concept
        format_id, format_title, format_instruction = format_item
        entries.append(
            {
                "id": f"trend_{concept_id}_{format_id}",
                "category": "trending",
                "title": f"🔥 {concept_title} · {format_title}",
                "kind": "ترند",
                "trend": 95 + ((index * 7) % 6),
                "prompt": (
                    f"برای {concept_instruction} {format_instruction}. "
                    "یک ایدهٔ کامل شامل هوک، شات‌لیست، متن روی تصویر یا نریشن، زمان‌بندی، CTA و یک نکتهٔ "
                    "اجرایی بده. خروجی فارسی طبیعی، قابل فیلم‌برداری با امکانات معمولی و بدون ادعای ساختگی باشد."
                ),
                "sample": f"نمونه خروجی: {concept_title} در قالب {format_title} با هوک، شات‌لیست و CTA آمادهٔ اجرا.",
            }
        )

    if len(entries) != 400:
        raise RuntimeError(f"Prompt catalog expansion must contain 400 entries, got {len(entries)}")
    ids = [item["id"] for item in entries]
    if len(set(ids)) != len(ids):
        raise RuntimeError("Prompt catalog expansion contains duplicate ids")
    return entries


EXTENDED_PROMPTS = _build_catalog()
EXTENDED_PROMPT_COUNT = len(EXTENDED_PROMPTS)

__all__ = ["EXTENDED_PROMPTS", "EXTENDED_PROMPT_COUNT"]
