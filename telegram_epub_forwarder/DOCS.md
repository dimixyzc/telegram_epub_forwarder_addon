# Telegram EPUB Forwarder

## Configuration

- `telegram_api_id`: Telegram API ID.
- `telegram_api_hash`: Telegram API hash.
- `telegram_phone`: Telegram phone number. Only needed for fallback login if no session string is configured.
- `telegram_session_string`: Existing Telethon StringSession value. Preferred for Home Assistant use. A Pyrogram session string is not compatible.
- `channels`: Telegram channel usernames or IDs to watch.
- `gmail_user`: Gmail sender address.
- `gmail_app_password`: Gmail app password.
- `recipient_email`: Kindle e-mail address.
- `max_epub_mb`: Safe raw EPUB size limit for SMTP delivery. Default: `18`.
- `notification_email`: Normal e-mail address for oversized-file notifications. Defaults to the Gmail sender if left empty.
- `keep_oversized_files`: Store optimized oversized EPUBs under `/data/oversized_epubs/`.

## Behavior

EPUB files at or below `max_epub_mb` are sent directly. Larger files are optimized by recompressing embedded images. If the optimized EPUB is still too large, the add-on stores it locally and sends a notification with a Send to Kindle web-upload link.
