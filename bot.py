import os
import re
import logging
import tempfile
from datetime import timedelta
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler
)
from PIL import Image
from moviepy.editor import VideoFileClip

# تنظیمات پیشرفته
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# حالت‌های مکالمه
MEDIA_TYPE, CROP_METHOD, CROP_DETAILS, RESIZE_OPTION, VIDEO_TRIM = range(5)

# تنظیمات پیشرفته
MAX_PROCESSING_TIME = 300  # 5 دقیقه
TEMP_DIR = tempfile.gettempdir()

# استانداردهای جهانی برش
ASPECT_RATIOS = {
    "1:1": (1, 1),
    "4:3": (4, 3),
    "16:9": (16, 9),
    "9:16": (9, 16),
    "21:9": (21, 9),
    "2:3": (2, 3),
    "3:4": (3, 4),
    "A4": (210, 297),
    "سینمایی": (2048, 858),
    "اینستاگرام پست": (1080, 1080),
    "اینستاگرام استوری": (1080, 1920),
    "تلگرام پست": (1200, 630),
    "واتس‌اپ وضعیت": (1080, 1920),
    "توییتر هدر": (1500, 500),
    "توییتر پست": (1200, 675),
    "فیسبوک کاور": (820, 312),
    "لینکدین پست": (1200, 627),
    "یوتیوب تامبنیل": (1280, 720),
    "آیفون والپیپر": (1170, 2532),
    "اندروید والپیپر": (1440, 2960),
    "4K": (3840, 2160),
    "فول اچ‌دی": (1920, 1080),
    "اچ‌دی": (1280, 720),
    "SVGA": (800, 600),
    "VGA": (640, 480),
    "QVGA": (320, 240),
    "لوگو": (512, 512),
    "بنر": (468, 60),
    "سند": (1240, 1754),
    "پاسپورت": (413, 531),
    "کارت ویزیت": (850, 550)
}

# ذخیره‌سازی داده‌های کاربر
user_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """شروع مکالمه و درخواست رسانه"""
    keyboard = [
        [InlineKeyboardButton("📷 عکس", callback_data="photo"),
        InlineKeyboardButton("🎬 فیلم", callback_data="video")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🌟 به ربات حرفه‌ای برش رسانه خوش آمدید!\n"
        "لطفاً نوع رسانه مورد نظر خود را انتخاب کنید:",
        reply_markup=reply_markup
    )
    return MEDIA_TYPE

async def handle_media_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """پردازش انتخاب نوع رسانه"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    media_type = query.data
    
    user_data[user_id] = {"media_type": media_type}
    
    await query.edit_message_text(
        f"🖼️ لطفاً {'عکس' if media_type == 'photo' else 'فیلم'} خود را ارسال کنید"
    )
    return CROP_METHOD

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """پردازش رسانه دریافتی"""
    user_id = update.message.from_user.id
    media_type = user_data[user_id]["media_type"]
    
    # ایجاد دایرکتوری موقت برای کاربر
    user_dir = os.path.join(TEMP_DIR, f"user_{user_id}")
    os.makedirs(user_dir, exist_ok=True)
    
    # دریافت فایل
    if media_type == "photo" and update.message.photo:
        file = await update.message.photo[-1].get_file()
        ext = "jpg"
    elif media_type == "video" and (update.message.video or update.message.document):
        file = await (update.message.video or update.message.document).get_file()
        ext = "mp4"
    else:
        await update.message.reply_text("⚠️ لطفاً یک رسانه معتبر ارسال کنید!")
        return CROP_METHOD
    
    # ذخیره‌سازی موقت
    file_path = os.path.join(user_dir, f"original_{user_id}.{ext}")
    await file.download_to_drive(file_path)
    user_data[user_id]["original_path"] = file_path
    
    # دریافت مشخصات
    if media_type == "photo":
        with Image.open(file_path) as img:
            width, height = img.size
            user_data[user_id]["original_size"] = (width, height)
            size_info = f"📐 ابعاد اصلی: {width}×{height} پیکسل"
    else:  # ویدئو
        with VideoFileClip(file_path) as video:
            duration = video.duration
            width, height = video.size
            user_data[user_id]["original_size"] = (width, height)
            user_data[user_id]["duration"] = duration
            size_info = (
                f"🎥 ابعاد: {width}×{height} پیکسل\n"
                f"⏱️ مدت زمان: {str(timedelta(seconds=int(duration)))}"
            )
    
    # ایجاد کیبورد استانداردها
    buttons = []
    for name in list(ASPECT_RATIOS.keys())[:15]:
        buttons.append(InlineKeyboardButton(name, callback_data=f"std_{name}"))
    
    buttons.append(InlineKeyboardButton("سایر استانداردها", callback_data="more_standards"))
    buttons.append(InlineKeyboardButton("📏 اندازه دلخواه", callback_data="custom"))
    buttons.append(InlineKeyboardButton("🔍 زوم دستی", callback_data="zoom"))
    
    keyboard = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"{size_info}\n\n"
        "🔧 لطفاً روش برش را انتخاب کنید:",
        reply_markup=reply_markup
    )
    return CROP_DETAILS

async def handle_standard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """پردازش انتخاب استاندارد"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    std_name = query.data.split("_")[1]
    
    if std_name == "more_standards":
        # نمایش استانداردهای بیشتر
        buttons = []
        for name in list(ASPECT_RATIOS.keys())[15:]:
            buttons.append(InlineKeyboardButton(name, callback_data=f"std_{name}"))
        
        keyboard = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📐 استانداردهای بیشتر:",
            reply_markup=reply_markup
        )
        return CROP_DETAILS
    
    ratio = ASPECT_RATIOS[std_name]
    user_data[user_id]["crop_ratio"] = ratio
    
    # محاسبه اندازه بر اساس نسبت
    orig_width, orig_height = user_data[user_id]["original_size"]
    
    if isinstance(ratio[0], int) and isinstance(ratio[1], int):
        # نسبت پیکسلی
        target_w, target_h = ratio
        
        # محاسبه زوم برای جا شدن در ابعاد اصلی
        scale = min(orig_width / target_w, orig_height / target_h)
        new_width = int(target_w * scale)
        new_height = int(target_h * scale)
        
        user_data[user_id]["crop_size"] = (new_width, new_height)
    else:
        # نسبت تصویری
        ratio_value = ratio[0] / ratio[1]
        orig_ratio = orig_width / orig_height
        
        if ratio_value > orig_ratio:
            new_height = orig_height
            new_width = int(orig_height * ratio_value)
        else:
            new_width = orig_width
            new_height = int(orig_width / ratio_value)
        
        user_data[user_id]["crop_size"] = (new_width, new_height)
    
    await ask_resize_option(query)
    return RESIZE_OPTION

async def handle_custom_size(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """درخواست اندازه دلخواه"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    media_type = user_data[user_id]["media_type"]
    
    if media_type == "photo":
        await query.edit_message_text(
            "📏 لطفاً ابعاد برش را به صورت «عرضxارتفاع» وارد کنید (مثال: 800x600):"
        )
    else:
        await query.edit_message_text(
            "🎬 لطفاً ابعاد برش را به صورت «عرضxارتفاع» وارد کنید (مثال: 1920x1080):\n"
            "یا زمان‌های شروع و پایان را به صورت «شروع-پایان» وارد کنید (مثال: 00:15-01:30):"
        )
    return VIDEO_TRIM if media_type == "video" else CROP_DETAILS

async def process_crop_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """پردازش دستورات برش"""
    user_id = update.message.from_user.id
    text = update.message.text
    media_type = user_data[user_id]["media_type"]
    
    if 'x' in text:  # ابعاد پیکسلی
        try:
            width, height = map(int, text.split('x'))
            orig_width, orig_height = user_data[user_id]["original_size"]
            
            if width > orig_width or height > orig_height:
                await update.message.reply_text(
                    f"⚠️ ابعاد وارد شده بزرگتر از اندازه اصلی ({orig_width}x{orig_height}) است!"
                )
                return CROP_DETAILS
                
            user_data[user_id]["crop_size"] = (width, height)
            await ask_resize_option(update.message)
            return RESIZE_OPTION
            
        except ValueError:
            await update.message.reply_text("⚠️ فرمت نامعتبر! لطفاً به صورت «عرضxارتفاع» وارد کنید.")
            return CROP_DETAILS
    
    elif '-' in text and media_type == "video":  # زمان‌های ویدئو
        try:
            start_time, end_time = text.split('-')
            start_sec = time_to_seconds(start_time)
            end_sec = time_to_seconds(end_time)
            duration = user_data[user_id]["duration"]
            
            if start_sec >= end_sec:
                await update.message.reply_text("⚠️ زمان پایان باید بعد از زمان شروع باشد!")
                return VIDEO_TRIM
                
            if end_sec > duration:
                await update.message.reply_text(f"⚠️ ویدئو فقط {duration} ثانیه است!")
                return VIDEO_TRIM
                
            user_data[user_id]["trim_times"] = (start_sec, end_sec)
            await process_media(update, context)
            return ConversationHandler.END
            
        except ValueError:
            await update.message.reply_text(
                "⚠️ فرمت زمان نامعتبر! لطفاً به صورت «دقیقه:ثانیه» وارد کنید."
            )
            return VIDEO_TRIM
    
    else:
        await update.message.reply_text("⚠️ دستور نامعتبر!")
        return CROP_DETAILS

async def ask_resize_option(message) -> None:
    """درخواست گزینه تغییر اندازه"""
    keyboard = [
        [InlineKeyboardButton("✅ بله", callback_data="resize_yes"),
        InlineKeyboardButton("❌ خیر", callback_data="resize_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if isinstance(message, Update):
        await message.message.reply_text(
            "🔍 آیا می‌خواهید تصویر را تغییر اندازه دهید؟",
            reply_markup=reply_markup
        )
    else:
        await message.reply_text(
            "🔍 آیا می‌خواهید تصویر را تغییر اندازه دهید؟",
            reply_markup=reply_markup
        )

async def handle_resize_option(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """پردازش انتخاب تغییر اندازه"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    option = query.data
    
    if option == "resize_no":
        await process_media(query)
        return ConversationHandler.END
    else:
        await query.edit_message_text(
            "📏 لطفاً اندازه جدید را به صورت «عرضxارتفاع» وارد کنید\n"
            "یا درصد تغییر اندازه را وارد کنید (مثال: 70%):"
        )
        return RESIZE_OPTION

async def process_resize(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """پردازش تغییر اندازه"""
    user_id = update.message.from_user.id
    text = update.message.text
    orig_width, orig_height = user_data[user_id]["original_size"]
    
    try:
        if '%' in text:
            # تغییر اندازه بر اساس درصد
            percent = int(text.replace('%', ''))
            if percent <= 0 or percent > 200:
                raise ValueError
            
            user_data[user_id]["resize_percent"] = percent
        elif 'x' in text:
            # تغییر اندازه به ابعاد خاص
            width, height = map(int, text.split('x'))
            if width > orig_width * 2 or height > orig_height * 2:
                await update.message.reply_text("⚠️ اندازه جدید بیش از حد بزرگ است!")
                return RESIZE_OPTION
                
            user_data[user_id]["resize_size"] = (width, height)
        else:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ فرمت نامعتبر! لطفاً اندازه یا درصد وارد کنید.")
        return RESIZE_OPTION
    
    await process_media(update.message)
    return ConversationHandler.END

async def process_media(message) -> None:
    """پردازش نهایی رسانه"""
    if isinstance(message, Update):
        user_id = message.message.from_user.id
        chat_id = message.message.chat_id
    else:
        user_id = message.from_user.id
        chat_id = message.chat_id
    
    data = user_data[user_id]
    media_type = data["media_type"]
    original_path = data["original_path"]
    
    # اطلاع پردازش
    if isinstance(message, Update):
        await message.callback_query.edit_message_text("⚙️ در حال پردازش... لطفاً منتظر بمانید")
    else:
        await message.reply_text("⚙️ در حال پردازش... لطفاً منتظر بمانید")
    
    try:
        if media_type == "photo":
            output_path = await process_image(data)
            await send_photo_result(chat_id, data, output_path, context)
        else:
            output_path = await process_video(data)
            await send_video_result(chat_id, data, output_path, context)
        
        # پاکسازی فایل‌های موقت
        cleanup_files(user_id)
        del user_data[user_id]
        
    except Exception as e:
        logger.error(f"Processing error: {e}")
        if isinstance(message, Update):
            await message.callback_query.edit_message_text(f"❌ خطا در پردازش: {str(e)}")
        else:
            await message.reply_text(f"❌ خطا در پردازش: {str(e)}")

async def process_image(data: dict) -> str:
    """پردازش تصویر"""
    with Image.open(data["original_path"]) as img:
        # اعمال برش
        if "crop_size" in data:
            width, height = data["crop_size"]
            orig_width, orig_height = img.size
            
            # محاسبه مختصات مرکز
            left = (orig_width - width) // 2
            top = (orig_height - height) // 2
            right = left + width
            bottom = top + height
            
            img = img.crop((left, top, right, bottom))
        
        # اعمال تغییر اندازه
        if "resize_percent" in data:
            percent = data["resize_percent"]
            new_width = int(img.width * percent / 100)
            new_height = int(img.height * percent / 100)
            img = img.resize((new_width, new_height), Image.LANCZOS)
        elif "resize_size" in data:
            width, height = data["resize_size"]
            img = img.resize((width, height), Image.LANCZOS)
        
        # ذخیره نتیجه
        output_path = os.path.join(TEMP_DIR, f"user_{user_id}", "result.jpg")
        img.save(output_path, quality=95)
        
        # ذخیره اطلاعات برای ارسال
        data["final_size"] = img.size
    
    return output_path

async def process_video(data: dict) -> str:
    """پردازش ویدئو"""
    with VideoFileClip(data["original_path"]) as video:
        # اعمال برش زمانی
        if "trim_times" in data:
            start, end = data["trim_times"]
            video = video.subclip(start, end)
        
        # اعمال برش تصویری
        if "crop_size" in data:
            width, height = data["crop_size"]
            orig_width, orig_height = video.size
            
            # محاسبه مختصات مرکز
            x_center = orig_width // 2
            y_center = orig_height // 2
            x1 = x_center - width // 2
            x2 = x_center + width // 2
            y1 = y_center - height // 2
            y2 = y_center + height // 2
            
            video = video.crop(x1=x1, y1=y1, x2=x2, y2=y2)
        
        # اعمال تغییر اندازه
        if "resize_percent" in data:
            percent = data["resize_percent"]
            new_width = int(video.w * percent / 100)
            new_height = int(video.h * percent / 100)
            video = video.resize((new_width, new_height))
        elif "resize_size" in data:
            width, height = data["resize_size"]
            video = video.resize((width, height))
        
        # ذخیره نتیجه
        output_path = os.path.join(TEMP_DIR, f"user_{user_id}", "result.mp4")
        video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            threads=4,
            preset='medium',
            ffmpeg_params=['-crf', '23']
        )
        
        # ذخیره اطلاعات برای ارسال
        data["final_size"] = (video.w, video.h)
        data["final_duration"] = video.duration
    
    return output_path

async def send_photo_result(chat_id: int, data: dict, path: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ارسال نتیجه نهایی عکس"""
    orig_width, orig_height = data["original_size"]
    final_width, final_height = data["final_size"]
    
    caption = (
        f"✅ عملیات برش با موفقیت انجام شد!\n\n"
        f"📐 ابعاد اصلی: {orig_width}×{orig_height} پیکسل\n"
        f"✂️ ابعاد نهایی: {final_width}×{final_height} پیکسل\n"
        f"📉 کاهش حجم: {100 - int((final_width * final_height) / (orig_width * orig_height) * 100)}%"
    )
    
    with open(path, "rb") as photo:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption
        )

async def send_video_result(chat_id: int, data: dict, path: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ارسال نتیجه نهایی ویدئو"""
    orig_width, orig_height = data["original_size"]
    final_width, final_height = data["final_size"]
    orig_duration = data["duration"]
    final_duration = data.get("final_duration", orig_duration)
    
    caption = (
        f"✅ عملیات برش با موفقیت انجام شد!\n\n"
        f"🎥 ابعاد اصلی: {orig_width}×{orig_height} پیکسل\n"
        f"⏱️ مدت اصلی: {str(timedelta(seconds=int(orig_duration)))}\n"
        f"✂️ ابعاد نهایی: {final_width}×{final_height} پیکسل\n"
        f"⏱️ مدت نهایی: {str(timedelta(seconds=int(final_duration))}\n"
        f"📉 کاهش حجم: {100 - int((final_width * final_height * final_duration) / (orig_width * orig_height * orig_duration) * 100)}%"
    )
    
    with open(path, "rb") as video:
        await context.bot.send_video(
            chat_id=chat_id,
            video=video,
            caption=caption,
            supports_streaming=True
        )

def time_to_seconds(time_str: str) -> float:
    """تبدیل زمان به ثانیه"""
    if ':' in time_str:
        parts = time_str.split(':')
        if len(parts) == 2:  # MM:SS
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:  # HH:MM:SS
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return float(time_str)  # ثانیه مستقیم

def cleanup_files(user_id: int) -> None:
    """پاکسازی فایل‌های موقت"""
    user_dir = os.path.join(TEMP_DIR, f"user_{user_id}")
    for file in os.listdir(user_dir):
        os.remove(os.path.join(user_dir, file))
    os.rmdir(user_dir)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """لغو عملیات"""
    user_id = update.message.from_user.id
    if user_id in user_data:
        cleanup_files(user_id)
        del user_data[user_id]
        
    await update.message.reply_text("❌ عملیات لغو شد!")
    return ConversationHandler.END

def main() -> None:
    """اجرای ربات"""
    TOKEN = "7685135237:AAEmsHktRw9cEqrHTkCoPZk-fBimK7TDjOo"
    
    app = Application.builder().token(TOKEN).build()
    
    # تنظیم مکالمه
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MEDIA_TYPE: [CallbackQueryHandler(handle_media_type)],
            CROP_METHOD: [MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.VIDEO, handle_media)],
            CROP_DETAILS: [
                CallbackQueryHandler(handle_standard, pattern=r"^std_"),
                CallbackQueryHandler(handle_custom_size, pattern=r"^custom$"),
                CallbackQueryHandler(handle_custom_size, pattern=r"^zoom$")
            ],
            RESIZE_OPTION: [
                CallbackQueryHandler(handle_resize_option),
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_resize)
            ],
            VIDEO_TRIM: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_crop_instruction)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=MAX_PROCESSING_TIME
    )
    
    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()