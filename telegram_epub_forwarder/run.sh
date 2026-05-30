#!/bin/sh
CONFIG_PATH=/data/options.json

export TG_API_ID=$(jq -r '.telegram_api_id' $CONFIG_PATH)
export TG_API_HASH=$(jq -r '.telegram_api_hash' $CONFIG_PATH)
export TG_PHONE=$(jq -r '.telegram_phone' $CONFIG_PATH)
export CHANNELS=$(jq -r '.channels | join(",")' $CONFIG_PATH)
export GMAIL_USER=$(jq -r '.gmail_user' $CONFIG_PATH)
export GMAIL_PASS=$(jq -r '.gmail_app_password' $CONFIG_PATH)
export RECIPIENT=$(jq -r '.recipient_email' $CONFIG_PATH)
export MAX_EPUB_MB=$(jq -r '.max_epub_mb // 18' $CONFIG_PATH)
export NOTIFICATION_EMAIL=$(jq -r '.notification_email // .gmail_user' $CONFIG_PATH)
export KEEP_OVERSIZED_FILES=$(jq -r '.keep_oversized_files // true' $CONFIG_PATH)

python /app/app.py
