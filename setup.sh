#!/usr/bin/env bash
# ----------------------------------------------------------------------------
# اسکریپت نصب خودکار — فقط همین یک فایل را اجرا کنید
#   bash setup.sh
# این اسکریپت:
#  1) پکیج‌های پایتون را نصب می‌کند
#  2) کتابخانهٔ چارت (Lightweight Charts) را دانلود و در جای درست می‌گذارد
#  3) برنامه را اجرا می‌کند
# ----------------------------------------------------------------------------
set -e
cd "$(dirname "$0")"

echo "== 1) نصب پکیج‌های پایتون =="
pip install -r requirements.txt

echo "== 2) دانلود کتابخانهٔ چارت (Lightweight Charts) =="
mkdir -p static/lib
LIB_FILE="static/lib/lightweight-charts.standalone.production.js"
if [ ! -f "$LIB_FILE" ]; then
  if command -v curl >/dev/null 2>&1; then
    curl -sL "https://cdnjs.cloudflare.com/ajax/libs/lightweight-charts/4.1.3/lightweight-charts.standalone.production.js" -o "$LIB_FILE"
  elif command -v wget >/dev/null 2>&1; then
    wget -q "https://cdnjs.cloudflare.com/ajax/libs/lightweight-charts/4.1.3/lightweight-charts.standalone.production.js" -O "$LIB_FILE"
  else
    echo "خطا: curl یا wget پیدا نشد. فایل را دستی از لینک زیر بگیرید و در $LIB_FILE بگذارید:"
    echo "https://cdnjs.cloudflare.com/ajax/libs/lightweight-charts/4.1.3/lightweight-charts.standalone.production.js"
    exit 1
  fi
  if [ ! -s "$LIB_FILE" ]; then
    echo "دانلود ناموفق بود (اینترنت/فایروال؟). به‌صورت دستی از لینک بالا دانلود و در $LIB_FILE بگذارید."
    exit 1
  fi
  echo "کتابخانه با موفقیت دانلود شد."
else
  echo "کتابخانه از قبل موجود است، رد شد."
fi

echo "== 3) اجرای برنامه =="
echo "مرورگر را باز کنید: http://127.0.0.1:5000"
python app.py
