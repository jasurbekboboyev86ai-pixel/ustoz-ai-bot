# -*- coding: utf-8 -*-
"""
80-maktab "Ustoz AI" - Ma'lumotlar bazasi moduli
Muallif: Boboev Jasurbek & Ustoz AI jamoasi
"""

import sqlite3
import json
import os
from datetime import datetime, timezone, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_database.db")
JSON_PATH = os.path.join(os.path.dirname(__file__), "teachers_data.json")
UZ_TZ = timezone(timedelta(hours=5))

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Foydalanuvchilar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            phone TEXT,
            full_name TEXT,
            teacher_name TEXT,
            role TEXT DEFAULT 'student',
            registered_at TEXT,
            last_active TEXT
        )
    """)
    
    # Tasdiqlashni kutayotgan o'qituvchilar so'rovlari
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            phone TEXT,
            full_name TEXT,
            teacher_name TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)
    
    # Dars jadvaliga kiritilgan qo'lda o'zgartirishlar
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_name TEXT,
            day TEXT,
            slot INTEGER,
            new_class TEXT
        )
    """)

    # O'quvchilar va ota-onalar sinf obunalari (1 kishi bir nechta sinfga ulanishi mumkin)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            class_name TEXT,
            created_at TEXT,
            UNIQUE(telegram_id, class_name)
        )
    """)

    # Ommaviy xabarlar tarixi va adashib ketganda o'chirish (Recall) xotirasi
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            target_group TEXT,
            message_text TEXT,
            sent_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broadcast_id INTEGER,
            chat_id INTEGER,
            message_id INTEGER
        )
    """)
    
    conn.commit()
    conn.close()

# Foydalanuvchi faolligini qayd qilish
def update_activity(telegram_id, full_name=""):
    conn = get_db()
    now_str = datetime.now(UZ_TZ).strftime("%Y-%m-%d %H:%M:%S")
    user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    if user:
        conn.execute("UPDATE users SET last_active = ? WHERE telegram_id = ?", (now_str, telegram_id))
    else:
        conn.execute(
            "INSERT INTO users (telegram_id, full_name, role, registered_at, last_active) VALUES (?, ?, 'student', ?, ?)",
            (telegram_id, full_name, now_str, now_str)
        )
    conn.commit()
    conn.close()

def is_phone_admin(phone, admin_phones):
    clean = "".join(filter(str.isdigit, phone))
    for ap in admin_phones:
        clean_ap = "".join(filter(str.isdigit, ap))
        if clean == clean_ap or clean.endswith(clean_ap) or clean_ap.endswith(clean):
            return True
    return False

def register_user(telegram_id, phone, full_name, teacher_name, role):
    conn = get_db()
    now_str = datetime.now(UZ_TZ).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO users (telegram_id, phone, full_name, teacher_name, role, registered_at, last_active)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            phone=excluded.phone,
            full_name=excluded.full_name,
            teacher_name=excluded.teacher_name,
            role=excluded.role,
            last_active=excluded.last_active
    """, (telegram_id, phone, full_name, teacher_name, role, now_str, now_str))
    conn.commit()
    conn.close()

def get_user(telegram_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    conn.close()
    return dict(user) if user else None

def get_all_connected_users():
    conn = get_db()
    users = conn.execute("SELECT * FROM users WHERE role IN ('admin', 'teacher')").fetchall()
    conn.close()
    return [dict(u) for u in users]

def get_all_admins():
    conn = get_db()
    admins = conn.execute("SELECT telegram_id FROM users WHERE role = 'admin'").fetchall()
    conn.close()
    return [a["telegram_id"] for a in admins]

# So'rovlar
def create_pending_request(telegram_id, phone, full_name, teacher_name):
    conn = get_db()
    now_str = datetime.now(UZ_TZ).strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pending_requests (telegram_id, phone, full_name, teacher_name, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (telegram_id, phone, full_name, teacher_name, now_str))
    req_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return req_id

def get_pending_request(req_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM pending_requests WHERE id = ?", (req_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def approve_request(req_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM pending_requests WHERE id = ? AND status = 'pending'", (req_id,)).fetchone()
    if not row:
        conn.close()
        return None
    req = dict(row)
    now_str = datetime.now(UZ_TZ).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE pending_requests SET status = 'approved' WHERE id = ?", (req_id,))
    conn.execute("""
        INSERT INTO users (telegram_id, phone, full_name, teacher_name, role, registered_at, last_active)
        VALUES (?, ?, ?, ?, 'teacher', ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            phone=excluded.phone,
            full_name=excluded.full_name,
            teacher_name=excluded.teacher_name,
            role='teacher',
            last_active=excluded.last_active
    """, (req['telegram_id'], req['phone'], req['full_name'], req['teacher_name'], now_str, now_str))
    conn.commit()
    conn.close()
    return req

def reject_request(req_id):
    conn = get_db()
    conn.execute("UPDATE pending_requests SET status = 'rejected' WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()

# Sinf obunalari (O'quvchilar va Ota-onalar)
def add_class_subscription(telegram_id, class_name):
    conn = get_db()
    now_str = datetime.now(UZ_TZ).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("INSERT INTO student_subscriptions (telegram_id, class_name, created_at) VALUES (?, ?, ?)",
                     (telegram_id, class_name.upper(), now_str))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def remove_class_subscription(telegram_id, class_name):
    conn = get_db()
    conn.execute("DELETE FROM student_subscriptions WHERE telegram_id = ? AND class_name = ?", (telegram_id, class_name.upper()))
    conn.commit()
    conn.close()

def get_user_subscriptions(telegram_id):
    conn = get_db()
    rows = conn.execute("SELECT class_name FROM student_subscriptions WHERE telegram_id = ? ORDER BY class_name ASC", (telegram_id,)).fetchall()
    conn.close()
    return [r["class_name"] for r in rows]

def get_all_active_subscriptions():
    conn = get_db()
    rows = conn.execute("SELECT telegram_id, class_name FROM student_subscriptions").fetchall()
    conn.close()
    subs = {}
    for r in rows:
        tid = r["telegram_id"]
        if tid not in subs:
            subs[tid] = []
        subs[tid].append(r["class_name"])
    return subs

# Xabarlar tarixi va O'chirish (Recall)
def save_broadcast(sender_id, target_group, message_text, sent_pairs):
    conn = get_db()
    now_str = datetime.now(UZ_TZ).strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO broadcast_history (sender_id, target_group, message_text, sent_at)
        VALUES (?, ?, ?, ?)
    """, (sender_id, target_group, message_text, now_str))
    b_id = cursor.lastrowid
    for chat_id, msg_id in sent_pairs:
        cursor.execute("INSERT INTO broadcast_recipients (broadcast_id, chat_id, message_id) VALUES (?, ?, ?)",
                       (b_id, chat_id, msg_id))
    conn.commit()
    conn.close()
    return b_id

def get_broadcast_recipients(broadcast_id):
    conn = get_db()
    rows = conn.execute("SELECT chat_id, message_id FROM broadcast_recipients WHERE broadcast_id = ?", (broadcast_id,)).fetchall()
    conn.close()
    return [(r["chat_id"], r["message_id"]) for r in rows]

def delete_broadcast_records(broadcast_id):
    conn = get_db()
    conn.execute("DELETE FROM broadcast_recipients WHERE broadcast_id = ?", (broadcast_id,))
    conn.execute("DELETE FROM broadcast_history WHERE id = ?", (broadcast_id,))
    conn.commit()
    conn.close()

# Jonli statistika va Infografika
def get_system_stats():
    conn = get_db()
    today_prefix = datetime.now(UZ_TZ).strftime("%Y-%m-%d")
    
    total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    total_teachers = conn.execute("SELECT COUNT(*) as c FROM users WHERE role = 'teacher'").fetchone()["c"]
    total_admins = conn.execute("SELECT COUNT(*) as c FROM users WHERE role = 'admin'").fetchone()["c"]
    total_students = conn.execute("SELECT COUNT(*) as c FROM users WHERE role = 'student'").fetchone()["c"]
    
    active_today = conn.execute("SELECT COUNT(*) as c FROM users WHERE last_active LIKE ?", (f"{today_prefix}%",)).fetchone()["c"]
    
    sub_count = conn.execute("SELECT COUNT(*) as c FROM student_subscriptions").fetchone()["c"]
    unique_subs = conn.execute("SELECT COUNT(DISTINCT telegram_id) as c FROM student_subscriptions").fetchone()["c"]
    
    top_classes = conn.execute("""
        SELECT class_name, COUNT(*) as cnt 
        FROM student_subscriptions 
        GROUP BY class_name 
        ORDER BY cnt DESC LIMIT 5
    """).fetchall()
    
    conn.close()
    return {
        "total_users": total_users,
        "teachers": total_teachers,
        "admins": total_admins,
        "students": total_students,
        "active_today": active_today,
        "total_subs": sub_count,
        "subscribed_users": unique_subs,
        "top_classes": [dict(tc) for tc in top_classes]
    }

# O'qituvchilar JSON ma'lumotlari
def get_teachers_list():
    if not os.path.exists(JSON_PATH):
        return []
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def get_teacher_schedule(teacher_name):
    teachers = get_teachers_list()
    for t in teachers:
        if t["name"].strip().lower() == teacher_name.strip().lower():
            return t
    return None

def set_override(teacher_name, day, slot, new_class):
    conn = get_db()
    conn.execute("INSERT INTO overrides (teacher_name, day, slot, new_class) VALUES (?, ?, ?, ?)",
                 (teacher_name, day, slot, new_class))
    conn.commit()
    conn.close()

def get_togaraklar(teacher_name):
    t = get_teacher_schedule(teacher_name)
    if not t:
        return []
    return t.get("togaraklar", [])

init_db()
