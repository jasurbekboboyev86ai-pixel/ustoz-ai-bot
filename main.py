# -*- coding: utf-8 -*-
"""
80-maktab "Ustoz AI" Telegram Boti - To'liq integratsiyalashgan versiya
Muallif: Boboev Jasurbek & Ustoz AI jamoasi
"""

import os
import sys
import time
import re
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

# Gemini AI konfiguratsiyasi (Barqaror 1.5-flash modeli)
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
ai_model = None
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        ai_model = genai.GenerativeModel("gemini-1.5-flash")
        print("✅ Gemini AI (gemini-1.5-flash) muvaffaqiyatli ulandi!")
    except Exception as e:
        print(f"❌ Gemini AI ulanish xatosi: {e}")
        ai_model = None

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or config.BOT_TOKEN
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

USER_STATES = {}
UZ_TZ = timezone(timedelta(hours=5))

# --- ASOSIY MENYU TUGMALARI ---

def get_welcome_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    b1 = types.KeyboardButton("📱 O'qituvchi bo'lib kirish (Tel raqam)", request_contact=True)
    b2 = types.KeyboardButton("🎒 Sinf dars jadvallari")
    b3 = types.KeyboardButton("🔔 Eslatmalarga obuna bo'lish")
    b4 = types.KeyboardButton("👨‍💻 Dasturchi va ma'lumot")
    markup.add(b1)
    markup.add(b2, b3)
    markup.add(b4)
    return markup

def get_admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    b1 = types.KeyboardButton("📥 Excel jadval yuklash")
    b2 = types.KeyboardButton("👥 O'qituvchilar holati")
    b3 = types.KeyboardButton("📊 Maktab umumiy hisoboti")
    b4 = types.KeyboardButton("📈 Jonli statistika")
    b5 = types.KeyboardButton("📢 Xabar yuborish (Filtr)")
    b6 = types.KeyboardButton("📅 Mening darslarim")
    b7 = types.KeyboardButton("⏰ Haftalik yuklamam")
    b8 = types.KeyboardButton("🎒 Sinf jadvali")
    b9 = types.KeyboardButton("💡 Metodik AI yordamchi")
    b10 = types.KeyboardButton("🏠 Bosh sahifa")
    markup.add(b1, b2)
    markup.add(b3, b4)
    markup.add(b5)
    markup.add(b6, b7)
    markup.add(b8, b9)
    markup.add(b10)
    return markup

def get_teacher_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    b1 = types.KeyboardButton("📅 Dars jadvalim")
    b2 = types.KeyboardButton("⏰ Haftalik yuklamam")
    b3 = types.KeyboardButton("🎨 To'garaklarim")
    b4 = types.KeyboardButton("✏️ Dars kunini to'g'irlash")
    b5 = types.KeyboardButton("🎒 Sinf jadvali")
    b6 = types.KeyboardButton("💡 Metodik AI yordamchi")
    b7 = types.KeyboardButton("✍️ Talab va takliflar")
    b8 = types.KeyboardButton("🏠 Bosh sahifa")
    markup.add(b1, b2)
    markup.add(b3, b4)
    markup.add(b5, b6)
    markup.add(b7, b8)
    return markup

def get_student_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    b1 = types.KeyboardButton("🎒 Sinf dars jadvallari")
    b2 = types.KeyboardButton("🔔 Mening obunalarim")
    b3 = types.KeyboardButton("💡 Savol-javob (AI)")
    b4 = types.KeyboardButton("✍️ Taklif bildirish")
    b5 = types.KeyboardButton("📱 O'qituvchi sifatida ulanish", request_contact=True)
    b6 = types.KeyboardButton("🏠 Bosh sahifa")
    markup.add(b1, b2)
    markup.add(b3, b4)
    markup.add(b5)
    markup.add(b6)
    return markup

# --- YORDAMCHI VA INLINE TUGMALAR ---

def get_days_inline_keyboard(prefix="day_view"):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [types.InlineKeyboardButton(f"📅 {d}", callback_data=f"{prefix}_{d}") for d in config.DAYS]
    markup.add(*btns)
    if prefix == "day_view":
        markup.add(types.InlineKeyboardButton("🗓️ Butun haftalik jadval", callback_data=f"{prefix}_ALL"))
    markup.add(types.InlineKeyboardButton("🏠 Bosh sahifaga qaytish", callback_data="go_home_inline"))
    return markup

def get_teachers_page_inline(page=0, per_page=8):
    teachers = database.get_teachers_list()
    total = len(teachers)
    start = page * per_page
    end = min(start + per_page, total)
    markup = types.InlineKeyboardMarkup(row_width=2)
    for t in teachers[start:end]:
        name = t["name"]
        subj = t["subjects"][0] if t["subjects"] else "Fan"
        markup.add(types.InlineKeyboardButton(f"👤 {name} ({subj})", callback_data=f"selteach_{name}"))
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton("⬅️ Oldingi", callback_data=f"tpage_{page-1}"))
    if end < total:
        nav.append(types.InlineKeyboardButton("Keyingi ➡️", callback_data=f"tpage_{page+1}"))
    if nav:
        markup.row(*nav)
    markup.add(types.InlineKeyboardButton("❌ Bekor qilish", callback_data="go_home_inline"))
    return markup

# --- SINF JADVALI HISOBLASH VA FORMATLASH ---

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
            is_sub = c in user_subs
            icon = "✅" if is_sub else "➕"
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
                        "subject": subj,
                        "time": e.get("time", "")
                    })
    return slots_data

def format_class_day_schedule(class_name, day):
    slots_data = get_class_day_schedule(class_name, day)
    text = f"🎒 <b>{class_name.upper()} SINF — {day.upper()} KUNI:</b>\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n"
    s1_lines = []
    for p in range(1, 7):
        if p in slots_data:
            for item in slots_data[p]:
                t_str = item["time"] or config.SMENA1_TIMES.get(p, "")
                s1_lines.append(f"• <b>{p}-dars</b> (<code>{t_str}</code>): <b>{item['subject']}</b>\n   └ <i>Ustoz: {item['teacher']}</i>")
    s2_lines = []
    for p in range(1, 7):
        slot = p + 6
        if slot in slots_data:
            for item in slots_data[slot]:
                t_str = item["time"] or config.SMENA2_TIMES.get(p, {}).get("time", "")
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
                text += f"  • {l}\n"
        else:
            text += "  <i>Dars yo'q</i>\n"
        text += "\n"
    text += "━━━━━━━━━━━━━━━━━━━━"
    return text

# --- BOSH SAHIFA VA START BUYRUG'I ---

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
            f"👑 <b>Assalomu alaykum, {user['full_name']}!</b>\n\n"
            f"Maktab boshqaruv markaziga xush kelibsiz. Barcha tizimlar to'liq nazoratingizda.",
            reply_markup=get_admin_keyboard()
        )
    elif user and user.get("role") == "teacher":
        bot.send_message(
            message.chat.id,
            f"👨‍🏫 <b>Assalomu alaykum, {user['teacher_name']}!</b>\n\n"
            f"80-maktab 'Ustoz AI' shaxsiy kabinetingizdasiz.",
            reply_markup=get_teacher_keyboard()
        )
    else:
        welcome_text = (
            "🏫 <b>80-umumiy o'rta ta'lim maktabi «Ustoz AI» tizimiga xush kelibsiz!</b>\n\n"
            "• <b>O'qituvchilar uchun:</b> Shaxsiy dars jadvali, yuklamalar va AI dars ishlanmalari.\n"
            "• <b>O'quvchi va ota-onalar uchun:</b> 1–11 sinflar dars jadvallari hamda kechki eslatmalar.\n\n"
            "<i>Kerakli bo'limni tanlang:</i>"
        )
        bot.send_message(message.chat.id, welcome_text, reply_markup=get_student_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == "go_home_inline")
def handle_home_inline(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    handle_start(call.message)
    bot.answer_callback_query(call.id)

# --- TELEFON VA REGISTRATSIYA ---

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
            f"🎉 <b>Xush kelibsiz, Jasurbek aka!</b>\n\n"
            f"Siz <b>Bosh Admin</b> sifatida muvaffaqiyatli tanildingiz.\n"
            f"Barcha maktab tizimi boshqaruvi sizga topshirildi.",
            reply_markup=get_admin_keyboard()
        )
        return
    
    USER_STATES[uid] = {"phone": phone, "full_name": full_name}
    bot.send_message(
        message.chat.id,
        f"📱 <b>Raqamingiz qabul qilindi:</b> <code>{phone}</code>\n\n"
        f"Iltimos, quyidagi ro'yxatdan <b>o'z ism-familiyangizni tanlang</b>:",
        reply_markup=get_teachers_page_inline(page=0)
    )

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
    phone = state["phone"] if state else "Noma'lum"
    full_name = state["full_name"] if state else call.from_user.first_name
    
    req_id = database.create_pending_request(uid, phone, full_name, teacher_name)
    bot.edit_message_text(
        f"⏳ <b>Arizangiz ma'muriyatga yuborildi!</b>\n\n"
        f"👤 Tanlangan ustoz: <b>{teacher_name}</b>\n"
        f"📱 Raqamingiz: <code>{phone}</code>\n\n"
        f"<i>Bosh Admin tasdiqlashi bilan shaxsiy kabinetingiz ochiladi.</i>",
        call.message.chat.id,
        call.message.message_id
    )
    bot.answer_callback_query(call.id, "So'rov yuborildi")
    
    admins = database.get_all_admins()
    admin_markup = types.InlineKeyboardMarkup(row_width=2)
    admin_markup.add(
        types.InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"appreq_{req_id}"),
        types.InlineKeyboardButton("❌ Rad etish", callback_data=f"rejreq_{req_id}")
    )
    un_str = f"@{call.from_user.username}" if call.from_user.username else "mavjud emas"
    admin_notice = (
        f"🔔 <b>YANGI O'QITUVCHI ULANISH SO'ROVI:</b>\n\n"
        f"👤 <b>O'qituvchi:</b> {teacher_name}\n"
        f"📱 <b>Telefon:</b> <code>{phone}</code>\n"
        f"💬 <b>Telegram:</b> {full_name} ({un_str})\n\n"
        f"Ushbu ustozga kirish huquqini berasizmi?"
    )
    for a_id in admins:
        try:
            bot.send_message(a_id, admin_notice, reply_markup=admin_markup)
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("appreq_"))
def handle_admin_approve(call):
    admin = database.get_user(call.from_user.id)
    if not admin or admin["role"] != "admin":
        return
    req_id = int(call.data.split("_")[1])
    req = database.approve_request(req_id)
    if req:
        bot.edit_message_text(f"✅ <b>TASDIQLANDI!</b>\n\n👤 Ustoz: <b>{req['teacher_name']}</b>\n📱 Tel: <code>{req['phone']}</code>", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(req["telegram_id"], f"🎉 <b>Arizangiz tasdiqlandi, {req['teacher_name']}!</b>\nShaxsiy kabinetingiz faollashtirildi:", reply_markup=get_teacher_keyboard())
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("rejreq_"))
def handle_admin_reject(call):
    admin = database.get_user(call.from_user.id)
    if not admin or admin["role"] != "admin":
        return
    req_id = int(call.data.split("_")[1])
    database.reject_request(req_id)
    bot.edit_message_text("❌ <b>So'rov rad etildi.</b>", call.message.chat.id, call.message.message_id)

# --- SINF JADVALI KO'RISH ---

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

# --- KO'P SINFLI OBUNA TIZIMI (OTA-ONALAR VA O'QUVCHILAR UCHUN) ---

@bot.message_handler(func=lambda msg: msg.text in ["🔔 Eslatmalarga obuna bo'lish", "🔔 Mening obunalarim"])
def handle_subscriptions_menu(message):
    uid = message.from_user.id
    database.update_activity(uid)
    subs = database.get_user_subscriptions(uid)
    text = "🔔 <b>DARS ESLATMALARIGA OBUNA BO'LISH</b>\n\n"
    if subs:
        text += f"✅ <b>Hozir ulangan sinflaringiz:</b> {', '.join(subs)}\n\n"
        text += "<i>Har oqshom soat 20:00 da ushbu sinflarning ertangi dars jadvali bitta xabarda yuboriladi.</i>\n\n"
    else:
        text += "❌ Siz hali hech qaysi sinfga obuna bo'lmadingiz.\n\n"
    text += "Farzandlaringiz sinflarini tanlash yoki o'chirish uchun parallel sinfni bosing:"
    bot.send_message(message.chat.id, text, reply_markup=get_grade_parallels_keyboard(sub_mode=True))

@bot.callback_query_handler(func=lambda call: call.data.startswith("subgrd_"))
def handle_sub_grade_parallel(call):
    val = call.data.replace("subgrd_", "")
    if val == "back":
        bot.edit_message_text("🔔 <b>Obuna uchun kerakli parallel sinfni tanlang:</b>", call.message.chat.id, call.message.message_id, reply_markup=get_grade_parallels_keyboard(True))
    else:
        user_subs = database.get_user_subscriptions(call.from_user.id)
        bot.edit_message_text(f"🏫 <b>{val}-sinflar:</b>\nSinf ustiga bosib obunani qo'shing yoki o'chiring:", call.message.chat.id, call.message.message_id, reply_markup=get_classes_in_grade_keyboard(val, True, user_subs))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("togglesub_"))
def handle_sub_toggle(call):
    parts = call.data.split("_")
    cls, gr = parts[1], parts[2]
    uid = call.from_user.id
    current_subs = database.get_user_subscriptions(uid)
    
    if cls in current_subs:
        database.remove_class_subscription(uid, cls)
        bot.answer_callback_query(call.id, f"{cls} obunasi o'chirildi")
    else:
        if len(current_subs) >= 5:
            bot.answer_callback_query(call.id, "Maksimal 5 tagacha sinfga obuna bo'lish mumkin!", show_alert=True)
            return
        database.add_class_subscription(uid, cls)
        bot.answer_callback_query(call.id, f"✅ {cls} sinf muvaffaqiyatli qo'shildi!")
        
    updated_subs = database.get_user_subscriptions(uid)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=get_classes_in_grade_keyboard(gr, True, updated_subs))

# --- JONLI STATISTIKA VA INFOGRAFIKA (ADMIN UCHUN) ---

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
    for idx, tc in enumerate(st["top_classes"], 1):
        top_cls_str += f"   {idx}. <b>{tc['class_name']}</b> — {tc['cnt']} obunachi\n"
    if not top_cls_str:
        top_cls_str = "   <i>Hozircha obunachilar yo'q</i>\n"

    stat_text = (
        f"📊 <b>«USTOZ AI» JONLI TIZIM STATISTIKASI:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 <b>Foydalanuvchilar qatlami:</b>\n"
        f"• 👑 Adminlar: <b>{st['admins']} nafar</b>\n"
        f"• 👨‍🏫 Ulangan o'qituvchilar: <b>{st['teachers']} nafar</b>\n"
        f"• 🎒 O'quvchi va ota-onalar: <b>{st['students']} nafar</b>\n"
        f"• 🌐 Jami qayd etilganlar: <b>{st['total_users']} nafar</b>\n\n"
        f"⚡ <b>Bugungi faollik:</b>\n"
        f"<code>[{make_bar(st['active_today'], max(st['total_users'], 1))}]</code>\n"
        f"Bugun botdan foydalandi: <b>{st['active_today']} kishi</b>\n\n"
        f"🔔 <b>Sinf eslatmalari holati:</b>\n"
        f"• Obuna bo'lgan oilalar: <b>{st['subscribed_users']} ta</b>\n"
        f"• Jami qo'shilgan sinflar: <b>{st['total_subs']} ta</b>\n\n"
        f"🏆 <b>Eng ommabop sinflar:</b>\n{top_cls_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Oxirgi yangilanish vaqti: {datetime.now(UZ_TZ).strftime('%H:%M:%S')}</i>"
    )
    bot.send_message(message.chat.id, stat_text)

# --- 2 BOSQICHLI XABAR YUBORISH VA HAMMADAN O'CHIRISH (RECALL) ---

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
    bot.send_message(
        message.chat.id,
        "📢 <b>E'lon yuborish bo'limi:</b>\n\nXabarni kimlarga yubormoqchisiz? Maqsadli guruhni tanlang:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("bcfilter_"))
def handle_bc_filter_select(call):
    target = call.data.replace("bcfilter_", "")
    USER_STATES[call.from_user.id] = {"action": "broadcast_text", "target": target}
    titles = {
        "teachers": "👨‍🏫 O'qituvchilarga",
        "students": "🎒 O'quvchi va ota-onalarga",
        "all": "📢 Butun maktabga"
    }
    bot.edit_message_text(
        f"📝 <b>Guruh: {titles.get(target)}</b>\n\nYubormoqchi bo'lgan xabaringiz matnini shu yerga yozing:\n\n<i>Bekor qilish: /cancel</i>",
        call.message.chat.id,
        call.message.message_id
    )
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda msg: msg.from_user.id in USER_STATES and USER_STATES[msg.from_user.id].get("action") == "broadcast_text")
def handle_bc_preview(message):
    uid = message.from_user.id
    target = USER_STATES[uid]["target"]
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
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Agar matn va qabul qiluvchilar to'g'ri bo'lsa, tasdiqlang:</i>",
        reply_markup=preview_markup
    )

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
        f"⚠️ <i>Agar xabar adashib yuborilgan bo'lsa, quyidagi tugma orqali uni hammadan butunlay o'chirib tashlashingiz mumkin:</i>",
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
    bot.edit_message_text(
        f"🗑 <b>XABAR BEKOR QILINDI VA O'CHIRILDI!</b>\n\n"
        f"Ushbu e'lon barcha <b>{deleted_count} ta chatdan</b> butunlay o'chirib yuborildi.",
        call.message.chat.id,
        call.message.message_id
    )
    bot.answer_callback_query(call.id, "Xabar barchadan o'chirildi!")

# --- O'QITUVCHILAR VA ADMIN UCHUN SHAXSIY BO'LIMLAR ---

def format_day_schedule(teacher_name, day):
    t = database.get_teacher_schedule(teacher_name)
    if not t:
        return f"❌ Jadval topilmadi."
    sched = t["schedule"].get(day, {})
    subj_str = ", ".join(t["subjects"]) if t["subjects"] else "Fan"
    text = f"📅 <b>{day.upper()} — DARS JADVALI</b>\n"
    text += f"👤 <b>Ustoz:</b> {t['name']} | 📚 <b>Fan:</b> {subj_str}\n\n"
    s1 = []
    for p in range(1, 7):
        e = sched.get(p) or sched.get(str(p)) or []
        if e:
            s1.append(f"• <b>{p}-dars</b> (<code>{config.SMENA1_TIMES[p]}</code>): <b>{', '.join([x['class'] for x in e])}</b>")
    text += "🔵 <b>I - SMENA (08:00 - 13:05):</b>\n" + ("\n".join(s1) if s1 else "<i>Bugun 1-smenada dars yo'q</i>") + "\n\n"
    s2 = []
    for p in range(1, 7):
        slot = config.SMENA2_TIMES[p]["slot"]
        t_str = config.SMENA2_TIMES[p]["time"]
        e = sched.get(slot) or sched.get(str(slot)) or []
        if e:
            s2.append(f"• <b>{p}-dars</b> (<code>{t_str}</code>): <b>{', '.join([x['class'] for x in e])}</b>")
    text += "🟢 <b>II - SMENA (13:10 - 18:10):</b>\n" + ("\n".join(s2) if s2 else "<i>Bugun 2-smenada dars yo'q</i>") + "\n\n"
    text += f"📊 <b>Bugungi jami dars: {len(s1) + len(s2)} soat</b>"
    return text

def format_week_schedule(teacher_name):
    t = database.get_teacher_schedule(teacher_name)
    if not t:
        return "❌ Jadval topilmadi."
    text = f"🗓️ <b>HAFTALIK TO'LIQ DARS JADVALI</b>\n👤 <b>Ustoz:</b> {t['name']}\n━━━━━━━━━━━━━━━━━━━━\n\n"
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
        text += f"📅 <b>{d}:</b>\n" + ("\n".join([f"  • {i}" for i in dl]) if dl else "  <i>Dars yo'q</i>") + "\n\n"
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
    t = database.get_teacher_schedule(user["teacher_name"] if user else "Boboev J")
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
    togs = database.get_togaraklar(t["name"])
    text = (
        f"📊 <b>HAFTALIK YUKLAMA HISOBOTI</b>\n\n"
        f"👤 <b>Ustoz:</b> {t['name']}\n"
        f"📚 <b>Fan:</b> {', '.join(t['subjects'])}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔵 I-Smena: {s1} soat | 🟢 II-Smena: {s2} soat\n"
        f"📖 O'quv darslari: {s1+s2} soat\n"
        f"🎨 To'garaklar: {len(togs)} soat\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⭐ <b>JAMI YUKLAMA: {s1+s2+len(togs)} SOAT</b>"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda msg: msg.text == "🎨 To'garaklarim")
def handle_teacher_clubs(message):
    user = database.get_user(message.from_user.id)
    togs = database.get_togaraklar(user["teacher_name"] if user else "Boboev J")
    if not togs:
        bot.send_message(message.chat.id, "Hozircha to'garak biriktirilmagan.")
        return
    text = f"🎨 <b>TO'GARAKLAR:</b>\n\n"
    for idx, tg in enumerate(togs, 1):
        text += f"{idx}. <b>{tg['name']}</b> ({tg['subject']})\n   • Kuni: {tg['day']} | Vaqti: {tg['time']}\n\n"
    bot.send_message(message.chat.id, text)

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

# --- AI METODIK YORDAMCHI TUGMASI ---

@bot.message_handler(func=lambda msg: msg.text in ["💡 Metodik AI yordamchi", "💡 Savol-javob (AI)"])
def handle_ai_prompt(message):
    bot.send_message(
        message.chat.id,
        "💡 <b>Ustoz AI — Aqlli pedagogik yordamchi ishga tushdi!</b>\n\n"
        "Istalgan savolingiz, fanni va dars mavzusini yozing. Masalan:\n"
        "• <i>«7-sinf Fizika: Bosim mavzusida qiziqarli dars ishlanmasi tuzib ber»</i>\n"
        "• <i>«5-sinf Musiqa: 5 talik qiziqarli test savollari tuzib ber»</i>\n\n"
        "Savolingizni shu yerga yozib yuboring:"
    )

@bot.message_handler(func=lambda msg: msg.text in ["✍️ Talab va takliflar", "✍️ Taklif bildirish"])
def handle_feedback_request(message):
    USER_STATES[message.from_user.id] = {"action": "send_feedback"}
    bot.send_message(
        message.chat.id,
        "✍️ Maktab ma'muriyatiga fikr, ariza yoki taklifingizni yozib yuboring (bekor qilish: /cancel):"
    )

@bot.message_handler(func=lambda msg: msg.from_user.id in USER_STATES and USER_STATES[msg.from_user.id].get("action") == "send_feedback")
def handle_feedback_delivery(message):
    uid = message.from_user.id
    del USER_STATES[uid]
    user = database.get_user(uid)
    name = user["full_name"] if user else message.from_user.first_name
    ph = user["phone"] if (user and user.get("phone")) else "Noma'lum"
    notice = f"📩 <b>YANGI MUROJAAT:</b>\n\n👤 Yuboruvchi: <b>{name}</b>\n📱 Tel: <code>{ph}</code>\n💬 Matn:\n{message.text}"
    for a in database.get_all_admins():
        try:
            bot.send_message(a, notice)
        except Exception:
            pass
    bot.send_message(message.chat.id, "✅ Rahmat! Murojaatingiz ma'muriyatga yetkazildi.")

@bot.message_handler(func=lambda msg: msg.text == "👨‍💻 Dasturchi va ma'lumot")
def handle_dev_info(message):
    bot.send_message(
        message.chat.id,
        "👨‍💻 <b>Loyiha muallifi:</b> Boboev Jasurbek\n"
        "🏫 <b>Muassasa:</b> 80-umumiy o'rta ta'lim maktabi\n"
        "🤖 <b>Tizim:</b> «Ustoz AI» — Maktab boshqaruv va ta'lim intellekti"
    )

# --- AVTOMATIK KECHKI DARS ESLATMASI TIZIMI ---

def send_all_daily_reminders(target_day=None):
    now = datetime.now(UZ_TZ)
    DAYS_MAP = {0: "Dushanba", 1: "Seshanba", 2: "Chorshanba", 3: "Payshanba", 4: "Juma", 5: "Shanba", 6: "Yakshanba"}
    NEXT_DAY = {
        "Dushanba": "Seshanba", "Seshanba": "Chorshanba", "Chorshanba": "Payshanba",
        "Payshanba": "Juma", "Juma": "Shanba", "Shanba": "Dushanba", "Yakshanba": "Dushanba"
    }
    if not target_day:
        today_name = DAYS_MAP.get(now.weekday(), "Dushanba")
        target_day = NEXT_DAY.get(today_name, "Dushanba")

    # 1. O'qituvchilarga shaxsiy dars jadvalini yuborish
    teachers = database.get_all_connected_users()
    t_count = 0
    for u in teachers:
        t_name = u.get("teacher_name")
        if not t_name:
            continue
        sched = format_day_schedule(t_name, target_day)
        msg = (
            f"🌙 <b>Xayrli kech, {u['full_name']}!</b>\n\n"
            f"🔔 <b>Ertangi ({target_day}) kungi dars jadvalingiz:</b>\n\n"
            f"{sched}\n\n"
            f"<i>Ertangi darslaringizga omad tilaymiz!</i>"
        )
        try:
            bot.send_message(u["telegram_id"], msg)
            t_count += 1
        except Exception:
            pass

    # 2. Ota-onalar va o'quvchilarga (bir nechta sinfni bitta xabarga jamlab) yuborish
    subs = database.get_all_active_subscriptions()
    p_count = 0
    for chat_id, class_list in subs.items():
        if not class_list:
            continue
        text = f"🌙 <b>Assalomu alaykum!</b>\n\n🔔 <b>Ertangi ({target_day}) kungi sinflar jadvali:</b>\n\n"
        for c in class_list:
            text += format_class_day_schedule(c, target_day) + "\n\n"
        text += "<i>Farzandlaringizga o'qishlarida muvaffaqiyat tilaymiz!</i>"
        try:
            bot.send_message(chat_id, text)
            p_count += 1
        except Exception:
            pass
            
    return t_count, p_count

def reminder_scheduler():
    last_sent_date = ""
    while True:
        try:
            now = datetime.now(UZ_TZ)
            today_str = now.strftime("%Y-%m-%d")
            # Har oqshom soat 20:00 da (Toshkent vaqti)
            if now.hour == 20 and last_sent_date != today_str:
                send_all_daily_reminders()
                last_sent_date = today_str
        except Exception as err:
            print(f"Scheduler error: {err}")
        time.sleep(30)

@bot.message_handler(commands=['test_reminder'])
def handle_test_reminder(message):
    admin = database.get_user(message.from_user.id)
    if not admin or admin["role"] != "admin":
        return
    bot.send_message(message.chat.id, "⏳ Eslatma yuborish sinovi boshlanmoqda...")
    tc, pc = send_all_daily_reminders()
    bot.send_message(message.chat.id, f"✅ Eslatma yuborildi:\n• O'qituvchilarga: <b>{tc} nafar</b>\n• Ota-onalar/O'quvchilarga: <b>{pc} oilaga</b>")

# Umumiy savollarga AI orqali javob berish
@bot.message_handler(func=lambda msg: True)
def handle_ai_text(message):
    database.update_activity(message.from_user.id, message.from_user.first_name)
    if ai_model:
        try:
            bot.send_chat_action(message.chat.id, 'typing')
            prompt = (
                "Sen O'zbekistondagi 80-umumiy o'rta ta'lim maktabining aqlli pedagogik AI yordamchisisan. "
                "O'qituvchilar, o'quvchilar va ota-onalarning savollariga o'zbek tilida, muloyim, aniq va professional darajada javob ber.\n\n"
                f"Savol: {message.text}"
            )
            res = ai_model.generate_content(prompt)
            if res and res.text:
                bot.reply_to(message, res.text)
                return
        except Exception as err:
            bot.reply_to(message, f"⚠️ AI javob berishda xatolik yuz berdi: {err}")
            return
            
    bot.reply_to(message, "Iltimos, quyidagi menyu tugmalaridan foydalaning:", reply_markup=get_student_keyboard())

# --- ISHGA TUSHIRISH ---
if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    Thread(target=reminder_scheduler, daemon=True).start()
    print("80-maktab 'Ustoz AI' to'liq boshqaruv tizimi ishga tushdi...")
    bot.infinity_polling(skip_pending=True)
