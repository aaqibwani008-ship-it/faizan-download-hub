import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import yt_dlp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.environ["BOT_TOKEN"]


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Faizan Download Hub!\n\n"
        "🔗 Video link bhejo.\n"
        "📥 Bot highest available quality (up to 1080p) mein video bhejega."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔗 Video link bhejo.\n"
        "🎥 Maximum 1080p available quality."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ Valid link bhejo.")
        return

    msg = await update.message.reply_text("⏳ Video download ho rahi hai...")

    filename = "faizan_video.mp4"

    try:
        ydl_opts = {
            "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "outtmpl": filename,
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        await msg.edit_text("📤 Video Telegram par bhej raha hoon...")

        with open(filename, "rb") as video:
            await update.message.reply_video(
                video=video,
                supports_streaming=True
            )

        os.remove(filename)

    except Exception as e:
        if os.path.exists(filename):
            os.remove(filename)

        await msg.edit_text(
            "❌ Video download nahi ho saki.\n"
            "Link check karo ya doosra link try karo."
        )


app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link)
)

print("🤖 Faizan Download Hub is running!")
app.run_polling()
