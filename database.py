import sqlite3
import os
import json
from datetime import date

DB_PATH = os.path.join(os.path.dirname(__file__), "database", "faceattend.db")

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = get_db()
    db.executescript("""
        -- TEACHERS
        CREATE TABLE IF NOT EXISTS teachers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            department TEXT DEFAULT 'Computer Science',
            subject_code TEXT,
            subject_name TEXT,
            contact_hours INTEGER DEFAULT 3,
            section TEXT DEFAULT 'K',
            room TEXT
        );

        -- STUDENTS
        CREATE TABLE IF NOT EXISTS students (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            usn TEXT UNIQUE NOT NULL,
            email TEXT,
            phone TEXT,
            section TEXT DEFAULT 'K',
            semester INTEGER DEFAULT 2,
            department TEXT DEFAULT 'CSE',
            cgpa REAL DEFAULT 0.0,
            address TEXT DEFAULT 'Bengaluru, Karnataka',
            joined_date TEXT DEFAULT 'Feb 2026',
            face_encoding TEXT,
            face_registered INTEGER DEFAULT 0
        );

        -- SUBJECTS
        CREATE TABLE IF NOT EXISTS subjects (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            short_name TEXT,
            contact_hours INTEGER DEFAULT 3,
            color TEXT DEFAULT '#2563EB'
        );

        -- ATTENDANCE RECORDS
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            usn TEXT NOT NULL,
            subject_code TEXT NOT NULL,
            date TEXT NOT NULL,
            status TEXT DEFAULT 'present',
            time_marked TEXT,
            marked_by TEXT,
            UNIQUE(usn, subject_code, date)
        );

        -- CIE MARKS
        CREATE TABLE IF NOT EXISTS cie_marks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            usn TEXT NOT NULL,
            subject_code TEXT NOT NULL,
            cie1 REAL DEFAULT 0,
            cie2 REAL DEFAULT 0,
            cie3 REAL DEFAULT 0,
            assignment REAL DEFAULT 0,
            UNIQUE(usn, subject_code)
        );

        -- NOTIFICATIONS
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            user_role TEXT NOT NULL,
            type TEXT DEFAULT 'info',
            title TEXT,
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            read INTEGER DEFAULT 0
        );

        -- TIMETABLE
        CREATE TABLE IF NOT EXISTS timetable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL,
            subject_code TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            slot_type TEXT DEFAULT 'lecture'
        );
    """)

    # Seed subjects
    subjects = [
        ("MAC21",  "Numerical Methods",                              "Num Methods",   6, "#2563EB"),
        ("CYC22",  "Applied Chemistry for Smart Systems",            "Chemistry",     6, "#10B981"),
        ("ESC23X", "Engineering Science Course-II",                  "Engg Science",  4, "#F59E0B"),
        ("PLC24",  "Python Programming for IT and Allied",           "Python",        5, "#7C3AED"),
        ("ETC25",  "Introduction to AI & Applications",              "Intro to AI",   3, "#EF4444"),
        ("HSCC26", "Communication Skills",                           "Comm Skills",   2, "#06B6D4"),
        ("AEC27",  "Interdisciplinary Project-Based Learning",       "Project",       2, "#EC4899"),
        ("HSCC28", "Constitution of India & Engineering Ethics",     "Constitution",  1, "#84CC16"),
    ]
    for s in subjects:
        db.execute("INSERT OR IGNORE INTO subjects (code,name,short_name,contact_hours,color) VALUES (?,?,?,?,?)", s)

    # Seed timetable
    timetable = [
        ("Monday",    "PLC24",   "9:00",  "10:50", "lab"),
        ("Monday",    "ETC25",   "11:05", "12:00", "lecture"),
        ("Monday",    "MAC21",   "12:50", "2:40",  "tutorial"),
        ("Tuesday",   "MAC21",   "9:00",  "9:55",  "lecture"),
        ("Tuesday",   "HSCC28",  "9:55",  "10:50", "lecture"),
        ("Tuesday",   "PLC24",   "11:05", "12:00", "lecture"),
        ("Tuesday",   "ETC25",   "12:50", "1:45",  "lecture"),
        ("Tuesday",   "CYC22",   "1:45",  "2:40",  "lecture"),
        ("Tuesday",   "ESC23X",  "2:40",  "3:35",  "lecture"),
        ("Wednesday", "HSCC26",  "9:00",  "9:55",  "lecture"),
        ("Wednesday", "ETC25",   "9:55",  "10:50", "lecture"),
        ("Wednesday", "MAC21",   "11:05", "12:00", "lecture"),
        ("Wednesday", "PLC24",   "12:50", "1:45",  "lecture"),
        ("Wednesday", "CYC22",   "1:45",  "2:40",  "lecture"),
        ("Thursday",  "AEC27",   "9:00",  "10:50", "lab"),
        ("Thursday",  "PLC24",   "11:05", "12:00", "lecture"),
        ("Thursday",  "HSCC26",  "12:50", "1:45",  "lecture"),
        ("Thursday",  "MAC21",   "1:45",  "2:40",  "lecture"),
        ("Friday",    "PLC24",   "9:00",  "9:55",  "lecture"),
        ("Friday",    "CYC22",   "9:55",  "10:50", "lecture"),
        ("Friday",    "CYC22",   "11:05", "12:50", "lab"),
        ("Friday",    "ESC23X",  "12:50", "1:45",  "lecture"),
        ("Saturday",  "MAC21",   "9:00",  "9:55",  "lecture"),
        ("Saturday",  "CYC22",   "9:55",  "10:50", "lecture"),
        ("Saturday",  "ESC23X",  "11:05", "12:50", "lab"),
    ]
    for t in timetable:
        db.execute("INSERT OR IGNORE INTO timetable (day,subject_code,start_time,end_time,slot_type) VALUES (?,?,?,?,?)", t)

    db.commit()
    db.close()
    print("✅ Database initialized — Ramaiah Institute of Technology")
