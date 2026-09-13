import os
import uuid
import asyncio
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

TOKEN = os.environ["BOT_TOKEN"]


# =========================
# HEALTH SERVER
# =========================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        return


def run_health_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


threading.Thread(target=run_health_server, daemon=True).start()


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Faizan Download Hub!\n\n"
        "🔗 Mujhe video link bhejo.\n\n"
        "🎬 360p\n"
        "🎬 480p\n"
        "🎬 720p\n"
        "🎬 1080p\n"
        "🎵 Audio\n\n"
        "👇 Link bhejo aur quality select karo."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔗 Public video link bhejo.\n\n"
        "Available qualities:\n"
        "🎬 360p\n"
        "🎬 480p\n"
        "🎬 720p\n"
        "🎬 1080p\n"
        "🎵 Audio"
    )


# =========================
# GET VIDEO INFO
# =========================

def get_info(url):
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        return ydl.extract_info(url, download=False)


# =========================
# LINK HANDLER
# =========================

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):

    url = update.message.text.strip()

    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ Valid video link bhejo.")
        return

    msg = await update.message.reply_text(
        "🔎 Video information check ho rahi hai...\n⏳ Please wait..."
    )

    try:
        info = await asyncio.to_thread(get_info, url)

        title = info.get("title") or "Video"
        thumbnail = info.get("thumbnail")

        # URL ko user ke session mein save
        context.user_data["video_url"] = url

        keyboard = [
            [
                InlineKeyboardButton("🎬 360p", callback_data="360"),
                InlineKeyboardButton("🎬 480p", callback_data="480"),
            ],
            [
                InlineKeyboardButton("🎬 720p", callback_data="720"),
                InlineKeyboardButton("🎬 1080p", callback_data="1080"),
            ],
            [
                InlineKeyboardButton("🎵 Audio", callback_data="audio")
            ],
        ]

        buttons = InlineKeyboardMarkup(keyboard)

        caption = (
            f"🎬 {title}\n\n"
            "👇 Download quality select karo:"
        )

        await msg.delete()

        if thumbnail:
            try:
                await update.message.reply_photo(
                    photo=thumbnail,
                    caption=caption,
                    reply_markup=buttons
                )
            except Exception:
                await update.message.reply_text(
                    caption,
                    reply_markup=buttons
                )
        else:
            await update.message.reply_text(
                caption,
                reply_markup=buttons
            )

    except Exception as e:
        print("INFO ERROR:", e)

        await msg.edit_text(
            "❌ Video information nahi mil saki.\n\n"
            "Link check karo ya doosra public link try karo."
        )


# =========================
# DOWNLOAD FUNCTION
# =========================

def download_video(url, quality, filename):

    if quality == "audio":

        options = {
            "format": "bestaudio/best",
            "outtmpl": filename.replace(".mp4", ".%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

    else:

        height = int(quality)

        options = {
            "format": (
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}]"
            ),
            "outtmpl": filename,
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
        }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    if quality == "audio":
        base = filename.rsplit(".", 1)[0]

        mp3_file = base + ".mp3"

        if os.path.exists(mp3_file):
            return mp3_file

        # Fallback: find generated audio file
        for file in os.listdir("."):
            if file.startswith(os.path.basename(base)):
                if file.endswith(".mp3"):
                    return file

    return filename


# =========================
# QUALITY BUTTON
# =========================

async def quality_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    url = context.user_data.get("video_url")

    if not url:
        await query.edit_message_caption(
            caption="❌ Link session expire ho gayi.\nDobara link bhejo."
        )
        return

    quality = query.data

    if quality not in ["360", "480", "720", "1080", "audio"]:
        return

    quality_name = "Audio" if quality == "audio" else f"{quality}p"

    await query.edit_message_caption(
        caption=(
            f"⏳ {quality_name} download ho rahi hai...\n\n"
            "Please wait."
        )
    )

    unique_id = uuid.uuid4().hex[:10]

    if quality == "audio":
        filename = f"faizan_{unique_id}.mp4"
    else:
        filename = f"faizan_{unique_id}.mp4"

    try:

        downloaded_file = await asyncio.to_thread(
            download_video,
            url,
            quality,
            filename
        )

        if not os.path.exists(downloaded_file):
            raise Exception("Downloaded file not found")

        await query.edit_message_caption(
            caption=f"📤 {quality_name} Telegram par bheji ja rahi hai..."
        )

        chat_id = query.message.chat_id

        if quality == "audio":

            with open(downloaded_file, "rb") as audio:
                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=audio,
                    title="Faizan Download Hub"
                )

        else:

            with open(downloaded_file, "rb") as video:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=video,
                    supports_streaming=True,
                    caption=f"🎬 {quality_name}\n\n"
                            "Downloaded by Faizan Download Hub"
                )

        await query.message.delete()

    except Exception as e:

        print("DOWNLOAD ERROR:", e)

        try:
            await query.edit_message_caption(
                caption=(
                    "❌ Video download nahi ho saki.\n\n"
                    "Link public hai ya nahi check karo, "
                    "phir dobara try karo."
                )
            )
        except Exception:
            pass

    finally:

        # Clean files
        possible_files = [
            filename,
            filename.replace(".mp4", ".mp3"),
            filename.replace(".mp4", ".webm"),
            filename.replace(".mp4", ".m4a"),
        ]

        for file in possible_files:
            if os.path.exists(file):
                try:
                    os.remove(file)
                except:
                    pass


# =========================
# BOT
# =========================

app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))

app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_link
    )
)

app.add_handler(
    CallbackQueryHandler(quality_callback)
)

print("🤖 Faizan Download Hub is running!")

app.run_polling()
