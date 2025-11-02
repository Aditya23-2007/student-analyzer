import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
import sqlite3
import shutil
import glob
import platform
from datetime import datetime

from auth_module import add_user, authenticate_user, list_users
from nlp_module import analyze_feedback, generate_wordcloud
from email_module import send_bulk

# ==============================
# CONFIG & CONSTANTS
# ==============================
ADMIN_CODE = "admin123"
st.set_page_config(page_title="Student Analyzer Dashboard", page_icon="🎓", layout="wide")

# ---------------------
# Styles
# ---------------------
st.markdown("""
    <style>
        .main-header {
            width: 100%;
            background-color: #DDE4FF;
            border-radius: 12px;
            padding: 1rem;
            margin-bottom: 1.0rem;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 3px 8px rgba(0,0,0,0.08);
        }
        .nav-radio > div { display:flex; justify-content:center; gap:12px; }
        .nav-radio label { background:#E8EAF6; padding:6px 12px; border-radius:10px; font-weight:600; cursor:pointer;}
        .nav-radio label:hover { transform: scale(1.03); }
    </style>
""", unsafe_allow_html=True)

st.markdown("<div class='main-header'><h1>🎓 Student Analyzer Dashboard</h1></div>", unsafe_allow_html=True)

# ---------------------
# Session initialization
# ---------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.student_data = None

# ---------------------
# AUTHENTICATION
# ---------------------
if not st.session_state.logged_in:
    st.write("## 🔐 Login / Sign up")
    auth_choice = st.radio("Choose", ["Login", "Sign Up"], index=0, key="auth_choice")

    if auth_choice == "Sign Up":
        st.subheader("Create an account")
        name = st.text_input("Full name", key="signup_name")
        email = st.text_input("Email (Gmail preferred)", key="signup_email")
        password = st.text_input("Password", type="password", key="signup_pw")
        password2 = st.text_input("Confirm password", type="password", key="signup_pw2")
        admin_code = st.text_input("Admin code (only if you're admin)", type="password", key="signup_admin")

        if st.button("Create account"):
            if not name or not email or not password:
                st.error("Please fill all fields.")
            elif password != password2:
                st.error("Passwords do not match.")
            else:
                is_admin = 1 if admin_code == ADMIN_CODE else 0
                ok = add_user(name, email, password, is_admin)
                if ok:
                    st.success("Account created successfully! Please login.")
                else:
                    st.error("Account creation failed (email may already be registered).")

        st.info("Note: Gmail App Passwords are only needed for sending emails (never stored).")

    else:
        st.subheader("Login to your account")
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_pw")

        if st.button("Login"):
            user = authenticate_user(email, password)
            if user:
                st.session_state.logged_in = True
                st.session_state.user = user
                st.success(f"Welcome, {user['name']}!")
                st.rerun()
            else:
                st.error("Invalid credentials.")
    st.stop()

# ---------------------
# MAIN APP
# ---------------------
user = st.session_state.user
if not user:
    st.error("User session expired. Please login again.")
    st.stop()

st.sidebar.markdown(f"**Logged in as:** {user['name']}  \n{user['email']}")
st.sidebar.markdown(f"**Role:** {'Admin' if user.get('is_admin') else 'User'}")

menu = ["Home", "Data Upload", "Marks & Attendance", "Feedback Analyzer", "Notifications", "Admin"]
selected = st.radio("", menu, horizontal=True, key="main_nav", label_visibility="collapsed")

# ---------------------
# HOME
# ---------------------
if selected == "Home":
    st.title(f"Welcome {user['name']} 👋")
    st.write("""
    This platform helps analyze attendance, marks, and feedback.
    Upload student data and generate insights easily.
    """)

# ---------------------
# DATA UPLOAD
# ---------------------
elif selected == "Data Upload":
    st.title("📁 Upload Student Data")
    uploaded = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
    if uploaded:
        df = pd.read_excel(uploaded)
        st.session_state.student_data = df
        st.success("Student data loaded successfully!")
        st.dataframe(df.head())
        os.makedirs("data", exist_ok=True)
        df.to_excel("data/students_latest.xlsx", index=False)

# ---------------------
# MARKS & ATTENDANCE
# ---------------------
elif selected == "Marks & Attendance":
    st.title("📊 Marks & Attendance")
    if st.session_state.student_data is None:
        st.info("Please upload data first.")
    else:
        df = st.session_state.student_data
        st.dataframe(df)
        if "attendance" in df.columns:
            avg_att = df["attendance"].mean()
            st.metric("Average Attendance (%)", f"{avg_att:.2f}")
        if "marks" in df.columns:
            avg_marks = df["marks"].mean()
            st.metric("Average Marks", f"{avg_marks:.2f}")

# ---------------------
# FEEDBACK ANALYZER
# ---------------------
elif selected == "Feedback Analyzer":
    st.title("🧠 Feedback Analyzer")
    uploaded_fb = st.file_uploader("Upload feedback file (.xlsx)", type=["xlsx"])
    if uploaded_fb:
        df_fb = pd.read_excel(uploaded_fb)
        if "feedback" not in df_fb.columns:
            st.error("Excel must have a 'feedback' column.")
        else:
            st.dataframe(df_fb.head())
            if st.button("Analyze Feedback"):
                results_list, top_words = analyze_feedback(df_fb["feedback"].astype(str).tolist())
                results_df = pd.DataFrame(results_list)
                st.subheader("Sentiment Results")
                st.dataframe(results_df)
                st.bar_chart(results_df["sentiment"].value_counts())
                st.subheader("Top Keywords")
                if top_words:
                    st.table(pd.DataFrame(top_words, columns=["word", "count"]))
                wc = generate_wordcloud(df_fb["feedback"].astype(str).tolist())
                if wc:
                    st.image(wc, caption="Word Cloud")

# ---------------------
# NOTIFICATIONS
# ---------------------
elif selected == "Notifications":
    st.title("📬 Notifications / Email Alerts")
    if st.session_state.student_data is None:
        st.info("Upload data first.")
    else:
        df = st.session_state.student_data
        low_att = df[df["attendance"] < 75] if "attendance" in df.columns else pd.DataFrame()
        low_marks = df[df["marks"] < 35] if "marks" in df.columns else pd.DataFrame()
        alerts = pd.concat([low_att, low_marks]).drop_duplicates()
        if alerts.empty:
            st.success("No alerts required.")
        else:
            st.warning(f"{len(alerts)} students flagged.")
            st.dataframe(alerts)
            app_pw = st.text_input("Gmail App Password", type="password")
            if st.button("Send Alerts"):
                if app_pw:
                    res = send_bulk(alerts, user["email"], app_pw, "Performance Alert",
                                    "Dear {name},\nPlease improve attendance/marks.")
                    ok = sum(1 for r in res if r["ok"])
                    st.success(f"Sent {ok}/{len(res)} emails.")
                else:
                    st.error("App password required.")

# ---------------------
# ADMIN PANEL
# ---------------------
elif selected == "Admin":
    st.title("👑 Admin Control Center")

    if not user.get("is_admin"):
        st.error("Admin access only.")
    else:
        st.success("Welcome, Admin! You have full control.")
        db_path = "data/users.db"

        # Load users
        def load_users():
            if not os.path.exists(db_path):
                return pd.DataFrame(columns=["id", "name", "email", "is_admin"])
            conn = sqlite3.connect(db_path)
            df = pd.read_sql_query("SELECT * FROM users", conn)
            conn.close()
            return df

        users_df = load_users()
        st.subheader("👥 User Management")
        if not users_df.empty:
            st.dataframe(users_df)
            selected_uid = st.selectbox("Select user ID to manage", users_df["id"])
            action = st.radio("Action", ["Promote to Admin", "Demote", "Delete"])
            if action == "Promote to Admin" and st.button("Confirm Promote"):
                conn = sqlite3.connect(db_path)
                conn.execute("UPDATE users SET is_admin=1 WHERE id=?", (selected_uid,))
                conn.commit()
                conn.close()
                st.success("User promoted.")
            elif action == "Demote" and st.button("Confirm Demote"):
                conn = sqlite3.connect(db_path)
                conn.execute("UPDATE users SET is_admin=0 WHERE id=?", (selected_uid,))
                conn.commit()
                conn.close()
                st.info("User demoted.")
            elif action == "Delete" and st.button("Confirm Delete"):
                conn = sqlite3.connect(db_path)
                conn.execute("DELETE FROM users WHERE id=?", (selected_uid,))
                conn.commit()
                conn.close()
                st.warning("User deleted.")
        else:
            st.info("No users in database.")

        # Email broadcast
        st.markdown("---")
        st.subheader("✉️ Email Broadcast")
        admin_pw = st.text_input("Admin Gmail App Password", type="password")
        subj = st.text_input("Subject", "Announcement from Admin")
        body = st.text_area("Email Body", "Dear {name},\n\nThis is an important message.")
        if st.button("Send Email to All Users"):
            if admin_pw:
                res = send_bulk(users_df, user["email"], admin_pw, subj, body)
                ok = sum(1 for r in res if r["ok"])
                st.success(f"Sent {ok}/{len(res)} emails.")
            else:
                st.error("Password required.")

        # Backup & maintenance
        st.markdown("---")
        st.subheader("🛠 Maintenance Tools")
        if st.button("Backup user DB"):
            os.makedirs("backups", exist_ok=True)
            backup_path = f"backups/users_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy2(db_path, backup_path)
            st.success(f"Backup created: {backup_path}")

        if st.button("Clean temp files"):
            count = 0
            for root, dirs, files in os.walk("."):
                for d in dirs:
                    if d == "__pycache__":
                        shutil.rmtree(os.path.join(root, d))
                        count += 1
            st.success(f"Removed {count} temp directories.")

        st.markdown("---")
        st.write(f"System Info: Python {platform.python_version()} | {platform.platform()}")

# ---------------------
# LOGOUT
# ---------------------
st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.session_state.user = None
    st.rerun()
