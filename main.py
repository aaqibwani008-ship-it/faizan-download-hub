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
    raise RuntimeError("BOT_TOKEN environment variable is missing")


# =========================
# HEALTH SERVER
# =========================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(
            b"Faizan Download Hub is running!"
        )

    def log_message(self, format, *args):
        return


def start_health_server():
    port = int(os.getenv("PORT", "10000"))

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )

    server.serve_forever()


# =========================
# URL DETECTION
# =========================

URL_REGEX = r"https?://[^\s]+"


def get_url(text):

    match = re.search(
        URL_REGEX,
        text or ""
    )

    if not match:
        return None

    return match.group(0).rstrip(
        ".,!?)]}"
    )


# =========================
# DOWNLOAD
# =========================

def download_video(url, quality):

    height = int(quality)

    temp_dir = tempfile.mkdtemp(
        prefix="faizan_"
    )

    output = os.path.join(
        temp_dir,
        "%(title).80s.%(ext)s"
    )

    ydl_opts = {

        # Select requested quality
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

        "retries": 10,

        "fragment_retries": 10,

        "socket_timeout": 30,

        # IMPORTANT:
        # Deno is installed in Dockerfile
        "js_runtimes": {
            "deno": "/root/.deno/bin/deno"
        },

        # Browser User-Agent
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0.0.0 "
                "Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },

        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }
        ],
    }

    print(
        f"START DOWNLOAD: {url} | {quality}p"
    )

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:

        info = ydl.extract_info(
            url,
            download=True
        )

        requested = ydl.prepare_filename(
            info
        )

        base = os.path.splitext(
            requested
        )[0]

        possible_files = [
            requested,
            base + ".mp4",
            base + ".mkv",
            base + ".webm",
        ]

        for file_path in possible_files:

            if os.path.exists(file_path):

                print(
                    "DOWNLOAD SUCCESS:",
                    file_path
                )

                return file_path

    return None


# =========================
# START
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    keyboard = [

        [
            InlineKeyboardButton(
                "360p",
                callback_data="360"
            ),
            InlineKeyboardButton(
                "480p",
                callback_data="480"
            ),
        ],

        [
            InlineKeyboardButton(
                "720p",
                callback_data="720"
            ),
            InlineKeyboardButton(
                "1080p",
                callback_data="1080"
            ),
        ],

    ]

    await update.message.reply_text(

        "👋 Faizan Download Hub\n\n"

        "Instagram, Snapchat aur "
        "YouTube ka public video link bhejo.\n\n"

        "Quality select karo 👇",

        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# =========================
# URL MESSAGE
# =========================

async def handle_url(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    url = get_url(
        update.message.text
    )

    if not url:

        await update.message.reply_text(
            "❌ Valid video URL nahi mila."
        )

        return

    context.user_data["url"] = url

    keyboard = [

        [
            InlineKeyboardButton(
                "360p",
                callback_data="360"
            ),
            InlineKeyboardButton(
                "480p",
                callback_data="480"
            ),
        ],

        [
            InlineKeyboardButton(
                "720p",
                callback_data="720"
            ),
            InlineKeyboardButton(
                "1080p",
                callback_data="1080"
            ),
        ],

    ]

    await update.message.reply_text(

        "🎥 Video link mil gaya!\n\n"
        "Quality select karo:",

        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# =========================
# QUALITY CALLBACK
# =========================

async def quality_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    url = context.user_data.get(
        "url"
    )

    if not url:

        await query.message.reply_text(
            "❌ Pehle video link bhejo."
        )

        return

    quality = query.data

    await query.message.reply_text(

        f"⏳ Downloading...\n\n"
        f"Quality: {quality}p\n\n"
        f"Thoda wait karo."
    )

    try:

        file_path = await asyncio.to_thread(
            download_video,
            url,
            quality
        )

        if not file_path:

            await query.message.reply_text(
                "❌ Video download nahi hua."
            )

            return

        if not os.path.exists(
            file_path
        ):

            await query.message.reply_text(
                "❌ Downloaded file nahi mili."
            )

            return

        file_size = os.path.getsize(
            file_path
        )

        # Telegram upload safety
        if file_size > 49 * 1024 * 1024:

            await query.message.reply_text(

                "❌ Video 49 MB se bada hai.\n\n"
                "360p ya 480p try karo."
            )

            try:
                os.remove(file_path)
            except:
                pass

            return

        with open(
            file_path,
            "rb"
        ) as video_file:

            await query.message.reply_video(

                video=video_file,

                supports_streaming=True,

                caption=(
                    f"✅ Downloaded\n"
                    f"Quality: {quality}p"
                )
            )

        try:
            os.remove(file_path)
        except:
            pass

    except Exception as e:

        print(
            "DOWNLOAD ERROR:",
            repr(e)
        )

        await query.message.reply_text(

            "❌ Download failed.\n\n"
            "Please try another video."
        )


# =========================
# ERROR HANDLER
# =========================

async def error_handler(
    update,
    context
):

    print(
        "BOT ERROR:",
        repr(context.error)
    )


# =========================
# MAIN
# =========================

def main():

    threading.Thread(
        target=start_health_server,
        daemon=True
    ).start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_url
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            quality_callback
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
