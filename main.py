import os
import re
import asyncio
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import yt_dlp

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")


# =========================
# RENDER HEALTH SERVER
# =========================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Faizan Download Hub is running!")

    def log_message(self, format, *args):
        return


def start_server():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


# =========================
# URL
# =========================

def get_url(text):
    match = re.search(r"https?://[^\s]+", text or "")

    if not match:
        return None

    return match.group(0).rstrip(".,!?)]}")


def supported_url(url):

    domains = [
        "instagram.com",
        "www.instagram.com",
        "snapchat.com",
        "www.snapchat.com",
    ]

    return any(domain in url.lower() for domain in domains)


# =========================
# DOWNLOAD
# =========================

def download_video(url, quality):

    height = int(quality)

    temp_dir = tempfile.mkdtemp(prefix="faizan_")

    output = os.path.join(
        temp_dir,
        "%(title).80s.%(ext)s"
    )

    ydl_opts = {
        "format": (
            f"bestvideo[height<={height}]+bestaudio/"
            f"best[height<={height}]/"
            f"best"
        ),

        "outtmpl": output,

        "merge_output_format": "mp4",

        "noplaylist": True,

        "quiet": False,

        "no_warnings": False,

        "retries": 5,

        "fragment_retries": 5,

        "socket_timeout": 30,

        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        },
    }

    print(f"DOWNLOADING: {url} | {quality}p")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:

        info = ydl.extract_info(
            url,
            download=True
        )

        filename = ydl.prepare_filename(info)

        base = os.path.splitext(filename)[0]

        files = [
            filename,
            base + ".mp4",
            base + ".mkv",
            base + ".webm",
        ]

        for file in files:

            if os.path.exists(file):

                print("DOWNLOAD SUCCESS:", file)

                return file

    return None


# =========================
# START
# =========================

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
        "👋 Faizan Download Hub\n\n"
        "Instagram aur Snapchat ka public video link bhejo.\n\n"
        "Quality select karo 👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# LINK HANDLER
# =========================

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):

    url = get_url(update.message.text)

    if not url:

        await update.message.reply_text(
            "❌ Valid link nahi mila."
        )

        return

    if not supported_url(url):

        await update.message.reply_text(
            "❌ Sirf Instagram aur Snapchat links supported hain."
        )

        return

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
        "🎥 Link mil gaya!\n\n"
        "Quality select karo 👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# QUALITY
# =========================

async def quality_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    url = context.user_data.get("url")

    if not url:

        await query.message.reply_text(
            "❌ Pehle Instagram ya Snapchat link bhejo."
        )

        return

    quality = query.data

    await query.message.reply_text(
        f"⏳ Downloading...\n\n"
        f"Quality: {quality}p"
    )

    try:

        file_path = await asyncio.to_thread(
            download_video,
            url,
            quality
        )

        if not file_path or not os.path.exists(file_path):

            await query.message.reply_text(
                "❌ Download failed."
            )

            return

        size = os.path.getsize(file_path)

        if size > 49 * 1024 * 1024:

            await query.message.reply_text(
                "❌ Video 49 MB se bada hai.\n"
                "Lower quality try karo."
            )

            os.remove(file_path)

            return

        with open(file_path, "rb") as video:

            await query.message.reply_video(
                video=video,
                supports_streaming=True,
                caption=f"✅ Downloaded • {quality}p"
            )

        os.remove(file_path)

    except Exception as e:

        print("DOWNLOAD ERROR:", repr(e))

        await query.message.reply_text(
            "❌ Download failed. "
            "Public video link dobara try karo."
        )


# =========================
# ERROR
# =========================

async def error_handler(update, context):

    print(
        "BOT ERROR:",
        repr(context.error)
    )


# =========================
# MAIN
# =========================

def main():

    threading.Thread(
        target=start_server,
        daemon=True
    ).start()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_url
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            quality_callback
        )
    )

    app.add_error_handler(error_handler)

    print("🤖 Faizan Download Hub is running!")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
