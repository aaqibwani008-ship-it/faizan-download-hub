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
# Render health check
# -------------------------

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Faizan Download Hub is running!")

    def log_message(self, format, *args):
        pass


def run_server():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


# -------------------------
# URL
# -------------------------

def get_url(text):
    match = re.search(r"https?://[^\s]+", text)

    if not match:
        return None

    return match.group(0).rstrip(".,!?)]}")


# -------------------------
# Download
# -------------------------

def download_video(url, quality):
    folder = tempfile.mkdtemp(prefix="faizan_")

    output = os.path.join(
        folder,
        "%(title).80s.%(ext)s"
    )

    height = {
        "360": 360,
        "480": 480,
        "720": 720,
        "1080": 1080,
    }.get(quality, 720)

    ydl_opts = {
        "outtmpl": output,

        # Flexible format:
        # requested quality -> lower quality -> best available
        "format": (
            f"bestvideo[height<={height}]+bestaudio/"
            f"best[height<={height}]/"
            f"best"
        ),

        "merge_output_format": "mp4",

        "noplaylist": True,

        "quiet": False,
        "no_warnings": False,

        "retries": 5,
        "fragment_retries": 5,
        "extractor_retries": 3,

        "socket_timeout": 60,

        "http_headers": {
            "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36"
        },
    }

    print("DOWNLOAD URL:", url)
    print("QUALITY:", quality)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        filename = ydl.prepare_filename(info)

        base, ext = os.path.splitext(filename)
        mp4 = base + ".mp4"

        if os.path.exists(mp4):
            filename = mp4

    print("FILE:", filename)

    return filename, info, folder


# -------------------------
# Start command
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
        "👋 Welcome to Faizan Download Hub!\n\n"
        "📥 Instagram\n"
        "📥 YouTube\n"
        "📥 Snapchat\n\n"
        "Public video link bhejo:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# -------------------------
# Link receive
# -------------------------

async def receive_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    url = get_url(update.message.text or "")

    if not url:
        await update.message.reply_text(
            "❌ Valid video link nahi mila.\n\n"
            "YouTube, Instagram ya Snapchat ka "
            "public link bhejo."
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
        "🔗 Link mil gaya!\n\n"
        "Quality select karo:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# -------------------------
# Quality selected
# -------------------------

async def quality_selected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    quality = query.data
    url = context.user_data.get("url")

    if not url:
        await query.message.reply_text(
            "❌ Link missing hai. Dobara link bhejo."
        )
        return

    await query.edit_message_text(
        f"⏳ Downloading...\n\n"
        f"🎬 Quality: {quality}p\n"
        f"Please wait..."
    )

    try:

        filename, info, folder = await asyncio.to_thread(
            download_video,
            url,
            quality
        )

        if not os.path.exists(filename):
            raise Exception("File not found")

        size = os.path.getsize(filename)

        # Telegram Bot API limit ke aas-paas
        if size > 49 * 1024 * 1024:

            await query.message.reply_text(
                "❌ Video Telegram ke liye bahut bada hai.\n\n"
                "720p ya 480p try karo."
            )

            return

        title = info.get(
            "title",
            "Downloaded Video"
        )

        with open(filename, "rb") as video:

            await query.message.reply_video(
                video=video,
                caption=(
                    "✅ Download Complete!\n\n"
                    f"🎬 {title}\n"
                    f"📺 Quality: {quality}p\n\n"
                    "🤖 Faizan Download Hub"
                ),
                supports_streaming=True,
            )

        # Cleanup

        try:
            os.remove(filename)
            os.rmdir(folder)
        except Exception:
            pass

    except Exception as error:

        print("DOWNLOAD ERROR:", error)

        error_text = str(error).lower()

        if "private" in error_text:

            msg = (
                "❌ Private video hai.\n"
                "Public video link try karo."
            )

        elif "login" in error_text:

            msg = (
                "❌ Is video ko login chahiye.\n"
                "Public video try karo."
            )

        elif "unsupported" in error_text:

            msg = (
                "❌ Ye URL supported nahi hai."
            )

        else:

            msg = (
                "❌ Download failed.\n\n"
                "Possible reasons:\n"
                "• Video private hai\n"
                "• Platform ne request block ki\n"
                "• Video available nahi hai\n\n"
                "Dobara try karo."
            )

        await query.message.reply_text(msg)


# -------------------------
# Error handler
# -------------------------

async def error_handler(update, context):

    print(
        "BOT ERROR:",
        context.error
    )


# -------------------------
# Main
# -------------------------

def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN environment variable missing"
        )

    # Render web server
    threading.Thread(
        target=run_server,
        daemon=True
    ).start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_link
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            quality_selected
        )
    )

    application.add_error_handler(
        error_handler
    )

    print(
        "🤖 Faizan Download Hub is running!"
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
