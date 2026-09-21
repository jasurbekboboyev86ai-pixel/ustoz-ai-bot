import os
from threading import Thread
from flask import Flask
import telebot
import google.generativeai as genai

# Render portini tekshiruvchi fon veb-serveri
app = Flask(__name__)

@app.route('/')
def home():
    return "Ustoz AI boti faol ishlamoqda!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# API kalitlarni xavfsiz muhitdan (Environment) olish
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.reply_to(message, "Assalomu alaykum, Ustoz! Men dars ishlanmalari, testlar va savollar bo‘yicha yordam beruvchi AI botman. Savolingizni yo‘llashingiz mumkin.")

@bot.message_handler(func=lambda msg: True)
def answer_msg(message):
    try:
        response = model.generate_content(message.text)
        bot.reply_to(message, response.text)
    except Exception as e:
        bot.reply_to(message, f"Kechirasiz, xatolik yuz berdi: {e}")

if __name__ == "__main__":
    # Veb-serverni alohida oqimda yurgizamiz
    Thread(target=run_web).start()
    # Telegram botni xabarlarni tinglashga tushiramiz
    bot.infinity_polling()
