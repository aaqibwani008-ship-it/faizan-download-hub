import os
import re
import asyncio
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# -------------------------
# Render health server
# -------------------------

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running")

    def log_message(self, format, *args):
        return


def run_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


# -------------------------
# URL detection
# -------------------------

URL_PATTERN = re.compile(
    r"https?://[^\s]+",
    re.IGNORECASE
)


def clean_url(url):
    return url.strip().rstrip(".,!?)]}")


# -------------------------
# Download
# -------------------------

def download_video(url, quality):
    temp_dir = tempfile.mkdtemp(prefix="telegram_dl_")

    output = os.path.join(temp_dir, "%(title).100s.%(ext)s")

    height = {
        "360": 360,
        "480": 480,
        "720": 720,
        "1080": 1080,
    }.get(quality, 720)

    ydl_opts = {
        "outtmpl": output,
        "format": (
            f"bestvideo[height<={height}]+bestaudio/"
            f"best[height<={height}]/best"
        ),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "restrictfilenames": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

        # yt-dlp may merge into mp4
        base, _ = os.path.splitext(filename)
        possible_mp4 = base + ".mp4"

        if os.path.exists(possible_mp4):
            filename = possible_mp4

    return filename, info, temp_dir


# -------------------------
# Start
# -------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("360p", callback_data="360"),
            InlineKeyboardButton("480p", callback_data="480"),
        ],
        [
            InlineKeyboardButton("720p", callback_data="720"),
            InlineKeyboardButton("1080p", callback_data="1080"),
        ],
    ]

    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Instagram, YouTube ya Snapchat ka public video link bhejo.\n\n"
        "Phir quality select karo:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# -------------------------
# URL message
# -------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    urls = URL_PATTERN.findall(text)

    if not urls:
        await update.message.reply_text(
            "❌ Valid video URL nahi mila.\n\n"
            "Instagram / YouTube / Snapchat ka public link bhejo."
        )
        return

    url = clean_url(urls[0])

    context.user_data["url"] = url

    keyboard = [
        [
            InlineKeyboardButton("360p", callback_data="360"),
            InlineKeyboardButton("480p", callback_data="480"),
        ],
        [
            InlineKeyboardButton("720p", callback_data="720"),
            InlineKeyboardButton("1080p", callback_data="1080"),
        ],
    ]

    await update.message.reply_text(
        "🎬 Link mil gaya!\n\n"
        "Quality select karo:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# -------------------------
# Quality button
# -------------------------

async def quality_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    quality = query.data
    url = context.user_data.get("url")

    if not url:
        await query.edit_message_text(
            "❌ Link nahi mila. Pehle video link bhejo."
        )
        return

    await query.edit_message_text(
        f"⏳ Downloading...\n\n"
        f"Quality: {quality}p\n"
        f"Please wait..."
    )

    try:
        filename, info, temp_dir = await asyncio.to_thread(
            download_video,
            url,
            quality
        )

        if not os.path.exists(filename):
            raise Exception("Downloaded file not found")

        file_size = os.path.getsize(filename)

        # Telegram Bot API normally has file-size limitations.
        # Avoid trying to send extremely large files.
        if file_size > 49 * 1024 * 1024:
            await query.message.reply_text(
                "❌ File bahut badi hai.\n"
                "Lower quality try karo."
            )
            return

        title = info.get("title", "Video")

        await query.message.reply_video(
            video=open(filename, "rb"),
            caption=(
                f"✅ Download complete!\n\n"
                f"🎬 {title}\n"
                f"📺 Quality: {quality}p"
            ),
            supports_streaming=True,
        )

        try:
            os.remove(filename)
            os.rmdir(temp_dir)
        except Exception:
            pass

    except Exception as e:
        error = str(e)

        if "login" in error.lower():
            message = (
                "❌ Is video ke liye login required hai.\n"
                "Public video link try karo."
            )
        elif "private" in error.lower():
            message = "❌ Private video download nahi ho sakta."
        elif "unsupported" in error.lower():
            message = "❌ Yeh URL supported nahi hai."
        else:
            message = (
                "❌ Download failed.\n\n"
                "Video public hai aur URL sahi hai to "
                "dobara try karo."
            )

        await query.message.reply_text(message)


# -------------------------
# Error handler
# -------------------------

async def error_handler(update, context):
    print("ERROR:", context.error)


# -------------------------
# Main
# -------------------------

def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable missing"
        )

    threading.Thread(
        target=run_health_server,
        daemon=True
    ).start()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    app.add_handler(
        CallbackQueryHandler(quality_callback)
    )

    app.add_error_handler(error_handler)

    print("🤖 Bot started...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
