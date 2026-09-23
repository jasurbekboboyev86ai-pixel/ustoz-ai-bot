# -*- coding: utf-8 -*-
"""
80-maktab "Ustoz AI" Telegram Boti - To'liq va Mukammal Birlashtirilgan Versiya
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

# --- GEMINI AI ISHONCHLI ULASH TIZIMI ---
GEMINI_KEY = (
    os.environ.get("GEMINI_API_KEY") 
    or os.environ.get("GEMINI_KEY") 
    or os.environ.get("GOOGLE_API_KEY") 
    or getattr(config, "GEMINI_API_KEY", "")
)

def generate_ai_response(prompt_text):
    if not GEMINI_KEY:
        return None, "API kalit (GEMINI_API_KEY) topilmadi. Render sozlamalarini tekshiring."
    
    try:
        genai.configure(api_key=GEMINI_KEY)
    except Exception as e:
        return None, f"Sozlash xatosi: {e}"

    models_to_try = [
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-1.5-pro",
        "gemini-pro"
    ]
    
    errors = []
    for mod_name in models_to_try:
        try:
            m = genai.GenerativeModel(mod_name)
            res = m.generate_content(prompt_text)
            if res:
                text = ""
                try:
                    text = res.text
                except Exception:
                    if res.candidates and res.candidates[0].content.parts:
                        text = res.candidates[0].content.parts[0].text
                if text and text.strip():
                    return text.strip(), None
        except Exception as err:
            errors.append(f"{mod_name}: {err}")
            continue

    err_msg = errors[0] if errors else "AI javob qaytara olmadi"
    return None, err_msg

# Telegram bot sozlamasi
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or config.BOT_TOKEN
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

USER_STATES = {}
UZ_TZ = timezone(timedelta(hours=5))
MAX_DAILY_GAME_SECONDS = 22 * 60  # Kuniga 22 daqiqa o'yin vaqti

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

def send_long_ai_message(chat_id, text, reply_to_id=None):
    """Uzun AI matnlarini (4000 belgidan katta) xatosiz yetkazuvchi himoya"""
    chunks = []
    while len(text) > 3900:
        split_idx = text.rfind("\n", 0, 3900)
        if split_idx == -1:
            split_idx = 3900
        chunks.append(text[:split_idx])
        text = text[split_idx:].lstrip()
    if text:
        chunks.append(text)
    
    for idx, chunk in enumerate(chunks):
        rep = reply_to_id if idx == 0 else None
        try:
            bot.send_message(chat_id, chunk, parse_mode="Markdown", reply_to_message_id=rep)
        except Exception:
            clean = chunk.replace("*", "").replace("_", "").replace("`", "").replace("#", "")
            bot.send_message(chat_id, clean, parse_mode=None, reply_to_message_id=rep)

# ==================== O'QITUVCHILAR RO'YXATI SAHIFALARI ====================

def get_teachers_page_inline(page=0, per_page=8):
    teachers = database.get_teachers_list()
    total = len(teachers)
    start = page * per_page
    end = min(start + per_page, total)
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    for t in teachers[start:end]:
        name = t["name"]
        subj = t["subjects"][0] if (t.get("subjects") and t["subjects"]) else "Fan"
        markup.add(types.InlineKeyboardButton(f"👤 {name} ({subj})", callback_data=f"selteach_{name}"))
        
    nav = []
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page > 0:
        nav.append(types.InlineKeyboardButton("⬅️ Oldingi", callback_data=f"tpage_{page-1}"))
    nav.append(types.InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="ignore_click"))
    if end < total:
        nav.append(types.InlineKeyboardButton("Keyingi ➡️", callback_data=f"tpage_{page+1}"))
        
    if nav:
        markup.row(*nav)
    markup.add(types.InlineKeyboardButton("❌ Bekor qilish", callback_data="go_home_inline"))
    return markup

@bot.callback_query_handler(func=lambda call: call.data == "ignore_click")
def handle_ignore_click(call):
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("tpage_"))
def handle_teacher_pagination(call):
    page = int(call.data.split("_")[1])
    try:
        bot.edit_message_reply_markup(
            call.message.chat.id, 
            call.message.message_id, 
            reply_markup=get_teachers_page_inline(page=page)
        )
    except Exception:
        pass
    bot.answer_callback_query(call.id)

# ==================== SINF JADVALLARI BO'YICHA YORDAMCHILAR ====================

def get_all_school_classes():
    teachers = database.get_teachers_list()
    classes = set()
    for t in teachers:
        for d, slots in t.get("schedule", {}).items():
            for slot, entries in slots.items():
                for e in entries:
                    c = e.get("class", "").strip().upper()
                    if c:
                        classes.add(c)
    def sort_key(c):
        num = re.findall(r'\d+', c)
        let = re.findall(r'[A-Za-z]+', c)
        return (int(num[0]) if num else 0, let[0] if let else "")
    return sorted(list(classes), key=sort_key)

def get_grade_parallels_keyboard(sub_mode=False):
    prefix = "subgrd_" if sub_mode else "grdpar_"
    markup = types.InlineKeyboardMarkup(row_width=4)
    btns = [types.InlineKeyboardButton(f"{i}-sinflar", callback_data=f"{prefix}{i}") for i in range(1, 12)]
    markup.add(*btns)
    markup.add(types.InlineKeyboardButton("🏠 Bosh sahifaga qaytish", callback_data="go_home_inline"))
    return markup

def get_classes_in_grade_keyboard(grade_num, sub_mode=False, user_subs=[]):
    all_cls = get_all_school_classes()
    matched = [c for c in all_cls if c.startswith(str(grade_num)) and (len(c) == len(str(grade_num)) + 1 or c[len(str(grade_num))].isalpha())]
    markup = types.InlineKeyboardMarkup(row_width=3)
    btns = []
    for c in matched:
        if sub_mode:
            icon = "✅" if c in user_subs else "➕"
            btns.append(types.InlineKeyboardButton(f"{icon} {c}", callback_data=f"togglesub_{c}_{grade_num}"))
        else:
            btns.append(types.InlineKeyboardButton(f"🏫 {c}", callback_data=f"selcls_{c}"))
    markup.add(*btns)
    back_target = "subgrd_back" if sub_mode else "grdpar_back"
    markup.add(types.InlineKeyboardButton("⬅️ Boshqa sinflar", callback_data=back_target))
    return markup

def get_class_days_keyboard(class_name):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [types.InlineKeyboardButton(f"📅 {d}", callback_data=f"clday_{class_name}_{d}") for d in config.DAYS]
    markup.add(*btns)
    markup.add(types.InlineKeyboardButton("🗓️ Butun haftalik jadval", callback_data=f"clday_{class_name}_ALL"))
    m = re.findall(r'\d+', class_name)
    gr = m[0] if m else "1"
    markup.add(types.InlineKeyboardButton("⬅️ Sinfni o'zgartirish", callback_data=f"grdpar_{gr}"))
    return markup

def get_class_day_schedule(class_name, day):
    teachers = database.get_teachers_list()
    slots_data = {}
    for t in teachers:
        t_sched = t.get("schedule", {}).get(day, {})
        for slot_str, entries in t_sched.items():
            try:
                slot_num = int(slot_str)
            except ValueError:
                continue
            for e in entries:
                if e.get("class", "").strip().upper() == class_name.upper():
                    subj = e.get("subject") or (t["subjects"][0] if t["subjects"] else "Dars")
                    if slot_num not in slots_data:
                        slots_data[slot_num] = []
                    slots_data[slot_num].append({
                        "teacher": t["name"],
                        "subject": subj
                    })
    return slots_data

def format_class_day_schedule(class_name, day):
    slots_data = get_class_day_schedule(class_name, day)
    z_data = load_json_data(ZVONOK_FILE, DEFAULT_BELL_SCHEDULE)
    rejim = z_data.get("rejim", "yozgi")
    rejim_nomi = "☀️ Yozgi rejim" if rejim == "yozgi" else "❄️ Qishki rejim"

    text = f"🎒 <b>{class_name.upper()} SINF — {day.upper()} KUNI:</b>\n"
    text += f"📌 <i>Dars vaqtlari: {rejim_nomi}</i>\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n"
    
    s1_lines = []
    for p in range(1, 7):
        if p in slots_data:
            for item in slots_data[p]:
                t_str = get_bell_time(1, p)
                s1_lines.append(f"• <b>{p}-dars</b> (<code>{t_str}</code>): <b>{item['subject']}</b>\n   └ <i>Ustoz: {item['teacher']}</i>")
                
    s2_lines = []
    for p in range(1, 7):
        slot = p + 6
        if slot in slots_data:
            for item in slots_data[slot]:
                t_str = get_bell_time(2, p)
                s2_lines.append(f"• <b>{p}-dars</b> (<code>{t_str}</code>): <b>{item['subject']}</b>\n   └ <i>Ustoz: {item['teacher']}</i>")
                
    if s1_lines:
        text += "🔵 <b>I - SMENA:</b>\n" + "\n".join(s1_lines) + "\n\n"
    if s2_lines:
        text += "🟢 <b>II - SMENA:</b>\n" + "\n".join(s2_lines) + "\n\n"
    if not s1_lines and not s2_lines:
        text += "<i>Bugun darslar mavjud emas yoki dam olish kuni.</i>\n"
    text += "━━━━━━━━━━━━━━━━━━━━"
    return text

def format_class_week_schedule(class_name):
    text = f"🗓️ <b>{class_name.upper()} SINF — TO'LIQ HAFTALIK JADVAL</b>\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    for d in config.DAYS:
        slots_data = get_class_day_schedule(class_name, d)
        day_lines = []
        for p in range(1, 7):
            if p in slots_data:
                for item in slots_data[p]:
                    day_lines.append(f"{p}-dars: {item['subject']} ({item['teacher']})")
        for p in range(1, 7):
            slot = p + 6
            if slot in slots_data:
                for item in slots_data[slot]:
                    day_lines.append(f"{p}-dars: {item['subject']} ({item['teacher']}) [2-sm]")
        text += f"📅 <b>{d}:</b>\n"
        if day_lines:
            for l in day_lines:
                text += f"   • {l}\n"
        else:
            text += "   <i>Dars yo'q</i>\n"
        text += "\n"
    text += "━━━━━━━━━━━━━━━━━━━━"
    return text

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

    if tanga >= 10:
        new_stars = tanga // 10
        yulduz += new_stars
        tanga = tanga % 10
        notice += f"\n🌟 <b>Qoyilmaqom!</b> 10 ta tangangiz <b>+{new_stars} ta ⭐ Oltin Yulduzcha</b>ga aylandi!"

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

# ==================== INTERAKTIV TO'GARAK TIZIMI ====================

def render_togarak_card(teacher_key):
    data = load_json_data(TOGARAK_FILE, {})
    u_data = data.get(teacher_key, {})
    
    fan = u_data.get("fan", "Kiritilmagan")
    nomi = u_data.get("nomi", "Kiritilmagan")
    kun = u_data.get("kun", "Tanlanmagan")
    vaqt = u_data.get("vaqt", "Belgilanmagan")
    
    matn = (
        f"🎨 <b>To‘garak mashg‘uloti sozlamalari:</b>\n\n"
        f"1. 📚 <b>Fan nomi:</b> {fan}\n"
        f"2. 🏷 <b>To‘garak nomi:</b> {nomi}\n"
        f"3. 📅 <b>Hafta kuni:</b> {kun}\n"
        f"4. ⏰ <b>Mashg‘ulot soati:</b> {vaqt}\n\n"
        f"<i>Kiritish yoki o‘zgartirish uchun kerakli tugmani tanlang:</i>"
    )
    markup = types.InlineKeyboardMarkup(row_width=2)
    b1 = types.InlineKeyboardButton("1. 📚 Fan nomi", callback_data="tog_btn_fan")
    b2 = types.InlineKeyboardButton("2. 🏷 To'garak nomi", callback_data="tog_btn_nomi")
    b3 = types.InlineKeyboardButton("3. 📅 Kun tanlash", callback_data="tog_btn_kun")
    b4 = types.InlineKeyboardButton("4. ⏰ Soat tanlash", callback_data="tog_btn_vaqt")
    markup.add(b1, b2)
    markup.add(b3, b4)
    markup.add(types.InlineKeyboardButton("🏠 Bosh sahifaga qaytish", callback_data="go_home_inline"))
    return matn, markup

@bot.message_handler(func=lambda msg: msg.text in ["🎨 To'garaklarim", "🎪 To‘garak", "🎪 Maktab to‘garaklari"])
def handle_teacher_clubs_interactive(message):
    uid = message.from_user.id
    user = database.get_user(uid)
    teacher_key = user["teacher_name"] if (user and user.get("teacher_name")) else str(uid)
    matn, markup = render_togarak_card(teacher_key)
    bot.send_message(message.chat.id, matn, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("tog_btn_"))
def process_togarak_buttons(call):
    uid = call.from_user.id
    user = database.get_user(uid)
    teacher_key = user["teacher_name"] if (user and user.get("teacher_name")) else str(uid)
    action = call.data
    
    if action == "tog_btn_fan":
        USER_STATES[uid] = {"action": "input_tog_fan", "tkey": teacher_key}
        bot.send_message(call.message.chat.id, "1️⃣ <b>Fan nomini</b> yozing va yuboring:\n<i>(Masalan: Informatika, Fizika, Musiqa)</i>", parse_mode="HTML")
    elif action == "tog_btn_nomi":
        USER_STATES[uid] = {"action": "input_tog_nomi", "tkey": teacher_key}
        bot.send_message(call.message.chat.id, "2️⃣ <b>To‘garak nomini</b> yozing va yuboring:\n<i>(Masalan: Yosh dasturchi, Mohir qo'llar)</i>", parse_mode="HTML")
    elif action == "tog_btn_kun":
        markup = types.InlineKeyboardMarkup(row_width=2)
        kunlar = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"]
        markup.add(*[types.InlineKeyboardButton(f"📅 {k}", callback_data=f"settogkun_{k}") for k in kunlar])
        bot.send_message(call.message.chat.id, "3️⃣ To‘garak o‘tiladigan hafta kunini tanlang:", reply_markup=markup)
    elif action == "tog_btn_vaqt":
        USER_STATES[uid] = {"action": "input_tog_vaqt", "tkey": teacher_key}
        bot.send_message(call.message.chat.id, "4️⃣ To‘garak boshlanish vaqtini yozing (Masalan: <code>11:30</code> yoki <code>14:00</code>):", parse_mode="HTML")
        
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("settogkun_"))
def save_togarak_selected_day(call):
    uid = call.from_user.id
    user = database.get_user(uid)
    teacher_key = user["teacher_name"] if (user and user.get("teacher_name")) else str(uid)
    
    kun = call.data.replace("settogkun_", "")
    data = load_json_data(TOGARAK_FILE, {})
    if teacher_key not in data:
        data[teacher_key] = {}
    data[teacher_key]["kun"] = kun
    save_json_data(TOGARAK_FILE, data)
    
    bot.answer_callback_query(call.id, f"{kun} saqlandi ✅")
    matn, markup = render_togarak_card(teacher_key)
    bot.send_message(call.message.chat.id, f"✅ <b>Hafta kuni saqlandi!</b>\n\n" + matn, reply_markup=markup, parse_mode="HTML")

# ==================== TUGMALAR VA MENYULAR ====================

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
    b13 = types.KeyboardButton("⏰ Haftalik yuklamam")
    b14 = types.KeyboardButton("🎒 Sinf jadvali")
    b15 = types.KeyboardButton("💡 Metodik AI yordamchi")
    b16 = types.KeyboardButton("🔄 Yangilash")
    b17 = types.KeyboardButton("🏠 Bosh sahifa")
    
    markup.add(b1, b2)
    markup.add(b3, b4)
    markup.add(b5, b6)
    markup.add(b7, b8)
    markup.add(b9, b10)
    markup.add(b11)
    markup.add(b12, b13)
    markup.add(b14, b15)
    markup.add(b16, b17)
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
    b6 = types.KeyboardButton("🎒 Sinf jadvali")
    b7 = types.KeyboardButton("💡 Metodik AI yordamchi")
    b8 = types.KeyboardButton("🔄 Yangilash")
    b9 = types.KeyboardButton("✍️ Taklif bildirish")
    b10 = types.KeyboardButton("🏠 Bosh sahifa")
    markup.add(b1, b2)
    markup.add(b3, b4)
    markup.add(b5, b6)
    markup.add(b7, b8)
    markup.add(b9, b10)
    return markup

def get_days_inline_keyboard(prefix="day_view"):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [types.InlineKeyboardButton(f"📅 {d}", callback_data=f"{prefix}_{d}") for d in config.DAYS]
    markup.add(*btns)
    if prefix == "day_view":
        markup.add(types.InlineKeyboardButton("🗓️ Butun haftalik jadval", callback_data=f"{prefix}_ALL"))
    markup.add(types.InlineKeyboardButton("🏠 Bosh sahifaga qaytish", callback_data="go_home_inline"))
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
    
    if user and user.get("role") == "admin":
        bot.send_message(
            message.chat.id,
            f"👑 <b>Assalomu alaykum, Bosh Admin {user['full_name']}!</b>\n"
            f"80-Maktab boshqaruv markazidasiz. Barcha tizimlar to‘liq nazoratingizda.",
            reply_markup=get_admin_keyboard()
        )
        return
        
    if user and user.get("role") == "teacher":
        bot.send_message(
            message.chat.id,
            f"👨‍🏫 <b>Assalomu alaykum, {user['teacher_name']}!</b>\n"
            f"80-maktab 'Ustoz AI' shaxsiy kabinetingizdasiz.",
            reply_markup=get_teacher_keyboard()
        )
        return

    f_data = load_json_data(FAMILY_FILE, {})
    if str(uid) in f_data and f_data[str(uid)].get("confirmed"):
        bot.send_message(
            message.chat.id,
            f"🎒 <b>Assalomu alaykum!</b>\n80-Maktab ta’lim va Zukko O‘yinlar portaliga xush kelibsiz.",
            reply_markup=get_student_parent_keyboard()
        )
        return

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

# ==================== O'QITUVCHILAR ULANISHI ====================

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
    bot.send_message(
        message.chat.id, 
        f"📱 Raqamingiz: <code>{phone}</code>\n\nQuyidagi ro‘yxatdan <b>o‘z ism-familiyangizni tanlang</b>:", 
        reply_markup=get_teachers_page_inline(page=0)
    )

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

@bot.callback_query_handler(func=lambda call: call.data.startswith("rejreq_"))
def handle_admin_rej(call):
    req_id = int(call.data.split("_")[1])
    database.reject_request(req_id)
    bot.edit_message_text("❌ So‘rov rad etildi.", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)

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

# ==================== 🎮 ZUKKO O'YINLAR ====================

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

# ==================== SINF DARS JADVALLARI MENYUSI ====================

@bot.message_handler(func=lambda msg: msg.text in ["🎒 Sinf jadvali", "🎒 Sinf dars jadvallari"])
def handle_view_class_schedule(message):
    database.update_activity(message.from_user.id)
    bot.send_message(
        message.chat.id,
        "🎒 <b>Qaysi sinf dars jadvali kerak?</b>\nKerakli parallel sinfni tanlang:",
        reply_markup=get_grade_parallels_keyboard(sub_mode=False)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("grdpar_"))
def handle_class_parallel_click(call):
    val = call.data.replace("grdpar_", "")
    if val == "back":
        bot.edit_message_text("🎒 <b>Kerakli parallel sinfni tanlang:</b>", call.message.chat.id, call.message.message_id, reply_markup=get_grade_parallels_keyboard(False))
    else:
        bot.edit_message_text(f"🏫 <b>{val}-sinflar:</b>\nSinfni tanlang:", call.message.chat.id, call.message.message_id, reply_markup=get_classes_in_grade_keyboard(val, False))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("selcls_"))
def handle_class_selected_view(call):
    cls = call.data.replace("selcls_", "")
    bot.edit_message_text(f"📅 <b>{cls} sinf</b> uchun qaysi kungi jadval kerak?", call.message.chat.id, call.message.message_id, reply_markup=get_class_days_keyboard(cls))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("clday_"))
def handle_class_day_schedule_show(call):
    parts = call.data.split("_")
    cls, day = parts[1], parts[2]
    text = format_class_week_schedule(cls) if day == "ALL" else format_class_day_schedule(cls, day)
    bot.send_message(call.message.chat.id, text, reply_markup=get_class_days_keyboard(cls))
    bot.answer_callback_query(call.id)

# ==================== O'QITUVCHI: DARS VA YUKLAMA ====================

def format_day_schedule(teacher_name, day):
    t = database.get_teacher_schedule(teacher_name)
    if not t:
        return f"❌ Jadval topilmadi."
        
    z_data = load_json_data(ZVONOK_FILE, DEFAULT_BELL_SCHEDULE)
    rejim = z_data.get("rejim", "yozgi")
    rejim_nomi = "☀️ Yozgi dars rejimi" if rejim == "yozgi" else "❄️ Qishki dars rejimi"

    sched = t["schedule"].get(day, {})
    subj_str = ", ".join(t["subjects"]) if t["subjects"] else "Fan"
    
    text = f"📅 <b>{day.upper()} — DARS JADVALI</b>\n"
    text += f"👤 <b>Ustoz:</b> {t['name']} | 📚 <b>Fan:</b> {subj_str}\n"
    text += f"📌 <i>Amaldagi tartib: {rejim_nomi}</i>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    s1 = []
    for p in range(1, 7):
        e = sched.get(p) or sched.get(str(p)) or []
        if e:
            t_str = get_bell_time(1, p)
            s1.append(f"• <b>{p}-dars</b> (<code>{t_str}</code>): <b>{', '.join([x['class'] for x in e])}</b>")
    text += "🔵 <b>I - SMENA:</b>\n" + ("\n".join(s1) if s1 else "<i>Bugun 1-smenada dars yo'q</i>") + "\n\n"
    
    s2 = []
    for p in range(1, 7):
        slot = config.SMENA2_TIMES[p]["slot"]
        t_str = get_bell_time(2, p)
        e = sched.get(slot) or sched.get(str(slot)) or []
        if e:
            s2.append(f"• <b>{p}-dars</b> (<code>{t_str}</code>): <b>{', '.join([x['class'] for x in e])}</b>")
    text += "🟢 <b>II - SMENA:</b>\n" + ("\n".join(s2) if s2 else "<i>Bugun 2-smenada dars yo'q</i>") + "\n\n"
    
    t_data = load_json_data(TOGARAK_FILE, {})
    user_tog = t_data.get(teacher_name)
    if user_tog and user_tog.get("fan") and user_tog.get("kun") == day:
        text += (
            f"🎪 <b>BUGUNGI TO‘GARAK MASHG‘ULOTI:</b>\n"
            f"• Fan: <b>{user_tog.get('fan')}</b>\n"
            f"• Nomi: <b>{user_tog.get('nomi', '-')}</b>\n"
            f"• Soati: <code>{user_tog.get('vaqt', '-')}</code>\n\n"
        )
        
    text += f"📊 <b>Bugungi jami dars: {len(s1) + len(s2)} soat</b>"
    return text

def format_week_schedule(teacher_name):
    t = database.get_teacher_schedule(teacher_name)
    if not t:
        return "❌ Jadval topilmadi."
        
    z_data = load_json_data(ZVONOK_FILE, DEFAULT_BELL_SCHEDULE)
    rejim = z_data.get("rejim", "yozgi")
    rejim_nomi = "☀️ Yozgi rejim" if rejim == "yozgi" else "❄️ Qishki rejim"

    text = f"🗓️ <b>HAFTALIK TO'LIQ DARS JADVALI</b>\n"
    text += f"👤 <b>Ustoz:</b> {t['name']} | 📌 <i>{rejim_nomi}</i>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    tot = 0
    for d in config.DAYS:
        sched = t["schedule"].get(d, {})
        dl = []
        for p in range(1, 7):
            e = sched.get(p) or sched.get(str(p)) or []
            if e:
                dl.append(f"{p}-dars: {', '.join([x['class'] for x in e])} (1-sm)")
        for p in range(1, 7):
            slot = config.SMENA2_TIMES[p]["slot"]
            e = sched.get(slot) or sched.get(str(slot)) or []
            if e:
                dl.append(f"{p}-dars: {', '.join([x['class'] for x in e])} (2-sm)")
        tot += len(dl)
        text += f"📅 <b>{d}:</b>\n" + ("\n".join([f"   • {i}" for i in dl]) if dl else "   <i>Dars yo'q</i>") + "\n\n"
        
    t_data = load_json_data(TOGARAK_FILE, {})
    user_tog = t_data.get(teacher_name)
    if user_tog and user_tog.get("fan"):
        text += (
            f"🎪 <b>Biriktirilgan To‘garak:</b>\n"
            f"• Fan: <b>{user_tog.get('fan')}</b> ({user_tog.get('nomi', '-')})\n"
            f"• Kuni: <b>{user_tog.get('kun', '-')}</b> | Vaqti: <code>{user_tog.get('vaqt', '-')}</code>\n\n"
        )
        
    text += f"━━━━━━━━━━━━━━━━━━━━\n⭐ <b>Haftalik darslar: {tot} soat</b>"
    return text

@bot.message_handler(func=lambda msg: msg.text in ["📅 Dars jadvalim", "📅 Mening darslarim"])
def handle_teacher_schedule(message):
    database.update_activity(message.from_user.id)
    user = database.get_user(message.from_user.id)
    t_name = user["teacher_name"] if user else "Boboev J"
    bot.send_message(message.chat.id, f"📅 <b>{t_name}</b>, qaysi kungi jadvalni ko'rasiz?", reply_markup=get_days_inline_keyboard("day_view"))

@bot.callback_query_handler(func=lambda call: call.data.startswith("day_view_"))
def handle_day_view(call):
    day = call.data.replace("day_view_", "")
    user = database.get_user(call.from_user.id)
    t_name = user["teacher_name"] if user else "Boboev J"
    text = format_week_schedule(t_name) if day == "ALL" else format_day_schedule(t_name, day)
    bot.send_message(call.message.chat.id, text, reply_markup=get_days_inline_keyboard("day_view"))
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda msg: msg.text == "⏰ Haftalik yuklamam")
def handle_teacher_workload(message):
    database.update_activity(message.from_user.id)
    user = database.get_user(message.from_user.id)
    t_name = user["teacher_name"] if user else "Boboev J"
    t = database.get_teacher_schedule(t_name)
    if not t:
        bot.send_message(message.chat.id, "Yuklama topilmadi.")
        return
        
    s1, s2 = 0, 0
    for d in config.DAYS:
        sc = t["schedule"].get(d, {})
        for p in range(1, 7):
            s1 += len(sc.get(p) or sc.get(str(p)) or [])
        for p in range(1, 7):
            slot = config.SMENA2_TIMES[p]["slot"]
            s2 += len(sc.get(slot) or sc.get(str(slot)) or [])
            
    t_data = load_json_data(TOGARAK_FILE, {})
    user_tog = t_data.get(t_name)
    tog_hours = 1 if (user_tog and user_tog.get("fan")) else 0
    
    text = (
        f"📊 <b>HAFTALIK YUKLAMA HISOBOTI</b>\n\n"
        f"👤 <b>Ustoz:</b> {t['name']}\n"
        f"📚 <b>Fan:</b> {', '.join(t['subjects'])}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔵 I-Smena: {s1} soat | 🟢 II-Smena: {s2} soat\n"
        f"📖 O'quv darslari: {s1+s2} soat\n"
        f"🎨 To'garak: {tog_hours} soat\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⭐ <b>JAMI YUKLAMA: {s1+s2+tog_hours} SOAT</b>"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda msg: msg.text == "✏️ Dars kunini to'g'irlash")
def handle_edit_day_prompt(message):
    user = database.get_user(message.from_user.id)
    if not user:
        return
    bot.send_message(
        message.chat.id,
        "✏️ Qaysi kungi darsingizni to'g'irlamoqchisiz?",
        reply_markup=get_days_inline_keyboard("edit_day")
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_day_"))
def handle_edit_day_callback(call):
    day = call.data.replace("edit_day_", "")
    user = database.get_user(call.from_user.id)
    if not user:
        return
    USER_STATES[call.from_user.id] = {"action": "editing_day_proc", "editing_day": day}
    msg_text = (
        f"✏️ <b>{day} kungi darsni to'g'irlash:</b>\n\n"
        f"Iltimos, dars raqami va yangi sinfni yozing.\n"
        f"<i>Masalan:</i> <code>2-dars 5A</code> yoki bo'sh qoldirish uchun: <code>2-dars -</code>"
    )
    bot.send_message(call.message.chat.id, msg_text)
    bot.answer_callback_query(call.id)

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

# ==================== ADMIN BUYRUQLARI VA HISOBOTLAR ====================

@bot.message_handler(func=lambda msg: msg.text == "👥 O'qituvchilar holati")
def handle_admin_teachers_state(message):
    admin = database.get_user(message.from_user.id)
    if not admin or admin["role"] != "admin":
        return
    users = database.get_all_connected_users()
    t_all = database.get_teachers_list()
    text = f"👥 <b>O'QITUVCHILAR ULANISH HOLATI:</b>\n\n"
    text += f"📚 Bazadagi jami o'qituvchilar: <b>{len(t_all)} nafar</b>\n"
    text += f"📱 Ulangan ustozlar: <b>{len(users)} nafar</b>\n\n"
    for idx, u in enumerate(users, 1):
        r = "👑 Admin" if u["role"] == "admin" else "👨‍🏫 O'qituvchi"
        text += f"{idx}. <b>{u['teacher_name']}</b> (<code>{u['phone']}</code>) — {r}\n"
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda msg: msg.text == "📊 Maktab umumiy hisoboti")
def handle_admin_total_report(message):
    admin = database.get_user(message.from_user.id)
    if not admin or admin["role"] != "admin":
        return
    t_all = database.get_teachers_list()
    tot_hrs = sum(t.get("total_hours", 0) for t in t_all)
    text = (
        f"📊 <b>80-MAKTAB BO'YICHA UMUMIY HISOBOT:</b>\n\n"
        f"🏫 Jami o'qituvchilar: <b>{len(t_all)} nafar</b>\n"
        f"⏱️ Jami haftalik darslar: <b>{tot_hrs} soat</b>\n"
        f"🎵 Boboev J: <b>20 soat dars + 1 soat to'garak = 21 soat</b>\n\n"
        f"✅ <i>Barcha ma'lumotlar to'liq bazada mavjud.</i>"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda msg: msg.text == "📈 Jonli statistika")
def handle_admin_stats(message):
    admin = database.get_user(message.from_user.id)
    if not admin or admin["role"] != "admin":
        return
    
    st = database.get_system_stats()
    def make_bar(val, total=100, length=10):
        pct = min(1.0, val / total) if total > 0 else 0
        filled = int(round(pct * length))
        return "█" * filled + "░" * (length - filled) + f" {int(pct*100)}%"

    top_cls_str = ""
    for idx, tc in enumerate(st.get("top_classes", []), 1):
        top_cls_str += f"   {idx}. <b>{tc['class_name']}</b> — {tc['cnt']} obunachi\n"
    if not top_cls_str:
        top_cls_str = "   <i>Hozircha obunachilar yo'q</i>\n"

    stat_text = (
        f"📊 <b>«USTOZ AI» JONLI TIZIM STATISTIKASI:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 <b>Foydalanuvchilar qatlami:</b>\n"
        f"• 👑 Adminlar: <b>{st.get('admins', 0)} nafar</b>\n"
        f"• 👨‍🏫 Ulangan o'qituvchilar: <b>{st.get('teachers', 0)} nafar</b>\n"
        f"• 🎒 O'quvchi va ota-onalar: <b>{st.get('students', 0)} nafar</b>\n"
        f"• 🌐 Jami qayd etilganlar: <b>{st.get('total_users', 0)} nafar</b>\n\n"
        f"⚡ <b>Bugungi faollik:</b>\n"
        f"<code>[{make_bar(st.get('active_today', 0), max(st.get('total_users', 1), 1))}]</code>\n"
        f"Bugun botdan foydalandi: <b>{st.get('active_today', 0)} kishi</b>\n\n"
        f"🔔 <b>Sinf eslatmalari:</b>\n"
        f"• Obuna bo'lgan oilalar: <b>{st.get('subscribed_users', 0)} ta</b>\n"
        f"• Jami qo'shilgan sinflar: <b>{st.get('total_subs', 0)} ta</b>\n\n"
        f"🏆 <b>Eng ommabop sinflar:</b>\n{top_cls_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Oxirgi yangilanish: {datetime.now(UZ_TZ).strftime('%H:%M:%S')}</i>"
    )
    bot.send_message(message.chat.id, stat_text)

# 2 BOSQICHLI XABAR YUBORISH (BROADCAST VA RECALL)
@bot.message_handler(func=lambda msg: msg.text == "📢 Xabar yuborish (Filtr)")
def handle_broadcast_menu(message):
    admin = database.get_user(message.from_user.id)
    if not admin or admin["role"] != "admin":
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👨‍🏫 Faqat o'qituvchilarga", callback_data="bcfilter_teachers"),
        types.InlineKeyboardButton("🎒 Faqat o'quvchi va ota-onalarga", callback_data="bcfilter_students"),
        types.InlineKeyboardButton("📢 Butun maktabga (Barchaga)", callback_data="bcfilter_all"),
        types.InlineKeyboardButton("❌ Bekor qilish", callback_data="go_home_inline")
    )
    bot.send_message(message.chat.id, "📢 <b>E'lon yuborish bo'limi:</b>\n\nXabarni kimlarga yubormoqchisiz?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("bcfilter_"))
def handle_bc_filter_select(call):
    target = call.data.replace("bcfilter_", "")
    USER_STATES[call.from_user.id] = {"action": "broadcast_text", "target": target}
    titles = {"teachers": "👨‍🏫 O'qituvchilarga", "students": "🎒 O'quvchi va ota-onalarga", "all": "📢 Butun maktabga"}
    bot.edit_message_text(f"📝 <b>Guruh: {titles.get(target)}</b>\n\nYubormoqchi bo'lgan xabaringiz matnini yozing:\n\n<i>Bekor qilish: /cancel</i>", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "bc_cancel")
def handle_bc_cancel_action(call):
    if call.from_user.id in USER_STATES:
        del USER_STATES[call.from_user.id]
    bot.edit_message_text("❌ <b>Xabar yuborish bekor qilindi.</b>", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "bc_confirm_send")
def handle_bc_execute_send(call):
    uid = call.from_user.id
    state = USER_STATES.get(uid)
    if not state or state.get("action") != "confirm_broadcast":
        return
    
    target = state["target"]
    msg_text = state["text"]
    del USER_STATES[uid]
    
    bot.edit_message_text("⏳ <b>Xabar yuborilmoqda...</b>", call.message.chat.id, call.message.message_id)
    recipients = []
    conn = database.get_db()
    if target == "teachers":
        rows = conn.execute("SELECT telegram_id FROM users WHERE role IN ('admin', 'teacher')").fetchall()
        recipients = [r["telegram_id"] for r in rows]
    elif target == "students":
        rows = conn.execute("SELECT telegram_id FROM users WHERE role = 'student'").fetchall()
        recipients = [r["telegram_id"] for r in rows]
    else:
        rows = conn.execute("SELECT telegram_id FROM users").fetchall()
        recipients = [r["telegram_id"] for r in rows]
    conn.close()

    sent_pairs = []
    prefix_title = "📢 <b>MAKTAB MA'MURIYATIDAN RASMIY E'LON:</b>\n\n"
    for r_id in set(recipients):
        try:
            m = bot.send_message(r_id, prefix_title + msg_text)
            sent_pairs.append((r_id, m.message_id))
        except Exception:
            pass

    b_id = database.save_broadcast(uid, target, msg_text, sent_pairs)
    recall_markup = types.InlineKeyboardMarkup()
    recall_markup.add(types.InlineKeyboardButton("🗑 BARCHADAN O'CHIRISH (RECALL)", callback_data=f"bcrecall_{b_id}"))
    
    bot.send_message(
        call.message.chat.id,
        f"✅ <b>Xabar muvaffaqiyatli tarqatildi!</b>\n\n"
        f"👥 Yetkazildi: <b>{len(sent_pairs)} kishiga</b>\n\n"
        f"⚠️ <i>Agar xabar adashib ketgan bo'lsa, o'chirishingiz mumkin:</i>",
        reply_markup=recall_markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("bcrecall_"))
def handle_bc_recall(call):
    admin = database.get_user(call.from_user.id)
    if not admin or admin["role"] != "admin":
        return
    b_id = int(call.data.replace("bcrecall_", ""))
    pairs = database.get_broadcast_recipients(b_id)
    
    deleted_count = 0
    for chat_id, msg_id in pairs:
        try:
            bot.delete_message(chat_id, msg_id)
            deleted_count += 1
        except Exception:
            pass
            
    database.delete_broadcast_records(b_id)
    bot.edit_message_text(f"🗑 <b>XABAR BEKOR QILINDI!</b>\n\nE'lon barcha <b>{deleted_count} ta chatdan</b> butunlay o'chirildi.", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Xabar o'chirildi!")

@bot.message_handler(func=lambda msg: msg.text == "📥 Excel jadval yuklash")
def handle_excel_prompt(message):
    admin = database.get_user(message.from_user.id)
    if not admin or admin["role"] != "admin":
        return
    bot.send_message(message.chat.id, "📥 Yangi dars jadvali Excel faylini (.xlsx) fayl ko'rinishida yuboring.")

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

# ==================== KUTUBXONA VA DARS MATNLARI ====================

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

# ==================== METODIK AI YORDAMCHI ====================

@bot.message_handler(func=lambda msg: msg.text in ["💡 Metodik AI yordamchi", "💡 Savol-javob (AI)"])
def handle_ai_prompt(message):
    USER_STATES[message.from_user.id] = {"action": "ai_query"}
    bot.send_message(
        message.chat.id,
        "💡 <b>Ustoz AI — Aqlli pedagogik yordamchi faol!</b>\n\n"
        "Fanni va dars mavzusini yozing. Masalan:\n"
        "• <i>«7-sinf Fizika: Bosim mavzusida to'liq dars ishlanmasi tuzib ber»</i>\n"
        "• <i>«5-sinf Musiqa: 5 talik qiziqarli test savollari tuzib ber»</i>\n\n"
        "Savolingizni shu yerga yozib yuboring (Bekor qilish uchun: /cancel):"
    )

@bot.message_handler(commands=['cancel'])
def handle_cancel_cmd(message):
    if message.from_user.id in USER_STATES:
        del USER_STATES[message.from_user.id]
    bot.send_message(message.chat.id, "Amal bekor qilindi.")

@bot.message_handler(func=lambda msg: msg.text in ["✍️ Talab va takliflar", "✍️ Taklif bildirish"])
def handle_feedback_request(message):
    USER_STATES[message.from_user.id] = {"action": "send_feedback"}
    bot.send_message(message.chat.id, "✍️ Maktab ma'muriyatiga fikr yoki taklifingizni yozib yuboring (bekor qilish: /cancel):")

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
    
    if act == "editing_day_proc":
        user = database.get_user(uid)
        day = st["editing_day"]
        text = message.text.strip()
        m = re.search(r"(\d+)\s*(?:-dars)?\s*([A-Za-z0-9,\s\-]+)", text)
        if m:
            slot_num = int(m.group(1))
            cls_val = m.group(2).strip().upper()
            database.set_override(user["teacher_name"], day, slot_num, cls_val)
            del USER_STATES[uid]
            bot.send_message(message.chat.id, f"✅ <b>Dars muvaffaqiyatli to'g'irlandi!</b>\n\n📅 Kun: {day}\n⏰ Dars: {slot_num}-dars\n🏫 Yangi sinf: <b>{cls_val}</b>")
        else:
            bot.send_message(message.chat.id, "❌ Noto'g'ri format. Masalan: <code>2-dars 5A</code>")
        return

    if act in ["input_tog_fan", "input_tog_nomi", "input_tog_vaqt"]:
        tkey = st["tkey"]
        data = load_json_data(TOGARAK_FILE, {})
        if tkey not in data:
            data[tkey] = {}
        if act == "input_tog_fan":
            data[tkey]["fan"] = message.text.strip()
        elif act == "input_tog_nomi":
            data[tkey]["nomi"] = message.text.strip()
        elif act == "input_tog_vaqt":
            data[tkey]["vaqt"] = message.text.strip()
        save_json_data(TOGARAK_FILE, data)
        del USER_STATES[uid]
        matn, markup = render_togarak_card(tkey)
        bot.send_message(message.chat.id, f"✅ <b>Ma’lumot saqlandi!</b>\n\n" + matn, reply_markup=markup, parse_mode="HTML")
        return

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

    if act == "adm_book_subj":
        gr = st["grade"]
        subj = message.text.strip().capitalize()
        USER_STATES[uid] = {"action": "adm_waiting_pdf", "grade": gr, "subj": subj}
        bot.send_message(message.chat.id, f"📥 <b>{gr}-sinf {subj}</b> tanlandi. PDF faylni Telegramga yuboring:")
        return

    if act == "lib_reading_lesson":
        gr, subj = st["grade"], st["subj"]
        q = message.text.strip()
        del USER_STATES[uid]
        bot.send_chat_action(message.chat.id, 'typing')
        prompt = f"Sen {gr}-sinf {subj} fani darslik muallifisan. '{q}' mavzusi bo'yicha maktab darsligi formatida o'quvchi uchun juda aniq, tushunarli qoidalar, dars matni va uyga vazifa tuzib ber."
        ans, err = generate_ai_response(prompt)
        header = f"━━━━━━━━━━━━━━━━━━━━\n📖 *{gr.upper()}-SINF | {subj.upper()} DARSLIGI*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        if ans:
            send_long_ai_message(message.chat.id, header + ans, message.message_id)
        else:
            bot.reply_to(message, f"⚠️ Xatolik: {err}")
        return

    if act == "ai_query":
        del USER_STATES[uid]
        bot.send_chat_action(message.chat.id, 'typing')
        prompt = (
            "Sen O'zbekistondagi 80-umumiy o'rta ta'lim maktabining aqlli pedagogik AI yordamchisisan. "
            "O'qituvchilar, o'quvchilar va ota-onalarning savollariga o'zbek tilida, muloyim, aniq va professional pedagogik darajada javob ber.\n\n"
            f"Savol/Mavzu: {message.text}"
        )
        answer, err = generate_ai_response(prompt)
        if answer:
            send_long_ai_message(message.chat.id, answer, message.message_id)
        else:
            bot.reply_to(message, f"⚠️ AI javob berishda xatolik yuz berdi: {err}\n\nIltimos, qaytadan urinib ko'ring.")
        return

    if act == "broadcast_text":
        target = st["target"]
        text = message.text
        USER_STATES[uid] = {"action": "confirm_broadcast", "target": target, "text": text}
        titles = {"teachers": "O'qituvchilar", "students": "O'quvchi/Ota-onalar", "all": "Barcha foydalanuvchilar"}
        preview_markup = types.InlineKeyboardMarkup(row_width=2)
        preview_markup.add(
            types.InlineKeyboardButton("🚀 Tasdiqlayman va yuborilsin", callback_data="bc_confirm_send"),
            types.InlineKeyboardButton("❌ Bekor qilish", callback_data="bc_cancel")
        )
        bot.send_message(
            message.chat.id,
            f"⚠️ <b>XABARNI YUBORISHNI TASDIQLAYSIZMI?</b>\n\n"
            f"🎯 <b>Qabul qiluvchilar:</b> {titles.get(target)}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 <b>Xabar matni:</b>\n{text}\n"
            f"━━━━━━━━━━━━━━━━━━━━",
            reply_markup=preview_markup
        )
        return

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
        send_long_ai_message(message.chat.id, ans, message.message_id)
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
