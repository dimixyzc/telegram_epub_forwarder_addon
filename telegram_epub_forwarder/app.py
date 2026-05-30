import os
import asyncio
import smtplib
import logging
import io
import zipfile
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
PHONE = os.environ["TG_PHONE"]
SESSION_STRING = os.environ.get("TG_SESSION_STRING", "")
CHANNELS = [c.strip() for c in os.environ["CHANNELS"].split(",")]
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_PASS = os.environ["GMAIL_PASS"]
RECIPIENT = os.environ["RECIPIENT"]
NOTIFICATION_EMAIL = os.environ.get("NOTIFICATION_EMAIL") or GMAIL_USER
MAX_EPUB_MB = float(os.environ.get("MAX_EPUB_MB", "18"))
KEEP_OVERSIZED_FILES = os.environ.get("KEEP_OVERSIZED_FILES", "true").lower() == "true"

SESSION_PATH = "/data/telegram_session"
AUTH_CODE_FILE = "/data/auth_code.txt"
OVERSIZED_DIR = "/data/oversized_epubs"
BYTES_PER_MB = 1024 * 1024
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
JPEG_QUALITIES = (75, 65, 55)
MAX_IMAGE_EDGE_PX = 1600


def wait_for_code():
    import time
    log.info("=" * 60)
    log.info("EINMALIGE ANMELDUNG ERFORDERLICH")
    log.info("Telegram schickt dir jetzt einen Code.")
    log.info("Gib ihn im SSH Terminal ein mit:")
    log.info(f"  echo '12345' > {AUTH_CODE_FILE}")
    log.info("=" * 60)
    while True:
        if os.path.exists(AUTH_CODE_FILE):
            with open(AUTH_CODE_FILE) as f:
                code = f.read().strip()
            os.remove(AUTH_CODE_FILE)
            log.info("Code gelesen. Anmeldung läuft...")
            return code
        time.sleep(2)


def normalize_session_string(session_string: str) -> str:
    session_string = "".join(session_string.split())
    if (
        len(session_string) >= 2
        and session_string[0] == session_string[-1]
        and session_string[0] in {"'", '"'}
    ):
        session_string = session_string[1:-1]
    return session_string


def build_telegram_client() -> TelegramClient:
    session_string = normalize_session_string(SESSION_STRING)
    if not session_string:
        log.info(f"Keine Telegram StringSession konfiguriert. Nutze Datei-Session: {SESSION_PATH}")
        return TelegramClient(SESSION_PATH, API_ID, API_HASH)

    try:
        session = StringSession(session_string)
    except Exception as exc:
        log.critical(
            "Telegram Session String ist ungueltig oder nicht im Telethon-Format. "
            "Bitte einen Telethon StringSession-Wert eintragen oder das Feld leer lassen, "
            f"um den Datei-Login zu nutzen. Laenge nach Bereinigung: {len(session_string)}. "
            f"Fehler: {exc}"
        )
        raise SystemExit(2) from exc

    log.info("Telegram StringSession konfiguriert.")
    return TelegramClient(session, API_ID, API_HASH)


def size_mb(file_bytes: bytes) -> float:
    return len(file_bytes) / BYTES_PER_MB


def format_mb(file_bytes: bytes) -> str:
    return f"{size_mb(file_bytes):.1f} MB"


def send_email(
    subject: str,
    body: str,
    recipient: str,
    attachment_filename: str | None = None,
    attachment_bytes: bytes | None = None,
):
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if attachment_filename and attachment_bytes is not None:
        part = MIMEBase("application", "epub+zip")
        part.set_payload(attachment_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{attachment_filename}"')
        msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASS)
        server.sendmail(GMAIL_USER, recipient, msg.as_string())
    log.info(f"E-Mail gesendet: {subject} -> {recipient}")


def send_kindle_email(filename: str, file_bytes: bytes):
    send_email(
        subject=filename,  # Kindle uses subject as book title
        body="",
        recipient=RECIPIENT,
        attachment_filename=filename,
        attachment_bytes=file_bytes,
    )


def send_oversized_notification(filename: str, original_bytes: bytes, final_bytes: bytes, saved_path: str | None):
    saved_note = f"\nLokale Datei: {saved_path}" if saved_path else ""
    body = (
        f"Die EPUB-Datei konnte nicht sicher per Kindle-E-Mail versendet werden.\n\n"
        f"Datei: {filename}\n"
        f"Originalgröße: {format_mb(original_bytes)}\n"
        f"Optimierte Größe: {format_mb(final_bytes)}\n"
        f"Limit für E-Mail-Versand: {MAX_EPUB_MB:.1f} MB\n"
        f"{saved_note}\n\n"
        f"Manueller Upload:\n"
        f"https://www.amazon.com/sendtokindle\n"
    )
    send_email(
        subject=f"Kindle EPUB zu gross: {filename}",
        body=body,
        recipient=NOTIFICATION_EMAIL,
    )


def save_oversized_file(filename: str, file_bytes: bytes) -> str | None:
    if not KEEP_OVERSIZED_FILES:
        return None
    os.makedirs(OVERSIZED_DIR, exist_ok=True)
    safe_name = os.path.basename(filename)
    path = os.path.join(OVERSIZED_DIR, safe_name)
    with open(path, "wb") as f:
        f.write(file_bytes)
    return path


def image_output_candidates(image: Image.Image, original_ext: str):
    image.thumbnail((MAX_IMAGE_EDGE_PX, MAX_IMAGE_EDGE_PX), Image.Resampling.LANCZOS)
    has_alpha = image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    )

    if original_ext == ".png" or has_alpha:
        png_image = image.convert("RGBA")
        out = io.BytesIO()
        png_image.save(out, format="PNG", optimize=True)
        yield out.getvalue()
        return

    rgb_image = image.convert("RGB")
    for quality in JPEG_QUALITIES:
        out = io.BytesIO()
        rgb_image.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
        yield out.getvalue()


def optimize_image(path: str, file_bytes: bytes) -> bytes:
    _, ext = os.path.splitext(path.lower())
    try:
        with Image.open(io.BytesIO(file_bytes)) as image:
            candidates = list(image_output_candidates(image, ext))
    except Exception as exc:
        log.warning(f"Bild konnte nicht optimiert werden ({path}): {exc}")
        return file_bytes

    best_bytes = min(candidates, key=len)
    if len(best_bytes) >= len(file_bytes):
        return file_bytes

    return best_bytes


def optimize_epub(file_bytes: bytes) -> bytes:
    output = io.BytesIO()

    with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as source:
        names = source.namelist()
        with zipfile.ZipFile(output, "w") as target:
            if "mimetype" in names:
                target.writestr(
                    zipfile.ZipInfo("mimetype"),
                    source.read("mimetype"),
                    compress_type=zipfile.ZIP_STORED,
                )

            for item in source.infolist():
                if item.filename == "mimetype":
                    continue

                data = source.read(item.filename)
                _, ext = os.path.splitext(item.filename.lower())
                target_name = item.filename

                if ext in IMAGE_EXTENSIONS:
                    data = optimize_image(item.filename, data)
                    if len(data) != item.file_size:
                        log.info(
                            f"Asset optimiert: {item.filename} "
                            f"{item.file_size / 1024:.0f} KB -> {len(data) / 1024:.0f} KB"
                        )

                info = zipfile.ZipInfo(target_name, date_time=item.date_time)
                info.compress_type = zipfile.ZIP_DEFLATED
                target.writestr(info, data)

    return output.getvalue()


def process_epub_for_kindle(filename: str, file_bytes: bytes):
    limit_bytes = int(MAX_EPUB_MB * BYTES_PER_MB)
    if len(file_bytes) <= limit_bytes:
        log.info(f"{filename} ist {format_mb(file_bytes)} und wird direkt gesendet.")
        send_kindle_email(filename, file_bytes)
        return

    log.info(f"{filename} ist {format_mb(file_bytes)}; Optimierung startet.")
    optimized_bytes = optimize_epub(file_bytes)
    log.info(f"Optimierung abgeschlossen: {format_mb(file_bytes)} -> {format_mb(optimized_bytes)}")

    if len(optimized_bytes) <= limit_bytes:
        optimized_name = filename.replace(".epub", "_optimized.epub")
        send_kindle_email(optimized_name, optimized_bytes)
        return

    saved_path = save_oversized_file(filename.replace(".epub", "_optimized.epub"), optimized_bytes)
    log.warning(
        f"{filename} bleibt nach Optimierung zu gross: {format_mb(optimized_bytes)} "
        f"> {MAX_EPUB_MB:.1f} MB"
    )
    send_oversized_notification(filename, file_bytes, optimized_bytes, saved_path)


async def main():
    client = build_telegram_client()
    if normalize_session_string(SESSION_STRING):
        await client.start()
        log.info("Telegram StringSession geladen.")
    else:
        await client.start(phone=PHONE, code_callback=wait_for_code)
        log.info(f"Telegram Datei-Session geladen: {SESSION_PATH}")

    log.info(f"Verbunden als {PHONE}. Überwache Channels: {CHANNELS}")

    @client.on(events.NewMessage(chats=CHANNELS))
    async def handler(event):
        msg = event.message
        if not msg.document:
            return
        filename = None
        for attr in msg.document.attributes:
            if hasattr(attr, "file_name"):
                filename = attr.file_name
                break
        if filename and filename.lower().endswith(".epub"):
            log.info(f".epub erkannt: {filename} – Download startet...")
            file_bytes = await client.download_media(msg.document, bytes)
            process_epub_for_kindle(filename, file_bytes)

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
