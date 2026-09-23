# -*- coding: utf-8 -*-
"""
80-maktab "Ustoz AI" Telegram Boti - To'liq integratsiyalashgan versiya
Muallif: Boboev Jasurbek & Ustoz AI jamoasi
"""

import os
import sys
import time
import re
import json
import random
from datetime import datetime, timezone, timedelta
from threading import Thread
from flask import Flask
import telebot
from telebot import types
import google.generativeai as genai

import config
import database

# Render Web Service uchun fon veb-serveri
app = Flask(__name__)

@app.route('/')
def home():
    return "80-maktab 'Ustoz AI' tizimi 24/7 faol ishlamoqda!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# --- GEMINI AI AVTOMATIK MODEL TANLASH TIZIMI ---
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or getattr(config, "GEMINI_API_KEY", "")
ai_model = None
active_model_name = None

def get_ai_model():
    global ai_model, active_model_name
    if ai_model is not None:
        return ai_model
    if not GEMINI_KEY:
        return None
    try:
        genai.configure(api_key=GEMINI_KEY)
        supported = [
            m.name for m in genai.list_models() 
            if 'generateContent' in m.supported_generation_methods
        ]
        priority = [
            "models/gemini-2.5-flash",
            "models/gemini-2.0-flash",
            "models/gemini-flash-latest",
            "models/gemini-2.5-pro",
            "models/gemini-pro"
        ]
        chosen = None
        for p in priority:
            if p in supported:
                chosen = p
                break
        active_model_name = chosen or (supported[0] if supported else "gemini-2.5-flash")
        ai_model = genai.GenerativeModel(active_model_name)
        print(f"✅ Gemini AI faollashtirildi! Model: {active_model_name}")
        return ai_model
    except Exception as e:
        print(f"❌ Gemini AI model aniqlashda xatolik: {e}")
        return None

def generate_ai_response(prompt_text):
    global ai_model, active_model_name
    if not GEMINI_KEY:
        return None, "API kalit (GEMINI_API_KEY) topilmadi."
    model = get_ai_model()
    if not model:
        return None, "Google AI tizimiga ulanib bo'lmadi."
    try:
        res = model.generate_content(prompt_text)
        if res and res.text:
            return res.text, None
    except Exception as err:
        try:
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods and m.name != active_model_name:
                    try:
                        backup_model = genai.GenerativeModel(m.name)
                        res = backup_model.generate_content(prompt_text)
                        if res and res.text:
                            ai_model = backup_model
                            active_model_name = m.name
                            return res.text, None
                    except Exception:
                        continue
        except Exception:
            pass
        return None, str(err)
    return None, "AI bo'sh javob qaytardi."

# Telegram bot sozlamasi
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or config.BOT_TOKEN
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

USER_STATES = {}
UZ_TZ = timezone(timedelta(hours=5))
MAX_DAILY_GAME_SECONDS = 22 * 60  # Kuniga ko'pi bilan 22 daqiqa

# ==================== JSON MA'LUMOT BAZALARI ====================
ZVONOK_FILE = "zvonok_jadvali.json"
TOGARAK_FILE = "togaraklar.json"
LIBRARY_FILE = "library_books.json"
FAMILY_FILE = "family_children.json"

DEFAULT_BELL_SCHEDULE = {
    "rejim": "yozgi",
    "yozgi": {
        "1": ["08:00 — 08:45", "08:50 — 09:35", "09:40 — 10:25", "10:35 — 11:20", "11:25 — 12:10", "12:15 — 13:00"],
        "2": ["13:15 — 14:00", "14:05 — 14:50", "14:55 — 15:40", "15:45 — 16:30", "16:35 — 17:20", "17:25 — 18:10"]
    },
    "qishki": {
        "1": ["08:00 — 08:40", "08:45 — 09:25", "09:30 — 10:10", "10:20 — 11:00", "11:05 — 11:45", "11:50 — 12:30"],
        "2": ["12:45 — 13:25", "13:30 — 14:10", "14:15 — 14:55", "15:00 — 15:40", "15:45 — 16:25", "16:30 — 17:10"]
    }
}

def load_json_data(filepath, default_value):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default_value
    return default_value

def save_json_data(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

if not os.path.exists(ZVONOK_FILE):
    save_json_data(ZVONOK_FILE, DEFAULT_BELL_SCHEDULE)

def get_bell_time(smena, slot_num):
    data = load_json_data(ZVONOK_FILE, DEFAULT_BELL_SCHEDULE)
    rejim = data.get("rejim", "yozgi")
    smena_str = str(smena)
    slots = data[rejim].get(smena_str, [])
    if 1 <= slot_num <= len(slots):
        return slots[slot_num - 1]
    return ""

def safe_send_markdown(chat_id, text, reply_to_id=None):
    """Markdown format xatosini yutib yubormaydigan xavfsiz jo'natgich"""
    try:
        return bot.send_message(chat_id, text, parse_mode="Markdown", reply_to_message_id=reply_to_id)
    except Exception:
        clean = text.replace("*", "").replace("_", "").replace("`", "").replace("#", "")
        return bot.send_message(chat_id, clean, parse_mode=None, reply_to_message_id=reply_to_id)

# ==================== O'YIN TAYMERI VA VALYUTA ====================

def get_child_timer_status(uid_str, child_idx, register_activity=False):
    f_data = load_json_data(FAMILY_FILE, {})
    ch = f_data.get(uid_str, {}).get("children", [])[child_idx]
    today_str = datetime.now(UZ_TZ).strftime("%Y-%m-%d")
    now_ts = time.time()
    
    if ch.get("last_played_date") != today_str:
        ch["last_played_date"] = today_str
        ch["played_seconds"] = 0
        ch["session_start"] = now_ts
        
    played = ch.get("played_seconds", 0)
    session_start = ch.get("session_start", now_ts)
    
    if register_activity:
        elapsed = now_ts - session_start
        if 0 < elapsed < 180:
            played += int(elapsed)
            ch["played_seconds"] = played
        ch["session_start"] = now_ts
        save_json_data(FAMILY_FILE, f_data)
    else:
        ch["session_start"] = now_ts
        save_json_data(FAMILY_FILE, f_data)
        
    rem_sec = max(0, MAX_DAILY_GAME_SECONDS - played)
    is_exhausted = (rem_sec <= 0)
    return rem_sec, is_exhausted, ch

def get_child_theme_and_rank(brilliant, yulduz, tanga):
    if brilliant >= 100:
        maqom = "👑 7-daraja: «80-Maktab Akademigi»"
        theme = {"color": "moviy", "border": "🔷", "badge": "🌌 MOVIY BRILLIANT ZUKKOSI 🌌", "icon": "💎"}
    elif brilliant >= 10:
        maqom = "🎓 6-daraja: «Fanlar donishmandi»"
        theme = {"color": "moviy", "border": "🔷", "badge": "🔷 MOVIY KRISTALL SOHIBI 🔷", "icon": "💎"}
    elif brilliant >= 1:
        maqom = "🏆 5-daraja: «Zakovat ustasi»"
        theme = {"color": "moviy", "border": "🔹", "badge": "🔹 YOSH BRILLIANT YETAKCHISI 🔹", "icon": "💎"}
    elif yulduz >= 60:
        maqom = "🎖️ 4-daraja: «Maktab fidoiysi»"
        theme = {"color": "oltin", "border": "🟡", "badge": "⭐ OLTIN YULDUZ SOHIBI ⭐", "icon": "⭐"}
    elif yulduz >= 30:
        maqom = "🥇 3-daraja: «Iqtidorli o‘quvchi»"
        theme = {"color": "oltin", "border": "🟡", "badge": "🌟 OLTIN NURLI BILIMDON 🌟", "icon": "⭐"}
    elif yulduz >= 10:
        maqom = "🥈 2-daraja: «Zukko shogird»"
        theme = {"color": "oltin", "border": "🟡", "badge": "✨ OLTIN QADAM ✨", "icon": "⭐"}
    else:
        maqom = "🥉 1-daraja: «Yosh izlanuvchi»"
        theme = {"color": "kumush", "border": "⚪", "badge": "⚪ KUMUSH TANGA IZLANUVCHISI ⚪", "icon": "🪙"}
        
    return maqom, theme

def get_peer_rank(target_class, target_name, target_uid):
    m = re.findall(r'\d+', target_class)
    gr_num = m[0] if m else "1"
    f_data = load_json_data(FAMILY_FILE, {})
    peers = []
    
    for uid_str, u in f_data.items():
        for ch in u.get("children", []):
            ch_cls = ch.get("class", "")
            if ch_cls.startswith(gr_num):
                score = (ch.get("brilliant", 0) * 1000) + (ch.get("yulduz", 0) * 10) + ch.get("tanga", 0)
                peers.append({
                    "name": ch["name"],
                    "class": ch_cls,
                    "score": score,
                    "is_me": (uid_str == target_uid and ch["name"] == target_name)
                })
                
    peers.sort(key=lambda x: x["score"], reverse=True)
    my_rank = 1
    for idx, p in enumerate(peers, 1):
        if p["is_me"]:
            my_rank = idx
            break
            
    return my_rank, len(peers), gr_num

def update_child_wallet(uid_str, child_idx, add_tanga=0, add_yulduz=0, add_brilliant=0):
    f_data = load_json_data(FAMILY_FILE, {})
    ch = f_data[uid_str]["children"][child_idx]
    
    tanga = ch.get("tanga", 0) + add_tanga
    yulduz = ch.get("yulduz", 0) + add_yulduz
    brilliant = ch.get("brilliant", 0) + add_brilliant
    notice = ""

    # 10 ta Tanga = 1 ta Yulduzcha
    if tanga >= 10:
        new_stars = tanga // 10
        yulduz += new_stars
        tanga = tanga % 10
        notice += f"\n🌟 <b>Qoyilmaqom!</b> 10 ta tangangiz <b>+{new_stars} ta ⭐ Oltin Yulduzcha</b>ga aylandi!"

    # 100 ta Yulduzcha = 1 ta Brilliant
    if yulduz >= 100:
        new_brill = yulduz // 100
        brilliant += new_brill
        yulduz = yulduz % 100
        notice += f"\n💎💎💎 <b>BUYUK ZAFAR!</b> 100 ta yulduzchangiz <b>+{new_brill} ta 💎 BRILLIANT</b>ga aylandi!"

    ch["tanga"] = tanga
    ch["yulduz"] = yulduz
    ch["brilliant"] = brilliant
    save_json_data(FAMILY_FILE, f_data)
    return ch, notice

# ==================== MENYULAR VA TUGMALAR ====================

def get_role_choice_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("👨‍🏫 O‘qituvchi"), types.KeyboardButton("🎒 O‘quvchi / Ota-ona"))
    return markup

def get_admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    b1 = types.KeyboardButton("📥 Excel jadval yuklash")
    b2 = types.KeyboardButton("⚙️ Qo‘ng‘iroqlar sozlamasi")
    b3 = types.KeyboardButton("🎁 O‘quvchini mukofotlash")
    b4 = types.KeyboardButton("🏆 Maktab Reytingi")
    b5 = types.KeyboardButton("📚 Kitob yuklash (PDF)")
    b6 = types.KeyboardButton("📚 E-kutubxona")
    b7 = types.KeyboardButton("👥 O'qituvchilar holati")
    b8 = types.KeyboardButton("🎪 Maktab to‘garaklari")
    b9 = types.KeyboardButton("📊 Maktab umumiy hisoboti")
    b10 = types.KeyboardButton("📈 Jonli statistika")
    b11 = types.KeyboardButton("📢 Xabar yuborish (Filtr)")
    b12 = types.KeyboardButton("📅 Mening darslarim")
    b13 = types.KeyboardButton("🎒 Sinf jadvali")
    b14 = types.KeyboardButton("💡 Metodik AI yordamchi")
    b15 = types.KeyboardButton("🔄 Yangilash")
    b16 = types.KeyboardButton("🏠 Bosh sahifa")
    
    markup.add(b1, b2)
    markup.add(b3, b4)
    markup.add(b5, b6)
    markup.add(b7, b8)
    markup.add(b9, b10)
    markup.add(b11)
    markup.add(b12, b13)
    markup.add(b14, b15)
    markup.add(b16)
    return markup

def get_teacher_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    b1 = types.KeyboardButton("📅 Dars jadvalim")
    b2 = types.KeyboardButton("⏰ Haftalik yuklamam")
    b3 = types.KeyboardButton("🎨 To'garaklarim")
    b4 = types.KeyboardButton("👨‍👩‍👧 Farzandlarim")
    b5 = types.KeyboardButton("🎮 Zukko O‘yinlar")
    b6 = types.KeyboardButton("🏆 Maktab Reytingi")
    b7 = types.KeyboardButton("📚 E-kutubxona")
    b8 = types.KeyboardButton("✏️ Dars kunini to'g'irlash")
    b9 = types.KeyboardButton("🎒 Sinf jadvali")
    b10 = types.KeyboardButton("💡 Metodik AI yordamchi")
    b11 = types.KeyboardButton("🔄 Yangilash")
    b12 = types.KeyboardButton("✍️ Talab va takliflar")
    b13 = types.KeyboardButton("🏠 Bosh sahifa")
    markup.add(b1, b2)
    markup.add(b3, b4)
    markup.add(b5, b6)
    markup.add(b7, b8)
    markup.add(b9, b10)
    markup.add(b11, b12)
    markup.add(b13)
    return markup

def get_student_parent_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    b1 = types.KeyboardButton("🎒 Farzandlarim darslari")
    b2 = types.KeyboardButton("🎮 Zukko O‘yinlar")
    b3 = types.KeyboardButton("🏆 Maktab Reytingi")
    b4 = types.KeyboardButton("👨‍👩‍👧 Farzandlarni tahrirlash")
    b5 = types.KeyboardButton("📚 E-kutubxona")
    b6 = types.KeyboardButton("💡 Savol-javob (AI)")
    b7 = types.KeyboardButton("🔄 Yangilash")
    b8 = types.KeyboardButton("✍️ Taklif bildirish")
    b9 = types.KeyboardButton("🏠 Bosh sahifa")
    markup.add(b1, b2)
    markup.add(b3, b4)
    markup.add(b5, b6)
    markup.add(b7, b8)
    markup.add(b9)
    return markup

# ==================== START VA BOSH SAHIFA ====================

@bot.message_handler(commands=['start'])
@bot.message_handler(func=lambda msg: msg.text in ["🏠 Bosh sahifa", "🏠 Bosh sahifaga qaytish"])
def handle_start(message):
    uid = message.from_user.id
    if uid in USER_STATES:
        del USER_STATES[uid]
    
    database.update_activity(uid, message.from_user.first_name)
    user = database.get_user(uid)
    
    # 1. Admin tekshiruvi
    if user and user.get("role") == "admin":
        bot.send_message(
            message.chat.id,
            f"👑 <b>Assalomu alaykum, Bosh Admin {user['full_name']}!</b>\n"
            f"80-Maktabning barcha boshqaruv tizimlari sizning to‘liq nazoratingizda.",
            reply_markup=get_admin_keyboard()
        )
        return
        
    # 2. O'qituvchi tekshiruvi (Doimiy xotiradan to'g'ridan-to'g'ri ochiladi)
    if user and user.get("role") == "teacher":
        bot.send_message(
            message.chat.id,
            f"👨‍🏫 <b>Assalomu alaykum, {user['teacher_name']}!</b>\n"
            f"80-maktab 'Ustoz AI' shaxsiy kabinetingizdasiz.",
            reply_markup=get_teacher_keyboard()
        )
        return

    # 3. O'quvchi / ota-ona tekshiruvi (Tasdiqlangan bo'lsa darhol kabinet ochiladi)
    f_data = load_json_data(FAMILY_FILE, {})
    if str(uid) in f_data and f_data[str(uid)].get("confirmed"):
        bot.send_message(
            message.chat.id,
            f"🎒 <b>Assalomu alaykum!</b>\n80-Maktab ta’lim va Zukko O‘yinlar portaliga xush kelibsiz.",
            reply_markup=get_student_parent_keyboard()
        )
        return

    # 4. Yangi foydalanuvchi — Rol tanlash
    bot.send_message(
        message.chat.id,
        "🏫 <b>80-umumiy o‘rta ta’lim maktabi «Ustoz AI» tizimiga xush kelibsiz!</b>\n\n"
        "Iltimos, o‘z maqomingizni tanlang:",
        reply_markup=get_role_choice_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data == "go_home_inline")
def handle_home_inline(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    handle_start(call.message)
    bot.answer_callback_query(call.id)

# ==================== O'QITUVCHILAR RO'YXATDAN O'TISH ====================

@bot.message_handler(func=lambda msg: msg.text == "👨‍🏫 O‘qituvchi")
def teacher_auth_start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True))
    markup.add(types.KeyboardButton("🏠 Bosh sahifa"))
    bot.send_message(
        message.chat.id, 
        "👨‍🏫 Shaxsingizni tasdiqlash uchun pastdagi <b>«📱 Telefon raqamni yuborish»</b> tugmasini bosing:", 
        reply_markup=markup
    )

@bot.message_handler(content_types=['contact'])
def handle_contact_submission(message):
    if not message.contact:
        return
    uid = message.from_user.id
    phone = message.contact.phone_number.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip() or "Ustoz"
    
    if database.is_phone_admin(phone, config.ADMIN_PHONES):
        database.register_user(uid, phone, full_name, "Boboev J", "admin")
        bot.send_message(message.chat.id, "🎉 <b>Bosh Admin kabinetingiz ochildi.</b>", reply_markup=get_admin_keyboard())
        return

    USER_STATES[uid] = {"phone": phone, "full_name": full_name}
    teachers = database.get_teachers_list()
    markup = types.InlineKeyboardMarkup(row_width=2)
    for t in teachers[:10]:
        markup.add(types.InlineKeyboardButton(f"👤 {t['name']}", callback_data=f"selteach_{t['name']}"))
    markup.add(types.InlineKeyboardButton("❌ Bekor qilish", callback_data="go_home_inline"))
    bot.send_message(message.chat.id, f"📱 Raqam: <code>{phone}</code>\nRo‘yxatdan o‘z ism-familiyangizni tanlang:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("selteach_"))
def handle_teacher_chosen(call):
    teacher_name = call.data.replace("selteach_", "")
    uid = call.from_user.id
    state = USER_STATES.get(uid, {})
    phone = state.get("phone", "Noma'lum")
    full_name = state.get("full_name", call.from_user.first_name)
    req_id = database.create_pending_request(uid, phone, full_name, teacher_name)
    bot.edit_message_text(f"⏳ Arizangiz Bosh Adminga yuborildi!\nTasdiqlanishi bilan xabar olasiz.", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)
    
    admin_markup = types.InlineKeyboardMarkup(row_width=2)
    admin_markup.add(types.InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"appreq_{req_id}"), types.InlineKeyboardButton("❌ Rad etish", callback_data=f"rejreq_{req_id}"))
    for a_id in database.get_all_admins():
        try:
            bot.send_message(a_id, f"🔔 <b>O‘qituvchi so‘rovi:</b> {teacher_name}\n📱 {phone}", reply_markup=admin_markup)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("appreq_"))
def handle_admin_app(call):
    req_id = int(call.data.split("_")[1])
    req = database.approve_request(req_id)
    if req:
        bot.edit_message_text(f"✅ Tasdiqlandi: <b>{req['teacher_name']}</b>", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(req["telegram_id"], "🎉 <b>Arizangiz tasdiqlandi! Siz faolsiz.</b>", reply_markup=get_teacher_keyboard())
        except Exception:
            pass

# ==================== O'QUVCHI / OTA-ONA (1-7 FARZAND) ====================

def render_family_card(user_id):
    f_data = load_json_data(FAMILY_FILE, {})
    u_data = f_data.get(str(user_id), {})
    children = u_data.get("children", [])
    
    text = f"👨‍👩‍👧 <b>Farzandlar ro‘yxati ({len(children)}/7 ta):</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    if not children:
        text += "<i>Hozircha birorta ham farzand qo‘shilmagan.</i>\n"
    else:
        for idx, ch in enumerate(children, 1):
            text += f"{idx}. 👤 <b>{ch['name']}</b> — <code>{ch['class']}</code> sinf\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    if len(children) < 7:
        markup.add(types.InlineKeyboardButton("➕ Farzand qo‘shish", callback_data="fam_add_child"))
    if children:
        markup.add(types.InlineKeyboardButton("✏️ Tahrirlash / O‘chirish", callback_data="fam_edit_list"))
        markup.add(types.InlineKeyboardButton("✅ Barchasini tasdiqlash", callback_data="fam_confirm_all"))
    markup.add(types.InlineKeyboardButton("🏠 Bosh sahifa", callback_data="go_home_inline"))
    return text, markup

@bot.message_handler(func=lambda msg: msg.text in ["🎒 O‘quvchi / Ota-ona", "👨‍👩‍👧 Farzandlarim", "👨‍👩‍👧 Farzandlarni tahrirlash"])
def handle_family_main(message):
    text, markup = render_family_card(message.from_user.id)
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "fam_add_child")
def handle_add_child_click(call):
    markup = types.InlineKeyboardMarkup(row_width=4)
    markup.add(*[types.InlineKeyboardButton(f"{i}-sinf", callback_data=f"chgr_{i}") for i in range(1, 12)])
    markup.add(types.InlineKeyboardButton("❌ Bekor qilish", callback_data="go_home_inline"))
    bot.edit_message_text("🎒 <b>Farzandingiz sinfini tanlang:</b>", call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("chgr_"))
def handle_fam_gr(call):
    val = call.data.replace("chgr_", "")
    matched = [f"{val}-A", f"{val}-B", f"{val}-V", f"{val}-D"]
    markup = types.InlineKeyboardMarkup(row_width=2)
    for c in matched:
        markup.add(types.InlineKeyboardButton(f"🏫 {c}", callback_data=f"chcls_{c}"))
    markup.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data="fam_add_child"))
    bot.edit_message_text(f"🏫 <b>{val}-sinflar:</b> Aniq sinfni tanlang:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("chcls_"))
def handle_fam_cls(call):
    sel_cls = call.data.replace("chcls_", "")
    USER_STATES[call.from_user.id] = {"action": "fam_wait_name", "class": sel_cls}
    bot.send_message(call.message.chat.id, f"🏫 Sinf: <b>{sel_cls}</b>\n\nFarzandingizning <b>ismini</b> yozib yuboring:\n<i>(Masalan: Ali yoki Marjona)</i>")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "fam_confirm_all")
def handle_fam_confirm(call):
    uid = str(call.from_user.id)
    f_data = load_json_data(FAMILY_FILE, {})
    if uid in f_data and f_data[uid].get("children"):
        f_data[uid]["confirmed"] = True
        save_json_data(FAMILY_FILE, f_data)
        bot.answer_callback_query(call.id, "Tasdiqlandi! ✅")
        user = database.get_user(call.from_user.id)
        if user and user.get("role") == "teacher":
            bot.send_message(call.message.chat.id, "✅ Farzandlaringiz tasdiqlandi!", reply_markup=get_teacher_keyboard())
        else:
            bot.send_message(call.message.chat.id, "🎉 Kabinetingiz to‘liq tayyor! Endi Zukko O‘yinlar o‘ynashingiz mumkin.", reply_markup=get_student_parent_keyboard())
    else:
        bot.answer_callback_query(call.id, "Avval kamida 1 nafar farzand qo‘shing!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "fam_edit_list")
def handle_fam_edit_list(call):
    uid = str(call.from_user.id)
    children = load_json_data(FAMILY_FILE, {}).get(uid, {}).get("children", [])
    markup = types.InlineKeyboardMarkup(row_width=1)
    for idx, ch in enumerate(children):
        markup.add(types.InlineKeyboardButton(f"🗑 {ch['name']} ({ch['class']}) ni o‘chirish", callback_data=f"delchild_{idx}"))
    markup.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data="fam_back_card"))
    bot.edit_message_text("O‘chirmoqchi bo‘lgan farzandingizni tanlang:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delchild_"))
def handle_del_child(call):
    idx = int(call.data.replace("delchild_", ""))
    uid = str(call.from_user.id)
    f_data = load_json_data(FAMILY_FILE, {})
    if uid in f_data and 0 <= idx < len(f_data[uid].get("children", [])):
        f_data[uid]["children"].pop(idx)
        save_json_data(FAMILY_FILE, f_data)
    text, markup = render_family_card(call.from_user.id)
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "fam_back_card")
def handle_fam_back(call):
    text, markup = render_family_card(call.from_user.id)
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

# ==================== 🎮 ZUKKO O'YINLAR (22 DAQIQA VA RANGLI HUB) ====================

@bot.message_handler(func=lambda msg: msg.text == "🎮 Zukko O‘yinlar")
def handle_games_entry(message):
    uid_str = str(message.from_user.id)
    f_data = load_json_data(FAMILY_FILE, {})
    children = f_data.get(uid_str, {}).get("children", [])
    
    if not children:
        bot.send_message(
            message.chat.id,
            "⚠️ <b>O‘yin o‘ynash uchun avval kamida 1 nafar farzand kiritilgan bo‘lishi kerak.</b>\n\n"
            "Iltimos, «👨‍👩‍👧 Farzandlarim» tugmasi orqali bolangizni qo‘shing."
        )
        return
        
    markup = types.InlineKeyboardMarkup(row_width=1)
    for idx, ch in enumerate(children):
        t = ch.get("tanga", 0)
        y = ch.get("yulduz", 0)
        b = ch.get("brilliant", 0)
        btn_text = f"👦 {ch['name']} ({ch['class']})  |  💎 {b}  ⭐ {y}  🪙 {t}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"playas_{idx}"))
    markup.add(types.InlineKeyboardButton("🏠 Bosh sahifa", callback_data="go_home_inline"))
    
    bot.send_message(
        message.chat.id,
        "🎮 <b>ZUKKO BILIMDON O‘YINLAR MAYDONI:</b>\n\n"
        "🌈 <i>Hozir kim o‘ynamoqchi? O‘z ismingizni tanlang:</i>",
        reply_markup=markup,
        parse_mode="HTML"
    )

def render_child_game_hub(uid_str, ch_idx):
    rem_sec, is_exhausted, ch = get_child_timer_status(uid_str, ch_idx, register_activity=False)
    
    t = ch.get("tanga", 0)
    y = ch.get("yulduz", 0)
    b = ch.get("brilliant", 0)
    maqom, theme = get_child_theme_and_rank(b, y, t)
    
    my_rank, total_peers, gr_num = get_peer_rank(ch.get("class", "1"), ch["name"], uid_str)
    rem_min = rem_sec // 60
    rem_s = rem_sec % 60
    
    played_sec = MAX_DAILY_GAME_SECONDS - rem_sec
    time_pct = min(10, int((played_sec / MAX_DAILY_GAME_SECONDS) * 10))
    time_bar = "🟥" * time_pct + "🟩" * (10 - time_pct)

    if is_exhausted:
        stop_text = (
            f"🛑 <b>{ch['name']}, sizning bugungi hisobingiz tugadi!</b>\n\n"
            f"📖 <b>Kitob o‘qing va dam oling, sizni buyuk marralar kutmoqda!</b> 🚀\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ <i>Kunlik 22 daqiqa limit to‘liq sarflandi.</i>\n"
            f"🌙 <i>Yangi o‘yin vaqti ertaga tongda ochiladi.</i>\n\n"
            f"🎖️ <b>Bugungi natijangiz:</b>\n"
            f"• Maqom: {maqom}\n"
            f"• Jamg‘arma: 💎 {b} ta | ⭐ {y} ta | 🪙 {t} ta\n"
            f"• {gr_num}-sinf tengdoshlar orasida: <b>{my_rank}-o‘rin</b>"
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("📚 Darsliklarni o‘qish (E-Kutubxona)", callback_data="go_to_lib_inline"))
        markup.add(types.InlineKeyboardButton("⬅️ Boshqa farzandni tanlash", callback_data="back_to_players"))
        return stop_text, markup

    b_sym = theme["border"]
    text = (
        f"{b_sym*12}\n"
        f"   {theme['badge']}\n"
        f"{b_sym*12}\n\n"
        f"👤 <b>O‘yinchi:</b> <b>{ch['name']}</b> (<code>{ch['class']} sinf</code>)\n"
        f"🎖️ <b>Maqom:</b> {maqom}\n"
        f"🏫 <b>Tengdoshlar ichida:</b> <b>{my_rank}-o‘rinda</b> <i>(Jami: {total_peers} nafar)</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 <b>Brilliant:</b> <code>{b} ta</code>\n"
        f"⭐ <b>Oltin Yulduz:</b> <code>{y} ta</code>\n"
        f"🪙 <b>Zukko Tanga:</b> <code>{t} / 10 ta</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ <b>Bugungi qolgan vaqtingiz:</b> <b>{rem_min} daqiqa {rem_s} soniya</b>\n"
        f"   <code>[{time_bar}]</code> (Maks: 22 daq)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🕹️ <i>O‘yin turini tanlang:</i>"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("⚡ Tezkor Arifmetika (Blits) 🟢", callback_data=f"g_math_{ch_idx}"),
        types.InlineKeyboardButton("🧠 AI Zukko Viktorina 🟣", callback_data=f"g_quiz_{ch_idx}"),
        types.InlineKeyboardButton("🧩 Mantiqiy Topishmoqlar 🟡", callback_data=f"g_riddle_{ch_idx}"),
        types.InlineKeyboardButton(f"🏅 {gr_num}-Sinflar Tengdoshlar Reytingi 🏆", callback_data=f"peerrank_{gr_num}_{ch_idx}"),
        types.InlineKeyboardButton("⬅️ O‘yinchini almashtirish", callback_data="back_to_players")
    )
    return text, markup

@bot.callback_query_handler(func=lambda call: call.data.startswith("playas_"))
def handle_player_select(call):
    ch_idx = int(call.data.replace("playas_", ""))
    uid_str = str(call.from_user.id)
    text, markup = render_child_game_hub(uid_str, ch_idx)
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_players")
def handle_back_to_players(call):
    uid_str = str(call.from_user.id)
    f_data = load_json_data(FAMILY_FILE, {})
    children = f_data.get(uid_str, {}).get("children", [])
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for idx, ch in enumerate(children):
        t = ch.get("tanga", 0)
        y = ch.get("yulduz", 0)
        b = ch.get("brilliant", 0)
        btn_text = f"👦 {ch['name']} ({ch['class']})  |  💎 {b}  ⭐ {y}  🪙 {t}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"playas_{idx}"))
    markup.add(types.InlineKeyboardButton("🏠 Bosh sahifa", callback_data="go_home_inline"))
    
    bot.edit_message_text("🎮 <b>Kim o‘ynamoqchi? O‘z ismingizni tanlang:</b>", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

# 1. Tezkor Arifmetika
@bot.callback_query_handler(func=lambda call: call.data.startswith("g_math_"))
def handle_math_game(call):
    ch_idx = int(call.data.replace("g_math_", ""))
    uid_str = str(call.from_user.id)
    rem_sec, is_exhausted, ch = get_child_timer_status(uid_str, ch_idx, register_activity=True)
    if is_exhausted:
        text, markup = render_child_game_hub(uid_str, ch_idx)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
        return
        
    m = re.findall(r'\d+', ch.get("class", "1"))
    gr_num = int(m[0]) if m else 1
    ops = ["+", "-"]
    if gr_num >= 3:
        ops.append("×")
    op = random.choice(ops)
    
    if op == "+":
        n1 = random.randint(3 * gr_num, 15 * gr_num)
        n2 = random.randint(2, 10 * gr_num)
        ans = n1 + n2
    elif op == "-":
        n1 = random.randint(10 * gr_num, 25 * gr_num)
        n2 = random.randint(1, n1)
        ans = n1 - n2
    else:
        n1 = random.randint(2, 9)
        n2 = random.randint(2, 9)
        ans = n1 * n2

    options = {ans}
    while len(options) < 4:
        delta = random.choice([-3, -2, -1, 1, 2, 3, 5, 10])
        wrong = ans + delta
        if wrong >= 0:
            options.add(wrong)
    opt_list = list(options)
    random.shuffle(opt_list)
    
    color_icons = ["🔴", "🔵", "🟡", "🟢"]
    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [types.InlineKeyboardButton(f"{color_icons[i]} {val}", callback_data=f"ansmath_{ch_idx}_{1 if val==ans else 0}_{ans}") for i, val in enumerate(opt_list)]
    markup.add(*btns)
    markup.add(types.InlineKeyboardButton("⬅️ O‘yin markazi", callback_data=f"playas_{ch_idx}"))
    
    q_text = (
        f"⚡ <b>TEZKOR ARIFMETIKA (BLITS):</b>\n\n"
        f"👤 O‘yinchi: <b>{ch['name']}</b> ({ch['class']} sinf)\n"
        f"⏳ Qolgan vaqt: <b>{rem_sec // 60} daqiqa</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Misolni yeching:</b>\n\n"
        f"     <code>{n1} {op} {n2} = ?</code>\n\n"
        f"<i>To‘g‘ri javob: +1 🪙 Zukko Tanga</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    bot.edit_message_text(q_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("ansmath_"))
def handle_math_answer(call):
    p = call.data.split("_")
    ch_idx = int(p[1])
    is_correct = int(p[2]) == 1
    correct_ans = p[3]
    uid_str = str(call.from_user.id)
    
    rem_sec, is_exhausted, ch = get_child_timer_status(uid_str, ch_idx, register_activity=True)
    if is_exhausted:
        text, markup = render_child_game_hub(uid_str, ch_idx)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
        return
        
    if is_correct:
        ch, note = update_child_wallet(uid_str, ch_idx, add_tanga=1)
        res_text = f"🎉 <b>BARAKALLA, TO‘G‘RI!</b>\n\n🪙 Sizga <b>+1 Zukko Tanga</b> berildi!{note}\n\nHisob: 💎 {ch['brilliant']} | ⭐ {ch['yulduz']} | 🪙 {ch['tanga']}"
    else:
        res_text = f"❌ <b>Afsus, noto‘g‘ri!</b>\nTo‘g‘ri javob: <b>{correct_ans}</b> edi."
        
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("⚡ Yana bitta misol! 🚀", callback_data=f"g_math_{ch_idx}"))
    markup.add(types.InlineKeyboardButton("⬅️ O‘yin markazi", callback_data=f"playas_{ch_idx}"))
    bot.edit_message_text(res_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

# 2. AI Viktorina
@bot.callback_query_handler(func=lambda call: call.data.startswith("g_quiz_"))
def handle_quiz_game(call):
    ch_idx = int(call.data.replace("g_quiz_", ""))
    uid_str = str(call.from_user.id)
    rem_sec, is_exhausted, ch = get_child_timer_status(uid_str, ch_idx, register_activity=True)
    if is_exhausted:
        text, markup = render_child_game_hub(uid_str, ch_idx)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
        return
        
    bot.edit_message_text("⏳ <i>Gemini AI siz uchun maxsus rangli savol tuzmoqda...</i>", call.message.chat.id, call.message.message_id)
    
    prompt = (
        f"O'quvchi {ch.get('class', '4')}-sinfda o'qiydi. Unga umumiy fanlardan 1 ta qiziqarli savol va 4 ta variant tuzib ber. "
        f"Javobni FAQAT quyidagi JSON formatida qaytar:\n"
        f'{{"savol": "Savol matni", "variantlar": ["A javob", "B javob", "C javob", "D javob"], "togri_index": 0}}'
    )
    ans_text, _ = generate_ai_response(prompt)
    try:
        clean_json = re.search(r'\{.*\}', ans_text, re.DOTALL).group(0)
        q_data = json.loads(clean_json)
    except Exception:
        q_data = {
            "savol": "Alisher Navoiy qaysi asrning buyuk shoiri hisoblanadi?",
            "variantlar": ["XV asr", "XII asr", "XVIII asr", "XIX asr"],
            "togri_index": 0
        }

    markup = types.InlineKeyboardMarkup(row_width=1)
    color_icons = ["🟣 A)", "🔵 B)", "🟡 C)", "🟢 D)"]
    for i, v in enumerate(q_data["variantlar"]):
        is_c = 1 if i == q_data["togri_index"] else 0
        markup.add(types.InlineKeyboardButton(f"{color_icons[i]} {v}", callback_data=f"ansquiz_{ch_idx}_{is_c}"))
    markup.add(types.InlineKeyboardButton("⬅️ Hubga qaytish", callback_data=f"playas_{ch_idx}"))

    text = (
        f"🧠 <b>AI ZUKKO VIKTORINA:</b>\n\n"
        f"👤 O‘yinchi: <b>{ch['name']}</b> ({ch['class']} sinf)\n"
        f"⏳ Qolgan vaqt: <b>{rem_sec // 60} daqiqa</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"❓ <b>Savol:</b>\n{q_data['savol']}\n\n"
        f"<i>To‘g‘ri javob: +2 🪙 Zukko Tanga</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("ansquiz_"))
def handle_quiz_ans(call):
    p = call.data.split("_")
    ch_idx = int(p[1])
    is_correct = int(p[2]) == 1
    uid_str = str(call.from_user.id)
    
    rem_sec, is_exhausted, ch = get_child_timer_status(uid_str, ch_idx, register_activity=True)
    if is_exhausted:
        text, markup = render_child_game_hub(uid_str, ch_idx)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
        return
        
    if is_correct:
        ch, note = update_child_wallet(uid_str, ch_idx, add_tanga=2)
        res = f"🎉 <b>A’LO! TO‘G‘RI JAVOB!</b>\n\n🪙 <b>+2 Zukko Tanga</b> qo‘shildi!{note}\n\nHisob: 💎 {ch['brilliant']} | ⭐ {ch['yulduz']} | 🪙 {ch['tanga']}"
    else:
        res = "❌ <b>Afsus, noto‘g‘ri javob!</b> Keyingi savolda omad tilaymiz! 🌟"
        
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🧠 Yangi savol! 🚀", callback_data=f"g_quiz_{ch_idx}"))
    markup.add(types.InlineKeyboardButton("⬅️ O‘yin markazi", callback_data=f"playas_{ch_idx}"))
    bot.edit_message_text(res, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

# 3. Mantiqiy Topishmoqlar
RIDDLES = [
    {"q": "Qo‘li yo‘q, oyog‘i yo‘q, derazaga naqsh chizar. Bu nima?", "opts": ["Ayoz / Qahraton", "Yomg‘ir", "Shamol", "Qor"], "c": 0},
    {"q": "O‘zi bitta, ko‘zi mingtadan ko‘p. Bu nima?", "opts": ["G‘alvir", "Ko‘zoynak", "Daftar", "Yulduz"], "c": 0},
    {"q": "Kunduzi uxlaydi, kechasi yonadi. Bu nima?", "opts": ["Oy va yulduzlar", "Quyosh", "Gugurt", "Sham"], "c": 0},
    {"q": "Tilsiz, zabonsiz, kishiga aql o‘rgatar. Bu nima?", "opts": ["Kitob", "Radio", "Telefon", "Qalam"], "c": 0}
]

@bot.callback_query_handler(func=lambda call: call.data.startswith("g_riddle_"))
def handle_riddle_game(call):
    ch_idx = int(call.data.replace("g_riddle_", ""))
    uid_str = str(call.from_user.id)
    rem_sec, is_exhausted, ch = get_child_timer_status(uid_str, ch_idx, register_activity=True)
    if is_exhausted:
        text, markup = render_child_game_hub(uid_str, ch_idx)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
        return
        
    r = random.choice(RIDDLES)
    markup = types.InlineKeyboardMarkup(row_width=1)
    icons = ["🟡", "🟠", "🟢", "🔵"]
    for i, opt in enumerate(r["opts"]):
        markup.add(types.InlineKeyboardButton(f"{icons[i]} {opt}", callback_data=f"ansrid_{ch_idx}_{1 if i==r['c'] else 0}"))
    markup.add(types.InlineKeyboardButton("⬅️ Hubga qaytish", callback_data=f"playas_{ch_idx}"))
    
    text = (
        f"🧩 <b>MANTIQIY TOPISHMOQ:</b>\n\n"
        f"👤 O‘yinchi: <b>{ch['name']}</b>\n"
        f"⏳ Qolgan vaqt: <b>{rem_sec // 60} daqiqa</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🦉 <i>«{r['q']}»</i>\n\n"
        f"<i>To‘g‘ri javob: +2 🪙 Zukko Tanga</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("ansrid_"))
def handle_riddle_ans(call):
    p = call.data.split("_")
    ch_idx = int(p[1])
    is_correct = int(p[2]) == 1
    uid_str = str(call.from_user.id)
    
    rem_sec, is_exhausted, ch = get_child_timer_status(uid_str, ch_idx, register_activity=True)
    if is_exhausted:
        text, markup = render_child_game_hub(uid_str, ch_idx)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
        return
        
    if is_correct:
        ch, note = update_child_wallet(uid_str, ch_idx, add_tanga=2)
        res = f"🎉 <b>TOPQIRSIZ! TO‘G‘RI TOPDINGIZ!</b>\n\n🪙 <b>+2 Zukko Tanga</b> hisobingizga tushdi!{note}\n\nHisob: 💎 {ch['brilliant']} | ⭐ {ch['yulduz']} | 🪙 {ch['tanga']}"
    else:
        res = "❌ <b>Topa olmadingiz!</b> Boshqa topishmoqni sinab ko‘ring! 💡"
        
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🧩 Yangi topishmoq! 🚀", callback_data=f"g_riddle_{ch_idx}"))
    markup.add(types.InlineKeyboardButton("⬅️ O‘yin markazi", callback_data=f"playas_{ch_idx}"))
    bot.edit_message_text(res, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

# 4. Tengdoshlar Reytingi
@bot.callback_query_handler(func=lambda call: call.data.startswith("peerrank_"))
def handle_show_peer_rank(call):
    p = call.data.split("_")
    gr_num = p[1]
    ch_idx = int(p[2])
    
    f_data = load_json_data(FAMILY_FILE, {})
    peers = []
    for u in f_data.values():
        for c in u.get("children", []):
            if c.get("class", "").startswith(gr_num):
                score = (c.get("brilliant", 0) * 1000) + (c.get("yulduz", 0) * 10) + c.get("tanga", 0)
                peers.append({"name": c["name"], "class": c["class"], "b": c.get("brilliant", 0), "y": c.get("yulduz", 0), "t": c.get("tanga", 0), "score": score})
                
    peers.sort(key=lambda x: x["score"], reverse=True)
    
    text = (
        f"╔══════════════════════════╗\n"
        f"   🏅 <b>{gr_num}-SINFLAR REYTINGI</b> 🏅\n"
        f"╚══════════════════════════╝\n\n"
    )
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for i, pr in enumerate(peers[:10]):
        text += f"{medals[i]} <b>{pr['name']}</b> ({pr['class']}): 💎 {pr['b']} | ⭐ {pr['y']} | 🪙 {pr['t']}\n"
    if not peers:
        text += "<i>Hozircha ma’lumot yo‘q.</i>\n"
        
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ O‘yin markaziga qaytish", callback_data=f"playas_{ch_idx}"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

# ==================== UMUMIY MAKTAB REYTINGI (TOP-10) ====================

def get_leaderboard_text():
    f_data = load_json_data(FAMILY_FILE, {})
    all_players = []
    for u in f_data.values():
        for ch in u.get("children", []):
            b = ch.get("brilliant", 0)
            y = ch.get("yulduz", 0)
            t = ch.get("tanga", 0)
            score = (b * 1000) + (y * 10) + t
            all_players.append({"name": ch["name"], "class": ch["class"], "b": b, "y": y, "t": t, "score": score})
            
    all_players.sort(key=lambda x: x["score"], reverse=True)
    text = f"╔══════════════════════════╗\n   🏆 <b>80-MAKTAB FAXRLARI (TOP-10)</b> 🏆\n╚══════════════════════════╝\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    if not all_players or all_players[0]["score"] == 0:
        text += "<i>Hozircha reyting shakllanmagan. Ilk tangalarni to‘plab yetakchiga aylaning!</i>\n"
    else:
        for i, p in enumerate(all_players[:10]):
            maqom, theme = get_child_theme_and_rank(p['b'], p['y'], p['t'])
            text += f"{medals[i]} <b>{p['name']}</b> ({p['class']})\n   {theme['icon']} 💎 {p['b']}  ⭐ {p['y']}  🪙 {p['t']} | <i>{maqom}</i>\n\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n<i>Jonli maktab reytingi</i>"
    return text

@bot.message_handler(func=lambda msg: msg.text == "🏆 Maktab Reytingi")
def handle_leaderboard_msg(message):
    bot.send_message(message.chat.id, get_leaderboard_text(), parse_mode="HTML")

# ==================== ADMIN: MUKOFOTLASH VA QO'NG'IROQLAR ====================

@bot.message_handler(func=lambda msg: msg.text == "🎁 O‘quvchini mukofotlash")
def handle_admin_reward(message):
    user = database.get_user(message.from_user.id)
    if not user or user.get("role") != "admin":
        return
    f_data = load_json_data(FAMILY_FILE, {})
    markup = types.InlineKeyboardMarkup(row_width=1)
    count = 0
    for uid_str, u_info in f_data.items():
        for idx, ch in enumerate(u_info.get("children", [])):
            count += 1
            markup.add(types.InlineKeyboardButton(f"👤 {ch['name']} ({ch['class']})", callback_data=f"admrew_{uid_str}_{idx}"))
    if count == 0:
        bot.send_message(message.chat.id, "Bazada o‘quvchilar yo‘q.")
        return
    markup.add(types.InlineKeyboardButton("❌ Bekor qilish", callback_data="go_home_inline"))
    bot.send_message(message.chat.id, "🎁 <b>Mukofotlamoqchi bo‘lgan o‘quvchini tanlang:</b>", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admrew_"))
def handle_admin_reward_target(call):
    p = call.data.split("_")
    uid_str, ch_idx = p[1], int(p[2])
    ch = load_json_data(FAMILY_FILE, {})[uid_str]["children"][ch_idx]
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🪙 +5 Zukko Tanga berish", callback_data=f"grant_{uid_str}_{ch_idx}_tanga_5"),
        types.InlineKeyboardButton("⭐ +1 Oltin Yulduzcha berish", callback_data=f"grant_{uid_str}_{ch_idx}_yulduz_1"),
        types.InlineKeyboardButton("💎 +1 BRILLIANT (Olimpiada/G‘alaba)", callback_data=f"grant_{uid_str}_{ch_idx}_brill_1"),
        types.InlineKeyboardButton("❌ Bekor qilish", callback_data="go_home_inline")
    )
    bot.edit_message_text(f"🎁 <b>{ch['name']} ({ch['class']})</b> ga qanday mukofot bermoqchisiz?", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("grant_"))
def handle_grant_execute(call):
    p = call.data.split("_")
    uid_str, ch_idx, typ, val = p[1], int(p[2]), p[3], int(p[4])
    dt = val if typ == "tanga" else 0
    dy = val if typ == "yulduz" else 0
    db = val if typ == "brill" else 0
    
    ch, note = update_child_wallet(uid_str, ch_idx, add_tanga=dt, add_yulduz=dy, add_brilliant=db)
    bot.edit_message_text(f"✅ Mukofot topshirildi!\n\n{ch['name']} hisobi:\n💎 {ch['brilliant']} | ⭐ {ch['yulduz']} | 🪙 {ch['tanga']}", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Yuborildi!")
    
    try:
        m_text = "+5 🪙 Zukko Tanga" if typ=="tanga" else ("+1 ⭐ Oltin Yulduzcha" if typ=="yulduz" else "+1 💎 BRILLIANT!")
        bot.send_message(int(uid_str), f"🎉 <b>XUSHXABAR!</b>\n\n<b>{ch['name']}</b>, siz maktabdagi faolligingiz uchun Bosh Admin tomonidan taqdirlandingiz:\n🎁 Mukofot: <b>{m_text}</b>\nHisob: 💎 {ch['brilliant']} | ⭐ {ch['yulduz']} | 🪙 {ch['tanga']}")
    except Exception:
        pass

@bot.message_handler(func=lambda msg: msg.text == "⚙️ Qo‘ng‘iroqlar sozlamasi" or msg.text == "/admin_soatlar")
def handle_admin_bell_menu(message):
    user = database.get_user(message.from_user.id)
    if not user or user.get("role") != "admin":
        return
    data = load_json_data(ZVONOK_FILE, DEFAULT_BELL_SCHEDULE)
    faol = data.get("rejim", "yozgi")
    matn = f"⚙️ <b>Qo‘ng‘iroqlar jadvali (Admin):</b>\n\nJoriy rejim: <b>{'☀️ Yozgi rejim (45 daqiqa)' if faol=='yozgi' else '❄️ Qishki rejim (40 daqiqa)'}</b>"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("☀️ Yozgi rejim", callback_data="adm_bell_yozgi"), types.InlineKeyboardButton("❄️ Qishki rejim", callback_data="adm_bell_qishki"))
    bot.send_message(message.chat.id, matn, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_bell_"))
def process_bell_switch(call):
    user = database.get_user(call.from_user.id)
    if not user or user.get("role") != "admin":
        return
    data = load_json_data(ZVONOK_FILE, DEFAULT_BELL_SCHEDULE)
    data["rejim"] = "yozgi" if call.data == "adm_bell_yozgi" else "qishki"
    save_json_data(ZVONOK_FILE, data)
    bot.answer_callback_query(call.id, "Rejim yangilandi!")
    bot.edit_message_text(f"⚙️ Qo‘ng‘iroqlar jadvali yangilandi: <b>{'☀️ Yozgi' if data['rejim']=='yozgi' else '❄️ Qishki'}</b>", call.message.chat.id, call.message.message_id, parse_mode="HTML")

# ==================== KUTUBXONA VA TO'GARAK ====================

@bot.message_handler(func=lambda msg: msg.text == "📚 Kitob yuklash (PDF)")
def handle_upload_book_menu(message):
    user = database.get_user(message.from_user.id)
    if not user or user.get("role") != "admin":
        return
    markup = types.InlineKeyboardMarkup(row_width=4)
    markup.add(*[types.InlineKeyboardButton(f"{i}-sinf", callback_data=f"upb_{i}") for i in range(1, 12)])
    markup.add(types.InlineKeyboardButton("🏠 Bosh sahifa", callback_data="go_home_inline"))
    bot.send_message(message.chat.id, "📚 Qaysi sinf darsligini yuklaysiz?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("upb_"))
def handle_upb_gr(call):
    gr = call.data.replace("upb_", "")
    USER_STATES[call.from_user.id] = {"action": "adm_book_subj", "grade": gr}
    bot.send_message(call.message.chat.id, f"✍️ <b>{gr}-sinf</b> uchun fan nomini yozing (Masalan: Musiqa, Ona tili):")
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda msg: msg.text == "📚 E-kutubxona")
def handle_lib_open(message):
    markup = types.InlineKeyboardMarkup(row_width=4)
    markup.add(*[types.InlineKeyboardButton(f"{i}-sinf", callback_data=f"libg_{i}") for i in range(1, 12)])
    markup.add(types.InlineKeyboardButton("🏠 Bosh sahifa", callback_data="go_home_inline"))
    bot.send_message(message.chat.id, "📚 <b>E-Kutubxona:</b> Sinfni tanlang:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "go_to_lib_inline")
def handle_goto_lib_inline(call):
    handle_lib_open(call.message)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("libg_"))
def handle_lib_gr_open(call):
    gr = call.data.replace("libg_", "")
    data = load_json_data(LIBRARY_FILE, {})
    books = data.get(gr, {})
    subjs = sorted(list(set(["Musiqa", "Matematika", "Ona tili", "Adabiyot", "Informatika", "Fizika"] + list(books.keys()))))
    markup = types.InlineKeyboardMarkup(row_width=2)
    for s in subjs:
        icon = "📕" if s in books else "📖"
        markup.add(types.InlineKeyboardButton(f"{icon} {s}", callback_data=f"libsel_{gr}_{s}"))
    markup.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data="go_home_inline"))
    bot.edit_message_text(f"📚 <b>{gr}-sinf darsliklari:</b>", call.message.chat.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("libsel_"))
def handle_lib_sel(call):
    p = call.data.split("_")
    gr, subj = p[1], p[2]
    markup = types.InlineKeyboardMarkup(row_width=1)
    data = load_json_data(LIBRARY_FILE, {})
    if gr in data and subj in data[gr]:
        markup.add(types.InlineKeyboardButton("📥 Kitobni yuklab olish (PDF)", callback_data=f"downpdf_{gr}_{subj}"))
    markup.add(types.InlineKeyboardButton("📖 Dars matnini o‘qish", callback_data=f"readlesson_{gr}_{subj}"))
    markup.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data=f"libg_{gr}"))
    bot.send_message(call.message.chat.id, f"📖 <b>{gr}-sinf | {subj} darsligi:</b>", reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("downpdf_"))
def handle_down_pdf(call):
    p = call.data.split("_")
    gr, subj = p[1], p[2]
    book = load_json_data(LIBRARY_FILE, {}).get(gr, {}).get(subj)
    if book and book.get("file_id"):
        bot.send_document(call.message.chat.id, book["file_id"], caption=f"📕 {gr}-sinf {subj} darsligi")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("readlesson_"))
def handle_readlesson_call(call):
    p = call.data.split("_")
    USER_STATES[call.from_user.id] = {"action": "lib_reading_lesson", "grade": p[1], "subj": p[2]}
    bot.send_message(call.message.chat.id, f"📖 <b>{p[1]}-sinf {p[2]}</b>: qaysi dars kerak? Masalan: <code>7-dars</code> deb yozing:")
    bot.answer_callback_query(call.id)

# ==================== METODIK AI YORDAMCHI (TUZATILGAN) ====================

@bot.message_handler(func=lambda msg: msg.text in ["💡 Metodik AI yordamchi", "💡 Savol-javob (AI)"])
def handle_ai_prompt(message):
    USER_STATES[message.from_user.id] = {"action": "ai_query"}
    bot.send_message(
        message.chat.id,
        "💡 <b>Ustoz AI — Aqlli pedagogik yordamchi faol!</b>\n\n"
        "Fanni va dars mavzusini yozing. Masalan:\n"
        "• <i>«7-sinf Fizika: Bosim mavzusida qiziqarli dars ishlanmasi tuzib ber»</i>\n"
        "• <i>«5-sinf Musiqa: 5 talik test savollari tuzib ber»</i>\n\n"
        "Savolingizni yozib yuboring (Bekor qilish uchun: /cancel):"
    )

@bot.message_handler(commands=['cancel'])
def handle_cancel_cmd(message):
    if message.from_user.id in USER_STATES:
        del USER_STATES[message.from_user.id]
    bot.send_message(message.chat.id, "Amal bekor qilindi.")

# ==================== MATN KELGANDA ISHLASH (FSM) ====================

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    user = database.get_user(message.from_user.id)
    if not user or user.get("role") != "admin":
        return
    doc = message.document
    uid = message.from_user.id
    
    if uid in USER_STATES and USER_STATES[uid].get("action") == "adm_waiting_pdf":
        st = USER_STATES[uid]
        gr, subj = st["grade"], st["subj"]
        data = load_json_data(LIBRARY_FILE, {})
        if gr not in data:
            data[gr] = {}
        data[gr][subj] = {"file_id": doc.file_id, "file_name": doc.file_name}
        save_json_data(LIBRARY_FILE, data)
        del USER_STATES[uid]
        bot.send_message(message.chat.id, f"✅ <b>{gr}-sinf {subj} darsligi saqlandi!</b>")
        return

    if doc.file_name.endswith(('.xlsx', '.xls')):
        f_info = bot.get_file(doc.file_id)
        d_file = bot.download_file(f_info.file_path)
        s_path = os.path.join(os.path.dirname(__file__), "uploaded_schedule.xlsx")
        with open(s_path, 'wb') as f:
            f.write(d_file)
        bot.send_message(message.chat.id, f"✅ Excel dars jadvali yangilandi!")

@bot.message_handler(func=lambda msg: msg.from_user.id in USER_STATES)
def handle_all_states(message):
    uid = message.from_user.id
    st = USER_STATES[uid]
    act = st.get("action")
    
    # Farzand ismini qabul qilish
    if act == "fam_wait_name":
        c_name = message.text.strip().capitalize()
        c_cls = st["class"]
        del USER_STATES[uid]
        f_data = load_json_data(FAMILY_FILE, {})
        if str(uid) not in f_data:
            f_data[str(uid)] = {"children": [], "confirmed": False}
        f_data[str(uid)]["children"].append({
            "name": c_name, "class": c_cls, 
            "tanga": 0, "yulduz": 0, "brilliant": 0,
            "played_seconds": 0, "last_played_date": ""
        })
        save_json_data(FAMILY_FILE, f_data)
        text, markup = render_family_card(uid)
        bot.send_message(message.chat.id, f"✅ <b>{c_name} ({c_cls})</b> qo‘shildi!\n\n" + text, reply_markup=markup, parse_mode="HTML")
        return

    # PDF darslik fani
    if act == "adm_book_subj":
        gr = st["grade"]
        subj = message.text.strip().capitalize()
        USER_STATES[uid] = {"action": "adm_waiting_pdf", "grade": gr, "subj": subj}
        bot.send_message(message.chat.id, f"📥 <b>{gr}-sinf {subj}</b> tanlandi. PDF faylni Telegramga yuboring:")
        return

    # Dars matnini o'qish (AI)
    if act == "lib_reading_lesson":
        gr, subj = st["grade"], st["subj"]
        q = message.text.strip()
        del USER_STATES[uid]
        bot.send_chat_action(message.chat.id, 'typing')
        prompt = f"Sen {gr}-sinf {subj} darslik muallifisan. '{q}' mavzusi bo'yicha to'liq, aniq, katta harflar va qoidalar bilan dars matni tuzib ber."
        ans, err = generate_ai_response(prompt)
        header = f"━━━━━━━━━━━━━━━━━━━━\n📖 *{gr.upper()}-SINF | {subj.upper()} DARSLIGI*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        if ans:
            safe_send_markdown(message.chat.id, header + ans, message.message_id)
        else:
            bot.reply_to(message, f"Xatolik: {err}")
        return

    # Metodik AI yordamchi savoli
    if act == "ai_query":
        del USER_STATES[uid]
        bot.send_chat_action(message.chat.id, 'typing')
        prompt = (
            "Sen O'zbekistondagi 80-umumiy o'rta ta'lim maktabining aqlli pedagogik AI yordamchisisan. "
            "O'qituvchilar, o'quvchilar va ota-onalarning savollariga o'zbek tilida, muloyim, aniq va professional darajada javob ber.\n\n"
            f"Savol: {message.text}"
        )
        answer, err = generate_ai_response(prompt)
        if answer:
            safe_send_markdown(message.chat.id, answer, message.message_id)
        else:
            bot.reply_to(message, f"⚠️ AI javob berishda xatolik: {err}")
        return

    # Fikr va takliflar
    if act == "send_feedback":
        del USER_STATES[uid]
        user = database.get_user(uid)
        name = user["full_name"] if user else message.from_user.first_name
        notice = f"📩 <b>YANGI MUROJAAT:</b>\n\n👤 Yuboruvchi: <b>{name}</b>\n💬 Matn:\n{message.text}"
        for a in database.get_all_admins():
            try:
                bot.send_message(a, notice)
            except Exception:
                pass
        bot.send_message(message.chat.id, "✅ Murojaatingiz ma'muriyatga yetkazildi.")
        return

# ==================== DARS JADVALLARI VA FARZANDLAR ====================

@bot.message_handler(func=lambda msg: msg.text in ["📅 Dars jadvalim", "📅 Mening darslarim"])
def handle_teacher_schedule(message):
    user = database.get_user(message.from_user.id)
    t_name = user["teacher_name"] if user else "Boboev J"
    now_day = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Dushanba"][datetime.now(UZ_TZ).weekday()]
    
    t = database.get_teacher_schedule(t_name)
    if not t:
        bot.send_message(message.chat.id, "Jadval topilmadi.")
        return
        
    z_data = load_json_data(ZVONOK_FILE, DEFAULT_BELL_SCHEDULE)
    rejim = "☀️ Yozgi rejim" if z_data.get("rejim") == "yozgi" else "❄️ Qishki rejim"
    
    text = f"📅 <b>{now_day.upper()} — DARS JADVALI:</b>\n👤 <b>Ustoz:</b> {t['name']}\n📌 <i>{rejim}</i>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    s_list = []
    for p in range(1, 7):
        e = t.get("schedule", {}).get(now_day, {}).get(str(p), [])
        if e:
            s_list.append(f"• <b>{p}-dars</b> (<code>{get_bell_time(1, p)}</code>): {', '.join([x['class'] for x in e])}")
    text += "\n".join(s_list) if s_list else "<i>Bugun darslaringiz yo‘q.</i>"
    
    tg_data = load_json_data(TOGARAK_FILE, {}).get(t_name)
    if tg_data and tg_data.get("fan") and tg_data.get("kun") == now_day:
        text += f"\n\n🎪 <b>Bugungi to‘garak:</b> {tg_data.get('fan')} ({tg_data.get('nomi', '-')}) | <code>{tg_data.get('vaqt', '-')}</code>"
        
    bot.send_message(message.chat.id, text, parse_mode="HTML")

@bot.message_handler(func=lambda msg: msg.text == "🎒 Farzandlarim darslari")
def handle_children_lessons(message):
    uid_str = str(message.from_user.id)
    f_data = load_json_data(FAMILY_FILE, {})
    children = f_data.get(uid_str, {}).get("children", [])
    if not children:
        bot.send_message(message.chat.id, "Siz hali birorta ham farzand qo‘shmadingiz.")
        return
        
    now_day = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Dushanba"][datetime.now(UZ_TZ).weekday()]
    z_data = load_json_data(ZVONOK_FILE, DEFAULT_BELL_SCHEDULE)
    rejim = "☀️ Yozgi rejim" if z_data.get("rejim") == "yozgi" else "❄️ Qishki rejim"
    
    text = f"🎒 <b>FARZANDLARINGIZ DARSLARI ({now_day.upper()}):</b>\n📌 <i>{rejim}</i>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    teachers = database.get_teachers_list()
    for ch in children:
        text += f"👤 <b>{ch['name']} ({ch['class']} sinf):</b>\n"
        lines = []
        for p in range(1, 7):
            for t in teachers:
                for e in t.get("schedule", {}).get(now_day, {}).get(str(p), []):
                    if e.get("class", "").strip().upper() == ch['class'].strip().upper():
                        lines.append(f"  • {p}-dars ({get_bell_time(1, p)}): <b>{e.get('subject', 'Dars')}</b> ({t['name']})")
                        break
        text += ("\n".join(lines) if lines else "  <i>Bugun darslar yo‘q.</i>") + "\n\n"
    bot.send_message(message.chat.id, text, parse_mode="HTML")

# ==================== 🔄 YANGILASH VA ESLATMALAR ====================

@bot.message_handler(func=lambda msg: "yangilash" in msg.text.lower())
def handle_universal_refresh(message):
    bot.send_chat_action(message.chat.id, 'typing')
    database.update_activity(message.from_user.id)
    z_data = load_json_data(ZVONOK_FILE, DEFAULT_BELL_SCHEDULE)
    faol = "☀️ Yozgi rejim" if z_data.get("rejim") == "yozgi" else "❄️ Qishki rejim"
    c_time = datetime.now(UZ_TZ).strftime("%H:%M:%S")
    bot.reply_to(message, f"✅ <b>Tizim muvaffaqiyatli yangilandi!</b>\n\n🕒 Vaqt: <b>{c_time}</b>\n📌 Qo‘ng‘iroqlar: <b>{faol}</b>\n⚡ Dars jadvallari, o‘yin hisobi va kutubxona eng oxirgi holatda.", parse_mode="HTML")

def send_paced_reminders(is_morning=False):
    now = datetime.now(UZ_TZ)
    DAYS_MAP = {0: "Dushanba", 1: "Seshanba", 2: "Chorshanba", 3: "Payshanba", 4: "Juma", 5: "Shanba", 6: "Yakshanba"}
    NEXT_DAY = {"Dushanba": "Seshanba", "Seshanba": "Chorshanba", "Chorshanba": "Payshanba", "Payshanba": "Juma", "Juma": "Shanba", "Shanba": "Dushanba", "Yakshanba": "Dushanba"}
    
    target_day = DAYS_MAP.get(now.weekday(), "Dushanba") if is_morning else NEXT_DAY.get(DAYS_MAP.get(now.weekday(), "Dushanba"), "Dushanba")
    z_data = load_json_data(ZVONOK_FILE, DEFAULT_BELL_SCHEDULE)
    rejim = "☀️ Yozgi rejim" if z_data.get("rejim") == "yozgi" else "❄️ Qishki rejim"
    salom = "Xayrli tong" if is_morning else "Xayrli kech"

    f_data = load_json_data(FAMILY_FILE, {})
    processed_uids = set()

    for u in database.get_all_connected_users():
        uid_str = str(u["telegram_id"])
        processed_uids.add(uid_str)
        t_name = u.get("teacher_name", "")
        
        msg = f"🔔🔔🔔\n<b>80-Maktab dars jadvali eslatma</b>\n\nUstoz {u['full_name']}, {salom}!\nRejim: <b>{rejim}</b>\n\n"
        t = database.get_teacher_schedule(t_name)
        if t:
            s_list = [f"• {p}-dars ({get_bell_time(1, p)}): {', '.join([x['class'] for x in t.get('schedule',{}).get(target_day,{}).get(str(p),[])])}" for p in range(1, 7) if t.get('schedule',{}).get(target_day,{}).get(str(p))]
            msg += "\n".join(s_list) if s_list else "Darslar yo‘q."
            
        if uid_str in f_data and f_data[uid_str].get("children"):
            msg += "\n\n👨‍👩‍👧 <b>Farzandlaringiz darslari:</b>\n"
            teachers = database.get_teachers_list()
            for ch in f_data[uid_str]["children"]:
                msg += f"\n👤 <b>{ch['name']} ({ch['class']}):</b>\n"
                lines = []
                for p in range(1, 7):
                    for tc in teachers:
                        for e in tc.get("schedule", {}).get(target_day, {}).get(str(p), []):
                            if e.get("class", "").strip().upper() == ch['class'].strip().upper():
                                lines.append(f"  • {p}-dars ({get_bell_time(1, p)}): {e.get('subject', 'Dars')} ({tc['name']})")
                                break
                msg += "\n".join(lines) if lines else "  <i>Dars yo‘q.</i>"
                
        try:
            bot.send_message(u["telegram_id"], msg)
        except Exception:
            pass
        time.sleep(0.08)

    for uid_str, u_info in f_data.items():
        if uid_str in processed_uids or not u_info.get("confirmed"):
            continue
        msg = f"🔔🔔🔔\n<b>80-Maktab dars jadvali eslatma</b>\n\nAssalomu alaykum!\nFarzandlaringiz dars jadvali ({rejim}):\n\n"
        teachers = database.get_teachers_list()
        for ch in u_info.get("children", []):
            msg += f"👤 <b>{ch['name']} ({ch['class']} sinf):</b>\n"
            lines = []
            for p in range(1, 7):
                for tc in teachers:
                    for e in tc.get("schedule", {}).get(target_day, {}).get(str(p), []):
                        if e.get("class", "").strip().upper() == ch['class'].strip().upper():
                            lines.append(f"  • {p}-dars ({get_bell_time(1, p)}): {e.get('subject', 'Dars')} ({tc['name']})")
                            break
            msg += ("\n".join(lines) if lines else "  <i>Dars yo‘q.</i>") + "\n\n"
        try:
            bot.send_message(int(uid_str), msg)
        except Exception:
            pass
        time.sleep(0.08)

def reminder_scheduler():
    s_m, s_e = "", ""
    while True:
        try:
            now = datetime.now(UZ_TZ)
            t_str = now.strftime("%Y-%m-%d")
            if now.hour == 7 and 0 <= now.minute < 5 and s_m != t_str:
                send_paced_reminders(is_morning=True)
                s_m = t_str
            if now.hour == 19 and 30 <= now.minute < 35 and s_e != t_str:
                send_paced_reminders(is_morning=False)
                s_e = t_str
        except Exception:
            pass
        time.sleep(30)

# --- UMUMIY ERKIN MATNLARGA AI JAVOBI ---
@bot.message_handler(func=lambda msg: True)
def handle_general_ai(message):
    bot.send_chat_action(message.chat.id, 'typing')
    prompt = (
        "Sen 80-maktab 'Ustoz AI' aqlli yordamchisisan. "
        "Muloyim, aniq va samimiy javob ber:\n\n"
        f"Savol: {message.text}"
    )
    ans, err = generate_ai_response(prompt)
    if ans:
        safe_send_markdown(message.chat.id, ans, message.message_id)
    else:
        bot.reply_to(message, f"⚠️ Xatolik: {err}\nMenyudan foydalanishingiz mumkin.")

# ==================== ISHGA TUSHIRISH ====================

if __name__ == "__main__":
    try:
        bot.remove_webhook()
    except Exception:
        pass
    Thread(target=run_web, daemon=True).start()
    Thread(target=reminder_scheduler, daemon=True).start()
    print("80-maktab 'Ustoz AI' to'liq boshqaruv tizimi ishga tushdi...")
    bot.infinity_polling(skip_pending=True)
