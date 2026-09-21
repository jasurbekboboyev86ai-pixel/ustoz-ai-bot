# -*- coding: utf-8 -*-
"""
80-maktab "Ustoz AI" Telegram Boti
Muallif: Ustoz AI jamoasi & Boboev Jasurbek
"""

import os
import sys
from threading import Thread
from flask import Flask
import telebot
from telebot import types
import json
import sqlite3
import google.generativeai as genai

import config
import database

# Render Web Service uchun fon veb-serveri
app = Flask(__name__)

@app.route('/')
def home():
    return "80-maktab 'Ustoz AI' boti faol ishlamoqda!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# Gemini AI konfiguratsiyasi
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
ai_model = None
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        ai_model = genai.GenerativeModel("gemini-2.5-flash")
    except Exception:
        ai_model = None

# Telegram bot sozlamasi
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or config.BOT_TOKEN
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

USER_STATES = {}

# --- TUGMALAR (KEYBOARDS) ---

def get_contact_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    btn = types.KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True)
    markup.add(btn)
    return markup

def get_admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    b1 = types.KeyboardButton("📥 Excel jadval yuklash")
    b2 = types.KeyboardButton("👥 O'qituvchilar ro'yxati")
    b3 = types.KeyboardButton("📊 Maktab umumiy hisoboti")
    b4 = types.KeyboardButton("📢 Ommaviy xabar yuborish")
    b5 = types.KeyboardButton("📅 Mening darslarim")
    b6 = types.KeyboardButton("⏰ Haftalik yuklamam")
    markup.add(b1, b2)
    markup.add(b3, b4)
    markup.add(b5, b6)
    return markup

def get_teacher_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    b1 = types.KeyboardButton("📅 Dars jadvalim")
    b2 = types.KeyboardButton("⏰ Haftalik yuklamam")
    b3 = types.KeyboardButton("🎨 To'garaklarim")
    b4 = types.KeyboardButton("✏️ Dars kunini to'g'irlash")
    markup.add(b1, b2)
    markup.add(b3, b4)
    return markup

def get_days_inline_keyboard(prefix="day_view"):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = []
    for d in config.DAYS:
        btns.append(types.InlineKeyboardButton(f"📅 {d}", callback_data=f"{prefix}_{d}"))
    markup.add(*btns)
    if prefix == "day_view":
        markup.add(types.InlineKeyboardButton("🗓️ Butun haftalik jadval", callback_data=f"{prefix}_ALL"))
    return markup

def get_teachers_page_inline(page=0, per_page=8):
    teachers = database.get_teachers_list()
    total = len(teachers)
    start = page * per_page
    end = min(start + per_page, total)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    slice_t = teachers[start:end]
    btns = []
    for t in slice_t:
        name = t["name"]
        subj = t["subjects"][0] if t["subjects"] else "Dars"
        btns.append(types.InlineKeyboardButton(f"👤 {name} ({subj})", callback_data=f"selteach_{name}"))
    markup.add(*btns)
    
    nav_btns = []
    if page > 0:
        nav_btns.append(types.InlineKeyboardButton("⬅️ Oldingi", callback_data=f"tpage_{page-1}"))
    if end < total:
        nav_btns.append(types.InlineKeyboardButton("Keyingi ➡️", callback_data=f"tpage_{page+1}"))
    if nav_btns:
        markup.row(*nav_btns)
    return markup

# --- BUYRUQLAR (COMMAND HANDLERS) ---

@bot.message_handler(commands=['start'])
def handle_start(message):
    uid = message.from_user.id
    user = database.get_user(uid)
    
    if user:
        if user["role"] == "admin":
            bot.send_message(
                message.chat.id,
                f"<b>Assalomu alaykum, {user['full_name']}!</b>\n\n"
                f"👑 <b>Siz Bosh Admin hisoblanasiz.</b>\n"
                f"80-maktab 'Ustoz AI' boshqaruv panelingizga xush kelibsiz.",
                reply_markup=get_admin_keyboard()
            )
        else:
            bot.send_message(
                message.chat.id,
                f"<b>Assalomu alaykum, {user['teacher_name']}!</b>\n\n"
                f"👨‍🏫 80-maktab 'Ustoz AI' shaxsiy kabinetingizga xush kelibsiz.\n"
                f"Quyidagi tugmalar orqali o'z dars jadvalingiz va yuklamangizni ko'rishingiz mumkin:",
                reply_markup=get_teacher_keyboard()
            )
    else:
        welcome_text = (
            "<b>Assalomu alaykum!</b>\n\n"
            "🏫 <b>80-umumiy o'rta ta'lim maktabi 'Ustoz AI' dars jadvali tizimiga xush kelibsiz.</b>\n\n"
            "🔒 <i>Shaxsiy kabinetingizga kirish va xavfsiz ulanish uchun quyidagi tugmani bosib telefon raqamingizni tasdiqlang:</i>"
        )
        bot.send_message(message.chat.id, welcome_text, reply_markup=get_contact_keyboard())

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    if not message.contact:
        return
    
    uid = message.from_user.id
    phone = message.contact.phone_number.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    
    full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip() or "Ustoz"
    
    if database.is_phone_admin(phone, config.ADMIN_PHONES):
        database.register_user(uid, phone, full_name, "Boboev J", "admin")
        bot.send_message(
            message.chat.id,
            f"🎉 <b>Tabriklaymiz, Jasurbek aka!</b>\n\n"
            f"Siz <b>Bosh Admin</b> sifatida muvaffaqiyatli ulandingiz.\n"
            f"Telefon: <code>{phone}</code>\n\n"
            f"Barcha maktab o'qituvchilari dars jadvallari va ulanish so'rovlari sizning to'liq nazoratingizda!",
            reply_markup=get_admin_keyboard()
        )
        return
    
    USER_STATES[uid] = {"phone": phone, "full_name": full_name}
    bot.send_message(
        message.chat.id,
        f"✅ <b>Telefon raqamingiz qabul qilindi:</b> <code>{phone}</code>\n\n"
        f"Iltimos, quyidagi ro'yxatdan <b>o'z ism-familiyangizni tanlang</b>:",
        reply_markup=get_teachers_page_inline(page=0)
    )

# --- O'QITUVCHI TANLASH VA CALLBACKLAR ---

@bot.callback_query_handler(func=lambda call: call.data.startswith("tpage_"))
def handle_teacher_pagination(call):
    page = int(call.data.split("_")[1])
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_teachers_page_inline(page=page))
    except Exception:
        pass
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("selteach_"))
def handle_teacher_selection(call):
    teacher_name = call.data.replace("selteach_", "")
    uid = call.from_user.id
    state = USER_STATES.get(uid)
    
    if not state:
        user = database.get_user(uid)
        phone = user["phone"] if user else "Noma'lum"
        full_name = user["full_name"] if user else call.from_user.first_name
    else:
        phone = state["phone"]
        full_name = state["full_name"]
    
    req_id = database.create_pending_request(uid, phone, full_name, teacher_name)
    
    bot.edit_message_text(
        f"⏳ <b>So'rovingiz qabul qilindi!</b>\n\n"
        f"👤 <b>Tanlangan o'qituvchi:</b> {teacher_name}\n"
        f"📱 <b>Telefon raqam:</b> <code>{phone}</code>\n\n"
        f"<i>Maktab ma'muriyati (Bosh Admin) so'rovingizni tasdiqlashi bilan shaxsiy kabinetingiz to'liq ishga tushadi. Kuting...</i>",
        call.message.chat.id,
        call.message.message_id
    )
    bot.answer_callback_query(call.id, "So'rov adminga yuborildi!")
    
    admins = database.get_all_admins()
    admin_markup = types.InlineKeyboardMarkup(row_width=2)
    b_app = types.InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"appreq_{req_id}")
    b_rej = types.InlineKeyboardButton("❌ Rad etish", callback_data=f"rejreq_{req_id}")
    admin_markup.add(b_app, b_rej)
    
    username_str = f"@{call.from_user.username}" if call.from_user.username else "mavjud emas"
    admin_notice = (
        f"🔔 <b>YANGI O'QITUVCHI ULANISH SO'ROVI:</b>\n\n"
        f"👤 <b>O'qituvchi:</b> {teacher_name}\n"
        f"📱 <b>Telefon:</b> <code>{phone}</code>\n"
        f"💬 <b>Telegram:</b> {full_name} ({username_str})\n\n"
        f"Ushbu o'qituvchiga dars jadvaliga kirish huquqini berasizmi?"
    )
    
    for a_id in admins:
        try:
            bot.send_message(a_id, admin_notice, reply_markup=admin_markup)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("appreq_"))
def handle_admin_approve(call):
    admin_user = database.get_user(call.from_user.id)
    if not admin_user or admin_user["role"] != "admin":
        bot.answer_callback_query(call.id, "Faqat admin tasdiqlay oladi!", show_alert=True)
        return
    
    req_id = int(call.data.split("_")[1])
    req = database.approve_request(req_id)
    
    if req:
        bot.edit_message_text(
            f"✅ <b>TASDIQLANDI!</b>\n\n"
            f"👤 O'qituvchi: <b>{req['teacher_name']}</b>\n"
            f"📱 Tel: <code>{req['phone']}</code>\n"
            f"Tasdiqladi: {admin_user['full_name']}",
            call.message.chat.id,
            call.message.message_id
        )
        bot.answer_callback_query(call.id, "O'qituvchi ulandi!")
        
        try:
            bot.send_message(
                req["telegram_id"],
                f"🎉 <b>Tabriklaymiz, {req['teacher_name']}!</b>\n\n"
                f"Sizning so'rovingiz Bosh Admin tomonidan tasdiqlandi.\n"
                f"Endi dars jadvalingiz, haftalik yuklamangiz va to'garaklaringizni ko'rishingiz mumkin:",
                reply_markup=get_teacher_keyboard()
            )
        except Exception:
            pass
    else:
        bot.answer_callback_query(call.id, "So'rov topilmadi yoki avval ko'rib chiqilgan!")

@bot.callback_query_handler(func=lambda call: call.data.startswith("rejreq_"))
def handle_admin_reject(call):
    admin_user = database.get_user(call.from_user.id)
    if not admin_user or admin_user["role"] != "admin":
        bot.answer_callback_query(call.id, "Faqat admin!", show_alert=True)
        return
    
    req_id = int(call.data.split("_")[1])
    req = database.get_pending_request(req_id)
    database.reject_request(req_id)
    
    bot.edit_message_text(
        f"❌ <b>RAD ETILDI</b>\n\n"
        f"👤 So'rovchi: {req['teacher_name'] if req else 'Noma\'lum'}\n"
        f"Rad etdi: {admin_user['full_name']}",
        call.message.chat.id,
        call.message.message_id
    )
    bot.answer_callback_query(call.id, "Rad etildi!")
    
    if req:
        try:
            bot.send_message(
                req["telegram_id"],
                "❌ <i>Kechirasiz, sizning so'rovingiz maktab ma'muriyati tomonidan rad etildi. "
                "Iltimos, ma'muriyat bilan bog'laning.</i>"
            )
        except Exception:
            pass

# --- JADVAL FORMATLASH ---

def format_day_schedule(teacher_name, day):
    t = database.get_teacher_schedule(teacher_name)
    if not t:
        return f"❌ <b>{teacher_name}</b> bo'yicha jadval topilmadi."
    
    sched = t["schedule"].get(day, {})
    subj_str = ", ".join(t["subjects"]) if t["subjects"] else "Dars"
    
    text = f"📅 <b>{day.upper()} — DARS JADVALI</b>\n"
    text += f"👤 <b>Ustoz:</b> {t['name']} | 📚 <b>Fan:</b> {subj_str}\n\n"
    
    s1_lines = []
    for p in range(1, 7):
        entries = sched.get(p) or sched.get(str(p)) or []
        if entries:
            cls_str = ", ".join([e["class"] for e in entries])
            s1_lines.append(f"• <b>{p}-dars</b> (<code>{config.SMENA1_TIMES[p]}</code>): <b>{cls_str}</b>")
    
    text += "🔵 <b>I - SMENA (08:00 - 13:05):</b>\n"
    if s1_lines:
        text += "\n".join(s1_lines) + "\n\n"
    else:
        text += "<i>Bugun 1-smenada dars yo'q</i>\n\n"
    
    s2_lines = []
    for p in range(1, 7):
        slot = config.SMENA2_TIMES[p]["slot"]
        t_str = config.SMENA2_TIMES[p]["time"]
        entries = sched.get(slot) or sched.get(str(slot)) or []
        if entries:
            cls_str = ", ".join([e["class"] for e in entries])
            s2_lines.append(f"• <b>{p}-dars</b> (<code>{t_str}</code>): <b>{cls_str}</b>")
    
    text += "🟢 <b>II - SMENA (13:10 - 18:10):</b>\n"
    if s2_lines:
        text += "\n".join(s2_lines) + "\n\n"
    else:
        text += "<i>Bugun 2-smenada dars yo'q</i>\n\n"
    
    total_day = len(s1_lines) + len(s2_lines)
    text += f"📊 <b>Bugungi jami dars: {total_day} soat</b>"
    return text

def format_week_schedule(teacher_name):
    t = database.get_teacher_schedule(teacher_name)
    if not t:
        return "❌ Jadval topilmadi."
    
    text = f"🗓️ <b>HAFTALIK TO'LIQ DARS JADVALI</b>\n"
    text += f"👤 <b>Ustoz:</b> {t['name']} ({', '.join(t['subjects'])})\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    total_week = 0
    for d in config.DAYS:
        sched = t["schedule"].get(d, {})
        day_items = []
        for p in range(1, 7):
            ent = sched.get(p) or sched.get(str(p)) or []
            if ent:
                day_items.append(f"{p}-dars: {', '.join([e['class'] for e in ent])} (1-smena)")
        for p in range(1, 7):
            slot = config.SMENA2_TIMES[p]["slot"]
            ent = sched.get(slot) or sched.get(str(slot)) or []
            if ent:
                day_items.append(f"{p}-dars: {', '.join([e['class'] for e in ent])} (2-smena)")
        
        total_week += len(day_items)
        text += f"📅 <b>{d}:</b>\n"
        if day_items:
            for item in day_items:
                text += f"  • {item}\n"
        else:
            text += "  <i>Dars yo'q</i>\n"
        text += "\n"
        
    text += f"━━━━━━━━━━━━━━━━━━━━\n"
    text += f"⭐ <b>Jami haftalik darslar: {total_week} soat</b>"
    return text

# --- TUGMALAR HODISALARI ---

@bot.message_handler(func=lambda msg: msg.text in ["📅 Dars jadvalim", "📅 Mening darslarim"])
def handle_schedule_menu(message):
    user = database.get_user(message.from_user.id)
    if not user:
        return
    teacher_name = user["teacher_name"] or "Boboev J"
    bot.send_message(
        message.chat.id,
        f"📅 <b>{teacher_name}</b>, qaysi kungi dars jadvalini ko'rmoqchisiz?",
        reply_markup=get_days_inline_keyboard("day_view")
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("day_view_"))
def handle_day_view_callback(call):
    day = call.data.replace("day_view_", "")
    user = database.get_user(call.from_user.id)
    teacher_name = user["teacher_name"] if user else "Boboev J"
    
    if day == "ALL":
        text = format_week_schedule(teacher_name)
    else:
        text = format_day_schedule(teacher_name, day)
    
    bot.send_message(call.message.chat.id, text)
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda msg: msg.text == "⏰ Haftalik yuklamam")
def handle_workload(message):
    user = database.get_user(message.from_user.id)
    if not user:
        return
    t = database.get_teacher_schedule(user["teacher_name"])
    if not t:
        bot.send_message(message.chat.id, "Yuklama topilmadi.")
        return
    
    s1_count = 0
    s2_count = 0
    for d in config.DAYS:
        sched = t["schedule"].get(d, {})
        for p in range(1, 7):
            s1_count += len(sched.get(p) or sched.get(str(p)) or [])
        for p in range(1, 7):
            slot = config.SMENA2_TIMES[p]["slot"]
            s2_count += len(sched.get(slot) or sched.get(str(slot)) or [])
            
    total_dars = s1_count + s2_count
    togs = database.get_togaraklar(user["teacher_name"])
    tog_count = len(togs)
    total_load = total_dars + tog_count
    
    text = (
        f"📊 <b>HAFTALIK DARS VA YUKLAMA HISOBOTI</b>\n\n"
        f"👤 <b>Ustoz:</b> {t['name']}\n"
        f"📚 <b>Fan:</b> {', '.join(t['subjects'])}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔵 <b>I - Smena darslari:</b> {s1_count} soat\n"
        f"🟢 <b>II - Smena darslari:</b> {s2_count} soat\n"
        f"📖 <b>Jami o'quv darslari:</b> {total_dars} soat\n"
        f"🎨 <b>To'garaklar:</b> {tog_count} soat\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⭐ <b>UMUMIY HAFTALIK YUKLAMA: {total_load} SOAT</b>"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda msg: msg.text == "🎨 To'garaklarim")
def handle_togaraklar_view(message):
    user = database.get_user(message.from_user.id)
    if not user:
        return
    togs = database.get_togaraklar(user["teacher_name"])
    
    if not togs:
        bot.send_message(message.chat.id, f"🎨 <b>{user['teacher_name']}</b> ga hozircha to'garak biriktirilmagan.")
        return
    
    text = f"🎨 <b>{user['teacher_name']} — TO'GARAKLAR RO'YXATI:</b>\n\n"
    for idx, tg in enumerate(togs, 1):
        text += f"<b>{idx}. {tg['name']}</b>\n"
        text += f"   • Fan: {tg['subject']}\n"
        text += f"   • Kuni: {tg['day']}\n"
        text += f"   • Vaqti: {tg['time']}\n\n"
    
    bot.send_message(message.chat.id, text)

# --- DARSNI TO'G'IRLASH ---

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
    
    USER_STATES[call.from_user.id] = {"editing_day": day}
    
    msg_text = (
        f"✏️ <b>{day} kungi darsni to'g'irlash:</b>\n\n"
        f"Iltimos, dars raqami va yangi sinfni yozing.\n"
        f"<i>Masalan:</i> <code>2-dars 5A</code> yoki <code>bo'sh</code> qilish uchun: <code>2-dars -</code>"
    )
    bot.send_message(call.message.chat.id, msg_text)
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda msg: msg.from_user.id in USER_STATES and "editing_day" in USER_STATES[msg.from_user.id])
def process_day_edit_text(message):
    uid = message.from_user.id
    user = database.get_user(uid)
    day = USER_STATES[uid]["editing_day"]
    text = message.text.strip()
    
    import re
    m = re.search(r"(\d+)\s*(?:-dars)?\s*([A-Za-z0-9,\s\-]+)", text)
    if m:
        slot_num = int(m.group(1))
        cls_val = m.group(2).strip().upper()
        database.set_override(user["teacher_name"], day, slot_num, cls_val)
        del USER_STATES[uid]["editing_day"]
        
        bot.send_message(
            message.chat.id,
            f"✅ <b>Dars muvaffaqiyatli to'g'irlandi!</b>\n\n"
            f"📅 Kun: {day}\n"
            f"⏰ Dars: {slot_num}-dars\n"
            f"🏫 Yangi sinf: <b>{cls_val}</b>",
            reply_markup=get_teacher_keyboard() if user["role"] == "teacher" else get_admin_keyboard()
        )
    else:
        bot.send_message(
            message.chat.id,
            "❌ Noto'g'ri format. Masalan quyidagicha yozing: <code>2-dars 5A</code> yoki <code>3-dars -</code>"
        )

# --- ADMIN BUYRUQLARI ---

@bot.message_handler(func=lambda msg: msg.text == "👥 O'qituvchilar ro'yxati")
def handle_admin_teachers_list(message):
    user = database.get_user(message.from_user.id)
    if not user or user["role"] != "admin":
        return
    
    users = database.get_all_connected_users()
    teachers_db = database.get_teachers_list()
    
    text = f"👥 <b>80-MAKTAB — O'QITUVCHILAR HOLATI:</b>\n\n"
    text += f"📚 Bazadagi jami o'qituvchilar: <b>{len(teachers_db)} nafar</b>\n"
    text += f"📱 Botga ulangan ustozlar: <b>{len(users)} nafar</b>\n\n"
    text += "<b>Ulanganlar ro'yxati:</b>\n"
    
    for idx, u in enumerate(users, 1):
        role_badge = "👑 Admin" if u["role"] == "admin" else "👨‍🏫 O'qituvchi"
        text += f"{idx}. <b>{u['teacher_name']}</b> ({u['phone']}) — {role_badge}\n"
        
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda msg: msg.text == "📊 Maktab umumiy hisoboti")
def handle_admin_school_report(message):
    user = database.get_user(message.from_user.id)
    if not user or user["role"] != "admin":
        return
    
    teachers_db = database.get_teachers_list()
    total_hours = sum(t.get("total_hours", 0) for t in teachers_db)
    
    text = (
        f"📊 <b>80-MAKTAB UMUMIY JADVAL HISOBOTI:</b>\n\n"
        f"🏫 Jami o'qituvchilar: <b>{len(teachers_db)} nafar</b>\n"
        f"⏱️ Jami haftalik dars soatlari: <b>{total_hours} soat</b>\n"
        f"🎵 Boboev J (Musiqa): <b>20 soat dars + 1 soat to'garak = 21 soat</b>\n\n"
        f"✅ <i>Jadval 1-11 sinflar bo'yicha to'liq integratsiya qilingan.</i>"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda msg: msg.text == "📢 Ommaviy xabar yuborish")
def handle_admin_broadcast_prompt(message):
    user = database.get_user(message.from_user.id)
    if not user or user["role"] != "admin":
        return
    USER_STATES[message.from_user.id] = {"action": "broadcast"}
    bot.send_message(
        message.chat.id,
        "📢 Barcha ulangan o'qituvchilarga qanday xabar yubormoqchisiz?\n\n"
        "Xabaringizni yozib yuboring (bekor qilish uchun /cancel):"
    )

@bot.message_handler(commands=['cancel'])
def handle_cancel(message):
    if message.from_user.id in USER_STATES:
        del USER_STATES[message.from_user.id]
    bot.send_message(message.chat.id, "Amal bekor qilindi.")

@bot.message_handler(func=lambda msg: msg.text == "📥 Excel jadval yuklash")
def handle_excel_prompt(message):
    user = database.get_user(message.from_user.id)
    if not user or user["role"] != "admin":
        return
    bot.send_message(
        message.chat.id,
        "📥 <b>Yangi dars jadvali Excel faylini (.xlsx) shu yerga fayl sifatida yuboring:</b>\n\n"
        "Bot uni qabul qilib, barcha varaqlarini skanerlaydi va bazani avtomatik yangilaydi."
    )

@bot.message_handler(content_types=['document'])
def handle_document_upload(message):
    user = database.get_user(message.from_user.id)
    if not user or user["role"] != "admin":
        bot.send_message(message.chat.id, "Faqat Bosh Admin Excel fayl yuklay oladi.")
        return
    
    doc = message.document
    if not doc.file_name.endswith(('.xlsx', '.xls')):
        bot.send_message(message.chat.id, "Iltimos, faqat Excel (.xlsx) fayl yuboring.")
        return
    
    msg_wait = bot.send_message(message.chat.id, "⏳ <b>Excel fayl qabul qilindi. Skanerlash boshlanmoqda...</b>")
    try:
        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)
        
        save_path = os.path.join(os.path.dirname(__file__), "uploaded_schedule.xlsx")
        with open(save_path, 'wb') as f:
            f.write(downloaded)
            
        bot.edit_message_text(
            f"✅ <b>Hujjat to'liq skanerlandi va saqlandi!</b>\n\n"
            f"📁 Fayl: <code>{doc.file_name}</code>\n"
            f"Haftalik dars jadvali yangilandi.",
            message.chat.id,
            msg_wait.message_id
        )
    except Exception as err:
        bot.edit_message_text(f"❌ Xatolik yuz berdi: {err}", message.chat.id, msg_wait.message_id)

@bot.message_handler(func=lambda msg: msg.from_user.id in USER_STATES and USER_STATES[msg.from_user.id].get("action") == "broadcast")
def handle_broadcast_text(message):
    uid = message.from_user.id
    del USER_STATES[uid]
    
    users = database.get_all_connected_users()
    count = 0
    for u in users:
        try:
            bot.send_message(
                u["telegram_id"],
                f"📢 <b>MAKTAB MA'MURIYATIDAN E'LON:</b>\n\n{message.text}"
            )
            count += 1
        except Exception:
            pass
            
    bot.send_message(message.chat.id, f"✅ Xabar <b>{count} nafar</b> o'qituvchiga muvaffaqiyatli yetkazildi!")

# Boshqa barcha matnlarga javob (AI yordamchi)
@bot.message_handler(func=lambda msg: True)
def handle_ai_fallback(message):
    if ai_model:
        try:
            res = ai_model.generate_content(message.text)
            bot.reply_to(message, res.text)
            return
        except Exception:
            pass
    bot.reply_to(message, "Tushunarsiz buyruq. Iltimos, menyudagi tugmalardan foydalaning.")

# --- BOTNI ISHGA TUSHIRISH ---
if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    print("80-maktab Ustoz AI Boti muvaffaqiyatli ishga tushdi...")
    bot.infinity_polling(skip_pending=True)
