import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackContext
)
from PIL import Image

# تنظیمات اولیه
TOKEN = "7685135237:AAEmsHktRw9cEqrHTkCoPZk-fBimK7TDjOo"  # توکن ربات خود را جایگزین کنید
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# مراحل مکالمه
SELECT_ACTION, VIDEO_TRIM, IMAGE_RESIZE = range(3)

# --- توابع اصلی ---
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(
        "🤖 به ربات ویرایشگر رسانه خوش آمدید!\n"
        "📸 برای تغییر اندازه عکس: /resize_image\n"
        "🎬 برای برش ویدیو: /trim_video"
    )

async def resize_image(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        "🖼️ لطفاً تصویر مورد نظر خود را ارسال کنید..."
    )
    return IMAGE_RESIZE

async def trim_video(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        "🎥 لطفاً ویدیوی مورد نظر خود را ارسال کنید..."
    )
    return VIDEO_TRIM

# --- پردازش تصاویر ---
async def process_image(update: Update, context: CallbackContext) -> int:
    photo = update.message.photo[-1]
    file = await photo.get_file()
    
    # ذخیره تصویر اصلی
    input_path = f"temp_{update.message.from_user.id}.jpg"
    await file.download_to_drive(input_path)
    
    context.user_data['image_path'] = input_path
    
    await update.message.reply_text(
        "📏 ابعاد جدید را وارد کنید (عرض و ارتفاع با فاصله):\n"
        "مثال: 800 600"
    )
    return SELECT_ACTION

async def apply_image_resize(update: Update, context: CallbackContext) -> int:
    try:
        width, height = map(int, update.message.text.split())
        img_path = context.user_data['image_path']
        
        # تغییر سایز تصویر
        img = Image.open(img_path)
        img = img.resize((width, height))
        
        # ذخیره نتیجه
        output_path = f"result_{update.message.from_user.id}.jpg"
        img.save(output_path)
        
        # ارسال نتیجه
        await update.message.reply_photo(
            photo=open(output_path, 'rb'),
            caption=f"✅ تصویر با ابعاد جدید {width}x{height}"
        )
        
        # پاک کردن فایل‌های موقت
        os.remove(img_path)
        os.remove(output_path)
        
    except Exception as e:
        await update.message.reply_text(f"❌ خطا: {str(e)}")
    
    return ConversationHandler.END

# --- پردازش ویدیو ---
async def process_video(update: Update, context: CallbackContext) -> int:
    video = update.message.video
    if not video:
        await update.message.reply_text("❌ لطفاً یک ویدیو معتبر ارسال کنید!")
        return ConversationHandler.END
    
    file = await video.get_file()
    
    # ذخیره ویدیو اصلی
    input_path = f"temp_{update.message.from_user.id}.mp4"
    await file.download_to_drive(input_path)
    
    context.user_data['video_path'] = input_path
    context.user_data['duration'] = video.duration
    
    await update.message.reply_text(
        f"⏳ مدت ویدیو: {video.duration} ثانیه\n"
        "⏱️ محدوده برش را وارد کنید (شروع و پایان با فاصله):\n"
        "مثال: 10 25"
    )
    return SELECT_ACTION

async def apply_video_trim(update: Update, context: CallbackContext) -> int:
    try:
        start_time, end_time = map(float, update.message.text.split())
        video_path = context.user_data['video_path']
        duration = context.user_data['duration']
        
        # اعتبارسنجی زمان‌ها
        if start_time < 0 or end_time > duration or start_time >= end_time:
            await update.message.reply_text("❌ محدوده زمانی نامعتبر!")
            return ConversationHandler.END
        
        # برش ویدیو با FFmpeg
        output_path = f"trimmed_{update.message.from_user.id}.mp4"
        os.system(
            f"ffmpeg -i {video_path} -ss {start_time} -to {end_time} "
            f"-c copy {output_path} -loglevel quiet -y"
        )
        
        # ارسال نتیجه
        await update.message.reply_video(
            video=open(output_path, 'rb'),
            caption=f"✅ ویدیو از {start_time} تا {end_time} ثانیه"
        )
        
        # پاک کردن فایل‌های موقت
        os.remove(video_path)
        os.remove(output_path)
        
    except Exception as e:
        await update.message.reply_text(f"❌ خطا: {str(e)}")
    
    return ConversationHandler.END

# --- تنظیمات اصلی ربات ---
def main() -> None:
    application = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('resize_image', resize_image),
            CommandHandler('trim_video', trim_video)
        ],
        states={
            IMAGE_RESIZE: [MessageHandler(filters.PHOTO, process_image)],
            VIDEO_TRIM: [MessageHandler(filters.VIDEO, process_video)],
            SELECT_ACTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, apply_video_trim),
                MessageHandler(filters.TEXT & ~filters.COMMAND, apply_image_resize)
            ]
        },
        fallbacks=[CommandHandler('cancel', lambda u,c: ConversationHandler.END)]
    )
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(conv_handler)
    
    application.run_polling()

if __name__ == '__main__':
    main()