import logging
import os
import io
import asyncio
from typing import Optional, Tuple, List
import tempfile
import shutil
from pathlib import Path

# Telegram Bot
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode

# Image Processing
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import cv2
import numpy as np

# Configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Token - باید توکن ربات خود را اینجا قرار دهید
BOT_TOKEN = "7685135237:AAEmsHktRw9cEqrHTkCoPZk-fBimK7TDjOo"

# حداکثر حجم فایل (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# پوشه موقت برای ذخیره فایل‌ها
TEMP_DIR = Path("temp_images")
TEMP_DIR.mkdir(exist_ok=True)

class ImageProcessor:
    """کلاس پردازش تصاویر با قابلیت‌های پیشرفته"""
    
    @staticmethod
    def load_image(file_path: str) -> Optional[Image.Image]:
        """بارگذاری تصویر با پشتیبانی از فرمت‌های مختلف"""
        try:
            img = Image.open(file_path)
            # تبدیل به RGB در صورت نیاز
            if img.mode in ('RGBA', 'P', 'L'):
                img = img.convert('RGB')
            return img
        except Exception as e:
            logger.error(f"خطا در بارگذاری تصویر: {e}")
            return None
    
    @staticmethod
    def crop_image(image: Image.Image, x: int, y: int, width: int, height: int) -> Optional[Image.Image]:
        """برش تصویر با مختصات مشخص"""
        try:
            # بررسی محدودیت‌ها
            img_width, img_height = image.size
            
            # اصلاح مختصات منفی
            x = max(0, x)
            y = max(0, y)
            
            # اصلاح ابعاد خارج از محدوده
            if x + width > img_width:
                width = img_width - x
            if y + height > img_height:
                height = img_height - y
            
            # بررسی صحت ابعاد
            if width <= 0 or height <= 0:
                return None
            
            # برش تصویر
            cropped = image.crop((x, y, x + width, y + height))
            return cropped
            
        except Exception as e:
            logger.error(f"خطا در برش تصویر: {e}")
            return None
    
    @staticmethod
    def resize_image(image: Image.Image, new_width: int, new_height: int, maintain_aspect: bool = False) -> Image.Image:
        """تغییر اندازه تصویر"""
        try:
            if maintain_aspect:
                image.thumbnail((new_width, new_height), Image.Resampling.LANCZOS)
                return image
            else:
                return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        except Exception as e:
            logger.error(f"خطا در تغییر اندازه: {e}")
            return image
    
    @staticmethod
    def crop_to_aspect_ratio(image: Image.Image, aspect_width: int, aspect_height: int) -> Image.Image:
        """برش تصویر بر اساس نسبت ابعاد"""
        try:
            img_width, img_height = image.size
            target_ratio = aspect_width / aspect_height
            current_ratio = img_width / img_height
            
            if current_ratio > target_ratio:
                # تصویر عریض‌تر از نسبت هدف
                new_width = int(img_height * target_ratio)
                x = (img_width - new_width) // 2
                return image.crop((x, 0, x + new_width, img_height))
            else:
                # تصویر بلندتر از نسبت هدف
                new_height = int(img_width / target_ratio)
                y = (img_height - new_height) // 2
                return image.crop((0, y, img_width, y + new_height))
                
        except Exception as e:
            logger.error(f"خطا در برش نسبت ابعاد: {e}")
            return image
    
    @staticmethod
    def smart_crop(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
        """برش هوشمند با تشخیص محتوا"""
        try:
            img_width, img_height = image.size
            
            # تبدیل به آرایه numpy
            img_array = np.array(image)
            
            # تشخیص لبه‌ها
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            
            # یافتن مناطق با بیشترین فعالیت
            kernel = np.ones((target_height//10, target_width//10), np.uint8)
            density = cv2.filter2D(edges.astype(np.float32), -1, kernel)
            
            # یافتن بهترین موقعیت برای برش
            max_loc = cv2.minMaxLoc(density)[3]
            
            # محاسبه مختصات برش
            x = max(0, max_loc[0] - target_width//2)
            y = max(0, max_loc[1] - target_height//2)
            
            # اصلاح محدودیت‌ها
            if x + target_width > img_width:
                x = img_width - target_width
            if y + target_height > img_height:
                y = img_height - target_height
            
            return image.crop((x, y, x + target_width, y + target_height))
            
        except Exception as e:
            logger.error(f"خطا در برش هوشمند: {e}")
            # برش از مرکز در صورت خطا
            return ImageProcessor.center_crop(image, target_width, target_height)
    
    @staticmethod
    def center_crop(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
        """برش از مرکز تصویر"""
        img_width, img_height = image.size
        
        x = (img_width - target_width) // 2
        y = (img_height - target_height) // 2
        
        x = max(0, x)
        y = max(0, y)
        
        return image.crop((x, y, x + target_width, y + target_height))
    
    @staticmethod
    def create_collage(images: List[Image.Image], rows: int, cols: int) -> Image.Image:
        """ایجاد کولاژ از چندین تصویر"""
        if not images:
            return None
        
        # محاسبه اندازه هر سلول
        cell_width = max(img.width for img in images) // cols
        cell_height = max(img.height for img in images) // rows
        
        # ایجاد کانواس
        canvas_width = cell_width * cols
        canvas_height = cell_height * rows
        canvas = Image.new('RGB', (canvas_width, canvas_height), 'white')
        
        # قرار دادن تصاویر
        for i, img in enumerate(images[:rows*cols]):
            row = i // cols
            col = i % cols
            
            # تغییر اندازه تصویر
            img_resized = img.resize((cell_width, cell_height), Image.Resampling.LANCZOS)
            
            # قرار دادن در کانواس
            x = col * cell_width
            y = row * cell_height
            canvas.paste(img_resized, (x, y))
        
        return canvas

class TelegramBot:
    """کلاس اصلی ربات تلگرام"""
    
    def __init__(self, token: str):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.user_data = {}  # ذخیره داده‌های کاربران
        
        # ثبت handlers
        self.setup_handlers()
    
    def setup_handlers(self):
        """تنظیم handlers مختلف"""
        # دستورات
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("presets", self.show_presets))
        
        # پیام‌های تصویری
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.application.add_handler(MessageHandler(filters.Document.IMAGE, self.handle_document))
        
        # پیام‌های متنی
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        
        # callback queries
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور شروع"""
        welcome_text = """
🎨 **ربات برش تصاویر پیشرفته** 🎨

این ربات قادر به انجام انواع برش و تغییرات روی تصاویر شماست:

✨ **قابلیت‌ها:**
• برش دقیق با مختصات
• برش بر اساس نسبت ابعاد
• برش هوشمند با تشخیص محتوا
• تغییر اندازه تصاویر
• پیش‌تنظیمات آماده
• پشتیبانی از تمام فرمت‌های تصویری

📝 **نحوه استفاده:**
1. تصویر خود را ارسال کنید
2. دستور برش را بنویسید
3. تصویر برش خورده را دریافت کنید

💡 **مثال‌های دستورات:**
• `crop 100 200 300 400` - برش با مختصات
• `resize 800 600` - تغییر اندازه
• `square` - برش مربعی
• `16:9` - برش با نسبت 16:9

برای مشاهده تمام دستورات: /help
برای پیش‌تنظیمات آماده: /presets
        """
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """راهنمای کامل"""
        help_text = """
📖 **راهنمای کامل ربات برش تصاویر**

**🔸 برش با مختصات:**
`crop x y width height`
مثال: `crop 100 50 300 200`

**🔸 برش مربعی:**
`square` یا `square 500`

**🔸 برش مستطیلی:**
`rectangle width height`
مثال: `rectangle 400 300`

**🔸 برش با نسبت ابعاد:**
`ratio width:height`
مثال: `16:9`, `4:3`, `1:1`

**🔸 تغییر اندازه:**
`resize width height`
مثال: `resize 800 600`

**🔸 برش هوشمند:**
`smart width height`
مثال: `smart 400 300`

**🔸 برش از مرکز:**
`center width height`
مثال: `center 500 400`

**🔸 پیش‌تنظیمات شبکه‌های اجتماعی:**
• `instagram` - 1080x1080
• `instagram_story` - 1080x1920
• `facebook` - 1200x630
• `twitter` - 1024x512
• `youtube` - 1280x720
• `linkedin` - 1200x627

**🔸 اندازه‌های کاغذ:**
• `a4` - 210x297mm
• `a3` - 297x420mm
• `letter` - 8.5x11 inch

**💡 نکات مهم:**
• حداکثر حجم فایل: 50MB
• فرمت‌های پشتیبانی: JPG, PNG, GIF, BMP, TIFF
• برای ابعاد بزرگ از فشرده‌سازی استفاده می‌شود
        """
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def show_presets(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش پیش‌تنظیمات"""
        keyboard = [
            [
                InlineKeyboardButton("📱 Instagram (1:1)", callback_data="preset_instagram"),
                InlineKeyboardButton("📱 Instagram Story", callback_data="preset_instagram_story")
            ],
            [
                InlineKeyboardButton("📘 Facebook Cover", callback_data="preset_facebook"),
                InlineKeyboardButton("🐦 Twitter Header", callback_data="preset_twitter")
            ],
            [
                InlineKeyboardButton("📺 YouTube Thumbnail", callback_data="preset_youtube"),
                InlineKeyboardButton("💼 LinkedIn Post", callback_data="preset_linkedin")
            ],
            [
                InlineKeyboardButton("🎬 16:9 Widescreen", callback_data="preset_16_9"),
                InlineKeyboardButton("📺 4:3 Standard", callback_data="preset_4_3")
            ],
            [
                InlineKeyboardButton("⬜ مربع 500x500", callback_data="preset_square_500"),
                InlineKeyboardButton("⬜ مربع 1000x1000", callback_data="preset_square_1000")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🎯 **پیش‌تنظیمات آماده:**\n\nتصویر خود را ارسال کنید و سپس یکی از گزینه‌های زیر را انتخاب کنید:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش تصاویر ارسالی"""
        try:
            # دریافت فایل با بالاترین کیفیت
            photo = update.message.photo[-1]
            
            # بررسی حجم فایل
            if photo.file_size > MAX_FILE_SIZE:
                await update.message.reply_text(
                    f"❌ حجم فایل بیش از حد مجاز است. حداکثر: {MAX_FILE_SIZE//1024//1024}MB"
                )
                return
            
            # دانلود فایل
            file = await context.bot.get_file(photo.file_id)
            file_path = TEMP_DIR / f"{update.effective_user.id}_{photo.file_unique_id}.jpg"
            
            await file.download_to_drive(file_path)
            
            # ذخیره اطلاعات کاربر
            user_id = update.effective_user.id
            self.user_data[user_id] = {
                'image_path': str(file_path),
                'original_size': None
            }
            
            # بارگذاری تصویر برای دریافت اطلاعات
            img = ImageProcessor.load_image(str(file_path))
            if img:
                self.user_data[user_id]['original_size'] = img.size
                
                await update.message.reply_text(
                    f"✅ **تصویر دریافت شد!**\n\n"
                    f"📏 اندازه اصلی: {img.size[0]}x{img.size[1]} پیکسل\n\n"
                    f"💡 حالا دستور برش خود را بنویسید:\n"
                    f"مثال: `crop 0 0 400 300`\n"
                    f"یا از /presets استفاده کنید",
                    parse_mode=ParseMode.MARKDOWN
                )
            
        except Exception as e:
            logger.error(f"خطا در پردازش تصویر: {e}")
            await update.message.reply_text("❌ خطا در پردازش تصویر. لطفاً دوباره تلاش کنید.")
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش فایل‌های تصویری ارسالی"""
        try:
            document = update.message.document
            
            # بررسی نوع فایل
            if not document.mime_type.startswith('image/'):
                await update.message.reply_text("❌ لطفاً فقط فایل‌های تصویری ارسال کنید.")
                return
            
            # بررسی حجم فایل
            if document.file_size > MAX_FILE_SIZE:
                await update.message.reply_text(
                    f"❌ حجم فایل بیش از حد مجاز است. حداکثر: {MAX_FILE_SIZE//1024//1024}MB"
                )
                return
            
            # دانلود فایل
            file = await context.bot.get_file(document.file_id)
            file_extension = document.file_name.split('.')[-1].lower()
            file_path = TEMP_DIR / f"{update.effective_user.id}_{document.file_unique_id}.{file_extension}"
            
            await file.download_to_drive(file_path)
            
            # ذخیره اطلاعات کاربر
            user_id = update.effective_user.id
            self.user_data[user_id] = {
                'image_path': str(file_path),
                'original_size': None
            }
            
            # بارگذاری تصویر
            img = ImageProcessor.load_image(str(file_path))
            if img:
                self.user_data[user_id]['original_size'] = img.size
                
                await update.message.reply_text(
                    f"✅ **فایل تصویری دریافت شد!**\n\n"
                    f"📁 نام فایل: {document.file_name}\n"
                    f"📏 اندازه: {img.size[0]}x{img.size[1]} پیکسل\n"
                    f"💾 حجم: {document.file_size/1024:.1f} KB\n\n"
                    f"💡 دستور برش خود را بنویسید یا از /presets استفاده کنید",
                    parse_mode=ParseMode.MARKDOWN
                )
            
        except Exception as e:
            logger.error(f"خطا در پردازش فایل: {e}")
            await update.message.reply_text("❌ خطا در پردازش فایل. لطفاً دوباره تلاش کنید.")
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش دستورات متنی"""
        user_id = update.effective_user.id
        text = update.message.text.strip().lower()
        
        # بررسی وجود تصویر
        if user_id not in self.user_data:
            await update.message.reply_text(
                "❌ ابتدا تصویری ارسال کنید.\n\n"
                "برای شروع از دستور /start استفاده کنید."
            )
            return
        
        try:
            # بارگذاری تصویر
            img_path = self.user_data[user_id]['image_path']
            img = ImageProcessor.load_image(img_path)
            
            if not img:
                await update.message.reply_text("❌ خطا در بارگذاری تصویر. لطفاً دوباره ارسال کنید.")
                return
            
            # پردازش دستور
            result_img = await self.process_command(text, img, update)
            
            if result_img:
                # ذخیره تصویر نتیجه
                output_path = TEMP_DIR / f"result_{user_id}_{hash(text)}.jpg"
                
                # بهینه‌سازی کیفیت بر اساس اندازه
                quality = 95
                if result_img.size[0] * result_img.size[1] > 2000000:  # بیش از 2MP
                    quality = 85
                elif result_img.size[0] * result_img.size[1] > 5000000:  # بیش از 5MP
                    quality = 75
                
                result_img.save(output_path, "JPEG", quality=quality, optimize=True)
                
                # ارسال نتیجه
                with open(output_path, 'rb') as f:
                    await query.message.reply_photo(
                        photo=f,
                        caption=f"✅ **{preset} اعمال شد!**\n📏 اندازه: {result_img.size[0]}x{result_img.size[1]} پیکسل",
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                # حذف فایل موقت
                output_path.unlink(missing_ok=True)
            
        except Exception as e:
            logger.error(f"خطا در callback: {e}")
            await query.message.reply_text("❌ خطا در اجرای preset")
    
    def cleanup_temp_files(self):
        """پاک‌سازی فایل‌های موقت قدیمی"""
        try:
            import time
            current_time = time.time()
            
            for file_path in TEMP_DIR.glob("*"):
                if file_path.is_file():
                    # فایل‌های بیش از 1 ساعت قدیمی را حذف کن
                    if current_time - file_path.stat().st_mtime > 3600:
                        file_path.unlink(missing_ok=True)
                        
        except Exception as e:
            logger.error(f"خطا در پاک‌سازی: {e}")
    
    async def periodic_cleanup(self):
        """پاک‌سازی دوره‌ای فایل‌ها"""
        while True:
            await asyncio.sleep(1800)  # هر 30 دقیقه
            self.cleanup_temp_files()
    
    def run(self):
        """اجرای ربات"""
        logger.info("ربات در حال راه‌اندازی...")
        
        # شروع پاک‌سازی دوره‌ای در background
        asyncio.create_task(self.periodic_cleanup())
        
        # اجرای ربات
        self.application.run_polling(drop_pending_updates=True)

# کلاس‌های اضافی برای قابلیت‌های پیشرفته‌تر

class AdvancedImageProcessor:
    """پردازشگر پیشرفته تصاویر با قابلیت‌های اضافی"""
    
    @staticmethod
    def create_grid_crop(image: Image.Image, grid_size: int) -> List[Image.Image]:
        """تقسیم تصویر به شبکه‌ای از قطعات کوچک"""
        width, height = image.size
        cell_width = width // grid_size
        cell_height = height // grid_size
        
        crops = []
        for row in range(grid_size):
            for col in range(grid_size):
                x = col * cell_width
                y = row * cell_height
                crop = image.crop((x, y, x + cell_width, y + cell_height))
                crops.append(crop)
        
        return crops
    
    @staticmethod
    def create_circular_crop(image: Image.Image, diameter: int) -> Image.Image:
        """برش دایره‌ای تصویر"""
        # تغییر اندازه به مربع
        size = min(image.size)
        image = ImageProcessor.center_crop(image, size, size)
        image = image.resize((diameter, diameter), Image.Resampling.LANCZOS)
        
        # ایجاد ماسک دایره‌ای
        mask = Image.new('L', (diameter, diameter), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, diameter, diameter), fill=255)
        
        # اعمال ماسک
        result = Image.new('RGBA', (diameter, diameter), (0, 0, 0, 0))
        result.paste(image, (0, 0))
        result.putalpha(mask)
        
        return result
    
    @staticmethod
    def create_rounded_corners(image: Image.Image, radius: int) -> Image.Image:
        """ایجاد گوشه‌های گرد"""
        width, height = image.size
        
        # ایجاد ماسک با گوشه‌های گرد
        mask = Image.new('L', (width, height), 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((0, 0, width, height), radius=radius, fill=255)
        
        # تبدیل به RGBA و اعمال ماسک
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        image.putalpha(mask)
        return image
    
    @staticmethod
    def add_border(image: Image.Image, border_width: int, border_color: str = "black") -> Image.Image:
        """اضافه کردن حاشیه به تصویر"""
        width, height = image.size
        new_width = width + 2 * border_width
        new_height = height + 2 * border_width
        
        # ایجاد تصویر جدید با حاشیه
        bordered = Image.new('RGB', (new_width, new_height), border_color)
        bordered.paste(image, (border_width, border_width))
        
        return bordered
    
    @staticmethod
    def create_polaroid_effect(image: Image.Image) -> Image.Image:
        """ایجاد افکت پولاروید"""
        # تنظیم اندازه
        max_size = 800
        if image.size[0] > max_size or image.size[1] > max_size:
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        width, height = image.size
        
        # اضافه کردن حاشیه سفید (مثل پولاروید)
        border_width = min(width, height) // 20
        bottom_border = border_width * 3  # حاشیه پایین بزرگ‌تر
        
        new_width = width + 2 * border_width
        new_height = height + border_width + bottom_border
        
        polaroid = Image.new('RGB', (new_width, new_height), 'white')
        polaroid.paste(image, (border_width, border_width))
        
        return polaroid

class BatchProcessor:
    """پردازش دسته‌ای تصاویر"""
    
    @staticmethod
    def process_multiple_sizes(image: Image.Image, sizes: List[Tuple[int, int]]) -> List[Image.Image]:
        """ایجاد چندین اندازه از یک تصویر"""
        results = []
        for width, height in sizes:
            # برش مرکزی با حفظ نسبت
            cropped = ImageProcessor.crop_to_aspect_ratio(image, width, height)
            resized = cropped.resize((width, height), Image.Resampling.LANCZOS)
            results.append(resized)
        
        return results
    
    @staticmethod
    def create_social_media_pack(image: Image.Image) -> dict:
        """ایجاد پک کامل برای شبکه‌های اجتماعی"""
        sizes = {
            'instagram_post': (1080, 1080),
            'instagram_story': (1080, 1920),
            'facebook_post': (1200, 630),
            'facebook_cover': (820, 312),
            'twitter_post': (1024, 512),
            'twitter_header': (1500, 500),
            'youtube_thumbnail': (1280, 720),
            'linkedin_post': (1200, 627),
            'pinterest': (1000, 1500)
        }
        
        pack = {}
        for name, (width, height) in sizes.items():
            try:
                cropped = ImageProcessor.crop_to_aspect_ratio(image, width, height)
                resized = cropped.resize((width, height), Image.Resampling.LANCZOS)
                pack[name] = resized
            except Exception as e:
                logger.error(f"خطا در ایجاد {name}: {e}")
        
        return pack

# تنظیمات اضافی و utility functions

class ImageAnalyzer:
    """تجزیه و تحلیل تصاویر"""
    
    @staticmethod
    def get_dominant_colors(image: Image.Image, num_colors: int = 5) -> List[tuple]:
        """استخراج رنگ‌های غالب تصویر"""
        try:
            # تبدیل به RGB
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # کاهش اندازه برای سرعت بیشتر
            image.thumbnail((150, 150))
            
            # تبدیل به آرایه numpy
            pixels = np.array(image).reshape(-1, 3)
            
            # حذف پیکسل‌های تکراری
            unique_colors, counts = np.unique(pixels, axis=0, return_counts=True)
            
            # مرتب‌سازی بر اساس تعداد
            sorted_indices = np.argsort(counts)[::-1]
            dominant_colors = unique_colors[sorted_indices[:num_colors]]
            
            return [tuple(color) for color in dominant_colors]
            
        except Exception as e:
            logger.error(f"خطا در تحلیل رنگ: {e}")
            return [(0, 0, 0)]
    
    @staticmethod
    def detect_faces(image: Image.Image) -> List[Tuple[int, int, int, int]]:
        """تشخیص چهره در تصویر"""
        try:
            # تبدیل به OpenCV format
            img_array = np.array(image)
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            
            # بارگذاری cascade classifier
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            
            # تشخیص چهره‌ها
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            
            return [(int(x), int(y), int(w), int(h)) for x, y, w, h in faces]
            
        except Exception as e:
            logger.error(f"خطا در تشخیص چهره: {e}")
            return []
    
    @staticmethod
    def smart_crop_with_faces(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
        """برش هوشمند با در نظر گیری چهره‌ها"""
        faces = ImageAnalyzer.detect_faces(image)
        
        if not faces:
            # اگر چهره‌ای پیدا نشد، برش معمولی انجام بده
            return ImageProcessor.smart_crop(image, target_width, target_height)
        
        # محاسبه مرکز چهره‌ها
        face_centers = []
        for x, y, w, h in faces:
            center_x = x + w // 2
            center_y = y + h // 2
            face_centers.append((center_x, center_y))
        
        # میانگین مراکز چهره‌ها
        avg_x = sum(c[0] for c in face_centers) // len(face_centers)
        avg_y = sum(c[1] for c in face_centers) // len(face_centers)
        
        # محاسبه موقعیت برش
        img_width, img_height = image.size
        
        crop_x = max(0, min(avg_x - target_width // 2, img_width - target_width))
        crop_y = max(0, min(avg_y - target_height // 2, img_height - target_height))
        
        return image.crop((crop_x, crop_y, crop_x + target_width, crop_y + target_height))

# اضافه کردن دستورات پیشرفته به کلاس TelegramBot

def extend_telegram_bot():
    """توسعه کلاس TelegramBot با قابلیت‌های اضافی"""
    
    # اضافه کردن دستورات جدید به handle_text
    original_process_command = TelegramBot.process_command
    
    async def extended_process_command(self, command: str, image: Image.Image, update: Update) -> Optional[Image.Image]:
        parts = command.split()
        cmd = parts[0]
        
        try:
            # دستورات جدید
            if cmd == "circle" or cmd == "circular":
                diameter = int(parts[1]) if len(parts) > 1 else min(image.size)
                return AdvancedImageProcessor.create_circular_crop(image, diameter)
            
            elif cmd == "round" or cmd == "rounded":
                radius = int(parts[1]) if len(parts) > 1 else 50
                return AdvancedImageProcessor.create_rounded_corners(image, radius)
            
            elif cmd == "border":
                width = int(parts[1]) if len(parts) > 1 else 10
                color = parts[2] if len(parts) > 2 else "black"
                return AdvancedImageProcessor.add_border(image, width, color)
            
            elif cmd == "polaroid":
                return AdvancedImageProcessor.create_polaroid_effect(image)
            
            elif cmd == "face" or cmd == "faces":
                if len(parts) >= 3:
                    width, height = map(int, parts[1:3])
                    return ImageAnalyzer.smart_crop_with_faces(image, width, height)
            
            elif cmd == "grid":
                grid_size = int(parts[1]) if len(parts) > 1 else 3
                crops = AdvancedImageProcessor.create_grid_crop(image, grid_size)
                # برگرداندن اولین قطعه (می‌توان تمام قطعات را ارسال کرد)
                return crops[0] if crops else None
            
            elif cmd == "social" or cmd == "pack":
                # ایجاد پک شبکه‌های اجتماعی
                pack = BatchProcessor.create_social_media_pack(image)
                
                # ارسال پیام با اطلاعات پک
                await update.message.reply_text(
                    f"📦 **پک شبکه‌های اجتماعی آماده شد!**\n\n"
                    f"✅ تعداد فرمت‌ها: {len(pack)}\n"
                    f"📱 شامل: Instagram، Facebook، Twitter، YouTube و...\n\n"
                    f"💡 برای دریافت هر فرمت جداگانه نام آن را بنویسید:\n"
                    f"مثال: `instagram_post`",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # ذخیره پک در user_data
                user_id = update.effective_user.id
                if 'social_pack' not in self.user_data[user_id]:
                    self.user_data[user_id]['social_pack'] = pack
                
                return None  # چون پک جداگانه ارسال نمی‌شود
            
            elif cmd in ['instagram_post', 'facebook_post', 'twitter_post', 'youtube_thumbnail', 
                        'linkedin_post', 'pinterest', 'instagram_story', 'facebook_cover', 'twitter_header']:
                # بررسی وجود پک
                user_id = update.effective_user.id
                if 'social_pack' in self.user_data[user_id] and cmd in self.user_data[user_id]['social_pack']:
                    return self.user_data[user_id]['social_pack'][cmd]
                else:
                    # ایجاد فرمت خاص
                    sizes = {
                        'instagram_post': (1080, 1080),
                        'instagram_story': (1080, 1920),
                        'facebook_post': (1200, 630),
                        'facebook_cover': (820, 312),
                        'twitter_post': (1024, 512),
                        'twitter_header': (1500, 500),
                        'youtube_thumbnail': (1280, 720),
                        'linkedin_post': (1200, 627),
                        'pinterest': (1000, 1500)
                    }
                    
                    if cmd in sizes:
                        width, height = sizes[cmd]
                        return ImageProcessor.center_crop(image, width, height)
            
            else:
                # اگر دستور شناخته نشد، به متد اصلی برو
                return await original_process_command(self, command, image, update)
                
        except ValueError:
            await update.message.reply_text("❌ مقادیر عددی نامعتبر!")
            return None
        except Exception as e:
            await update.message.reply_text(f"❌ خطا: {str(e)}")
            return None
    
    # جایگزین کردن متد
    TelegramBot.process_command = extended_process_command

# اعمال توسعه‌ها
extend_telegram_bot()

# تابع اصلی
def main():
    """تابع اصلی برای اجرای ربات"""
    
    # بررسی توکن
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ لطفاً توکن ربات را در متغیر BOT_TOKEN تنظیم کنید.")
        print("برای دریافت توکن به @BotFather در تلگرام مراجعه کنید.")
        return
    
    # ایجاد و اجرای ربات
    bot = TelegramBot(BOT_TOKEN)
    
    print("🤖 ربات برش تصاویر در حال اجرا...")
    print("برای توقف از Ctrl+C استفاده کنید.")
    
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n🛑 ربات متوقف شد.")
    except Exception as e:
        print(f"❌ خطا در اجرای ربات: {e}")
    finally:
        # پاک‌سازی فایل‌های موقت
        bot.cleanup_temp_files()
        print("🧹 فایل‌های موقت پاک شدند.")

if __name__ == "__main__":
    main()_path, "JPEG", quality=quality, optimize=True)
                
                # ارسال نتیجه
                with open(output_path, 'rb') as f:
                    await update.message.reply_photo(
                        photo=f,
                        caption=f"✅ **برش انجام شد!**\n📏 اندازه جدید: {result_img.size[0]}x{result_img.size[1]} پیکسل",
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                # حذف فایل موقت
                output_path.unlink(missing_ok=True)
            
        except Exception as e:
            logger.error(f"خطا در پردازش دستور: {e}")
            await update.message.reply_text(f"❌ خطا در اجرای دستور: {str(e)}")
    
    async def process_command(self, command: str, image: Image.Image, update: Update) -> Optional[Image.Image]:
        """پردازش دستورات مختلف برش"""
        parts = command.split()
        cmd = parts[0]
        
        img_width, img_height = image.size
        
        try:
            # دستور crop با مختصات
            if cmd == "crop" and len(parts) >= 5:
                x, y, width, height = map(int, parts[1:5])
                return ImageProcessor.crop_image(image, x, y, width, height)
            
            # برش مربعی
            elif cmd == "square":
                size = int(parts[1]) if len(parts) > 1 else min(img_width, img_height)
                return ImageProcessor.center_crop(image, size, size)
            
            # برش مستطیلی
            elif cmd == "rectangle" and len(parts) >= 3:
                width, height = map(int, parts[1:3])
                return ImageProcessor.center_crop(image, width, height)
            
            # تغییر اندازه
            elif cmd == "resize" and len(parts) >= 3:
                width, height = map(int, parts[1:3])
                return ImageProcessor.resize_image(image, width, height)
            
            # برش هوشمند
            elif cmd == "smart" and len(parts) >= 3:
                width, height = map(int, parts[1:3])
                return ImageProcessor.smart_crop(image, width, height)
            
            # برش از مرکز
            elif cmd == "center" and len(parts) >= 3:
                width, height = map(int, parts[1:3])
                return ImageProcessor.center_crop(image, width, height)
            
            # نسبت ابعاد
            elif ":" in command:
                ratio_parts = command.split(":")
                if len(ratio_parts) == 2:
                    w_ratio, h_ratio = map(int, ratio_parts)
                    return ImageProcessor.crop_to_aspect_ratio(image, w_ratio, h_ratio)
            
            # پیش‌تنظیمات شبکه‌های اجتماعی
            elif cmd == "instagram":
                return ImageProcessor.center_crop(image, 1080, 1080)
            elif cmd == "instagram_story":
                return ImageProcessor.center_crop(image, 1080, 1920)
            elif cmd == "facebook":
                return ImageProcessor.center_crop(image, 1200, 630)
            elif cmd == "twitter":
                return ImageProcessor.center_crop(image, 1024, 512)
            elif cmd == "youtube":
                return ImageProcessor.center_crop(image, 1280, 720)
            elif cmd == "linkedin":
                return ImageProcessor.center_crop(image, 1200, 627)
            
            # اندازه‌های استاندارد
            elif cmd == "hd":
                return ImageProcessor.resize_image(image, 1920, 1080)
            elif cmd == "fullhd":
                return ImageProcessor.resize_image(image, 1920, 1080)
            elif cmd == "4k":
                return ImageProcessor.resize_image(image, 3840, 2160)
            
            else:
                await update.message.reply_text(
                    "❌ دستور نامعتبر!\n\n"
                    "✅ **دستورات معتبر:**\n"
                    "• `crop x y width height`\n"
                    "• `square [size]`\n"
                    "• `rectangle width height`\n"
                    "• `resize width height`\n"
                    "• `smart width height`\n"
                    "• `center width height`\n"
                    "• `16:9`, `4:3`, `1:1`\n"
                    "• `instagram`, `youtube`, `facebook`\n\n"
                    "برای راهنما: /help",
                    parse_mode=ParseMode.MARKDOWN
                )
                return None
                
        except ValueError:
            await update.message.reply_text("❌ مقادیر عددی نامعتبر! لطفاً اعداد صحیح وارد کنید.")
            return None
        except Exception as e:
            await update.message.reply_text(f"❌ خطا در پردازش: {str(e)}")
            return None
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش callback queries از دکمه‌های inline"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        # بررسی وجود تصویر
        if user_id not in self.user_data:
            await query.message.reply_text("❌ ابتدا تصویری ارسال کنید.")
            return
        
        try:
            # بارگذاری تصویر
            img_path = self.user_data[user_id]['image_path']
            img = ImageProcessor.load_image(img_path)
            
            if not img:
                await query.message.reply_text("❌ خطا در بارگذاری تصویر.")
                return
            
            # انجام برش بر اساس preset
            result_img = None
            preset = query.data.replace("preset_", "")
            
            preset_configs = {
                "instagram": (1080, 1080),
                "instagram_story": (1080, 1920),
                "facebook": (1200, 630),
                "twitter": (1024, 512),
                "youtube": (1280, 720),
                "linkedin": (1200, 627),
                "16_9": None,  # نسبت ابعاد
                "4_3": None,   # نسبت ابعاد
                "square_500": (500, 500),
                "square_1000": (1000, 1000)
            }
            
            if preset in preset_configs:
                config = preset_configs[preset]
                
                if preset == "16_9":
                    result_img = ImageProcessor.crop_to_aspect_ratio(img, 16, 9)
                elif preset == "4_3":
                    result_img = ImageProcessor.crop_to_aspect_ratio(img, 4, 3)
                elif config:
                    width, height = config
                    result_img = ImageProcessor.center_crop(img, width, height)
            
            if result_img:
                # ذخیره و ارسال نتیجه
                output_path = TEMP_DIR / f"preset_{user_id}_{preset}.jpg"
                
                quality = 95
                if result_img.size[0] * result_img.size[1] > 2000000:
                    quality = 85
                
                result_img.save(output