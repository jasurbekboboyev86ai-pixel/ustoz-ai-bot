import os
import json
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_database.db")
JSON_PATH = os.path.join(os.path.dirname(__file__), "teachers_data.json")

def get_connection():
    return sqlite3.connect(DB_PATH)

def get_user(telegram_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id, phone, full_name, teacher_name, role FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "telegram_id": row[0],
            "phone": row[1],
            "full_name": row[2],
            "teacher_name": row[3],
            "role": row[4]
        }
    return None

def is_phone_admin(phone, admin_phones):
    clean_p = phone.replace("+", "").replace(" ", "").replace("-", "").strip()
    for ap in admin_phones:
        clean_ap = ap.replace("+", "").replace(" ", "").replace("-", "").strip()
        if clean_p.endswith(clean_ap[-9:]):
            return True
    return False

def register_user(telegram_id, phone, full_name, teacher_name, role):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO users (telegram_id, phone, full_name, teacher_name, role)
        VALUES (?, ?, ?, ?, ?)
    """, (telegram_id, phone, full_name, teacher_name, role))
    conn.commit()
    conn.close()

def create_pending_request(telegram_id, phone, full_name, teacher_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO pending_requests (telegram_id, phone, full_name, teacher_name, status)
        VALUES (?, ?, ?, ?, 'pending')
    """, (telegram_id, phone, full_name, teacher_name))
    req_id = cur.lastrowid
    conn.commit()
    conn.close()
    return req_id

def get_pending_request(req_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, telegram_id, phone, full_name, teacher_name, status FROM pending_requests WHERE id = ?", (req_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "telegram_id": row[1],
            "phone": row[2],
            "full_name": row[3],
            "teacher_name": row[4],
            "status": row[5]
        }
    return None

def approve_request(req_id):
    req = get_pending_request(req_id)
    if not req:
        return None
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE pending_requests SET status = 'approved' WHERE id = ?", (req_id,))
    cur.execute("""
        INSERT OR REPLACE INTO users (telegram_id, phone, full_name, teacher_name, role)
        VALUES (?, ?, ?, ?, 'teacher')
    """, (req["telegram_id"], req["phone"], req["full_name"], req["teacher_name"]))
    conn.commit()
    conn.close()
    return req

def reject_request(req_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE pending_requests SET status = 'rejected' WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()

def get_all_admins():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM users WHERE role = 'admin'")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_teachers_list():
    if os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_teachers_list(data):
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_teacher_schedule(teacher_name):
    teachers = get_teachers_list()
    # Normalize name search
    t_clean = teacher_name.lower().strip()
    found = None
    for t in teachers:
        if t["name"].lower().strip() == t_clean or t_clean in t["name"].lower().strip():
            found = json.loads(json.dumps(t))
            break
    if not found:
        return None

    # Apply database custom overrides if any
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT day, slot, classes FROM custom_overrides WHERE teacher_name = ?", (found["name"],))
    for day, slot, cls_str in cur.fetchall():
        if day not in found["schedule"]:
            found["schedule"][day] = {}
        if not cls_str or cls_str == "-":
            found["schedule"][day][str(slot)] = []
        else:
            classes = [c.strip() for c in cls_str.split(",") if c.strip()]
            entries = [{"class": c, "subject": found["subjects"][0] if found["subjects"] else "Dars", "time": ""} for c in classes]
            found["schedule"][day][str(slot)] = entries
    conn.close()
    return found

def set_override(teacher_name, day, slot, classes_str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO custom_overrides (teacher_name, day, slot, classes)
        VALUES (?, ?, ?, ?)
    """, (teacher_name, day, str(slot), classes_str))
    conn.commit()
    conn.close()

def get_togaraklar(teacher_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, subject, day, time FROM togaraklar WHERE teacher_name LIKE ?", (f"%{teacher_name.strip()}%",))
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "subject": r[2], "day": r[3], "time": r[4]} for r in rows]

def get_all_users_count():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT role, COUNT(*) FROM users GROUP BY role")
    res = dict(cur.fetchall())
    conn.close()
    return res

def get_all_connected_users():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id, phone, full_name, teacher_name, role FROM users")
    rows = cur.fetchall()
    conn.close()
    return [{"telegram_id": r[0], "phone": r[1], "full_name": r[2], "teacher_name": r[3], "role": r[4]} for r in rows]
