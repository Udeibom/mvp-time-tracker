import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import uuid
from datetime import datetime, date, timedelta
import matplotlib.pyplot as plt
import time

# -----------------------------
# Page Config
# -----------------------------
st.set_page_config(page_title="MVP Time Tracker", layout="wide")

# -----------------------------
# Authentication
# -----------------------------
def login_page():
    st.title("🔐 MVP Time Tracker Login")
    st.markdown("Welcome! Please log in as **Owner** or continue as **Guest**.")
    
    mode = st.radio("Login as:", ["Owner", "Guest"], horizontal=True)

    if mode == "Owner":
        user = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login = st.button("Login")

        if login:
            if (
                user == st.secrets["auth"]["owner_user"]
                and password == st.secrets["auth"]["owner_pass"]
            ):
                st.session_state["auth_mode"] = "owner"
                st.success("✅ Logged in as Owner")
                st.rerun()
            else:
                st.error("❌ Invalid credentials. Try again.")
    else:
        if st.button("Continue as Guest"):
            st.session_state["auth_mode"] = "guest"
            st.success("👋 Logged in as Guest (session data only)")
            st.rerun()


if "auth_mode" not in st.session_state:
    login_page()
    st.stop()

# -----------------------------
# Database Setup (Owner / Guest)
# -----------------------------
auth_mode = st.session_state["auth_mode"]

if auth_mode == "owner":
    st.sidebar.success("🟢 Owner mode (Google Sheets connected)")

    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
    SHEET_URL = st.secrets["sheet"]["url"]
    CREDS = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    gc = gspread.authorize(CREDS)
    sh = gc.open_by_url(SHEET_URL)

    try:
        ws = sh.worksheet("sessions")
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title="sessions", rows="100", cols="10")
        ws.append_row(
            [
                "id",
                "created_at",
                "date",
                "start_time",
                "end_time",
                "duration_hours",
                "project",
                "task_type",
                "notes",
                "focus_rating",
            ]
        )

    def add_session(record):
        row = [
            record["id"],
            record["created_at"],
            record["date"],
            record["start_time"],
            record["end_time"],
            record["duration_hours"],
            record.get("project"),
            record.get("task_type"),
            record.get("notes"),
            record.get("focus_rating"),
        ]
        ws.append_row(row)
        return True

    def fetch_df():
        data = ws.get_all_records()
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
        df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
        df["end_time"] = pd.to_datetime(df["end_time"], errors="coerce")
        df["duration_hours"] = pd.to_numeric(df["duration_hours"], errors="coerce").fillna(0)
        return df

else:
    st.sidebar.warning("🟡 Guest mode (data not saved)")

    if "guest_df" not in st.session_state:
        st.session_state["guest_df"] = pd.DataFrame(
            columns=[
                "id",
                "created_at",
                "date",
                "start_time",
                "end_time",
                "duration_hours",
                "project",
                "task_type",
                "notes",
                "focus_rating",
            ]
        )

    def add_session(record):
        st.session_state["guest_df"] = pd.concat(
            [st.session_state["guest_df"], pd.DataFrame([record])], ignore_index=True
        )
        return True

    def fetch_df():
        return st.session_state["guest_df"]

# -----------------------------
# Utility Functions
# -----------------------------
def combine_date_time(d: date, t) -> datetime:
    return datetime.combine(d, t)

def compute_duration_hours(start_dt: datetime, end_dt: datetime) -> float:
    if not isinstance(start_dt, datetime) or not isinstance(end_dt, datetime):
        return 0.0
    if end_dt < start_dt:
        end_dt += timedelta(days=1)
    seconds = (end_dt - start_dt).total_seconds()
    return round(seconds / 3600.0, 4)

# -----------------------------
# Sidebar Navigation
# -----------------------------
page = st.sidebar.radio("Go to", ["Log session", "Dashboard & Export"])

# -----------------------------
# Timer State
# -----------------------------
for key, val in {
    "timer_running": False,
    "timer_start": None,
    "timer_end": None,
    "timer_duration": 0.0,
    "timer_stopped": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# -----------------------------
# LOG SESSION PAGE
# -----------------------------
if page == "Log session":
    st.title("🕒 Log a Session")
    col1, col2 = st.columns([2, 1])

    # Manual entry
    with col1:
        with st.form("manual_form"):
            d = st.date_input("Date", value=date.today())
            s_time = st.time_input("Start time", datetime.now().time().replace(microsecond=0))
            e_time = st.time_input(
                "End time",
                (datetime.now() + timedelta(minutes=30)).time().replace(microsecond=0),
            )

            project = st.text_input("Project", value="Personal")
            task_type = st.text_input("Task type", value="Coding")
            notes = st.text_area("Notes")
            focus_rating = st.slider("Focus (1–5)", 1, 5, 3)

            start_dt = combine_date_time(d, s_time)
            end_dt = combine_date_time(d, e_time)
            duration_preview = compute_duration_hours(start_dt, end_dt)
            st.markdown(f"**Duration (hours):** {duration_preview}")

            if st.form_submit_button("Log session"):
                record = {
                    "id": uuid.uuid4().hex,
                    "created_at": datetime.utcnow().isoformat(),
                    "date": d.isoformat(),
                    "start_time": start_dt.isoformat(),
                    "end_time": end_dt.isoformat(),
                    "duration_hours": duration_preview,
                    "project": project,
                    "task_type": task_type,
                    "notes": notes,
                    "focus_rating": int(focus_rating),
                }
                add_session(record)
                st.success("✅ Session logged!")

    # Timer section
    with col2:
        st.subheader("Quick Timer")

        if not st.session_state.timer_running:
            if st.button("Start Timer"):
                st.session_state.timer_start = datetime.utcnow()
                st.session_state.timer_running = True
                st.session_state.timer_stopped = False
                st.session_state.timer_end = None
                st.session_state.timer_duration = 0.0
                st.success("⏱ Timer started!")
        else:
            start_dt = st.session_state.timer_start
            placeholder = st.empty()
            elapsed = datetime.utcnow() - start_dt
            hours = elapsed.total_seconds() / 3600
            placeholder.info(f"⏳ Elapsed time: **{hours:.3f} hours**")

            if st.button("Stop Timer"):
                end_dt = datetime.utcnow()
                duration_hours = compute_duration_hours(start_dt, end_dt)
                st.session_state.timer_end = end_dt
                st.session_state.timer_duration = duration_hours
                st.session_state.timer_running = False
                st.session_state.timer_stopped = True
                st.success(f"✅ Timer stopped. Duration: {duration_hours:.3f} hours")
                st.rerun()
            else:
                time.sleep(1)
                st.rerun()

        if st.session_state.timer_stopped:
            st.subheader("Log this Timer Session")
            start_dt = st.session_state.timer_start
            end_dt = st.session_state.timer_end
            duration_hours = st.session_state.timer_duration

            st.markdown(
                f"**Start:** {start_dt.strftime('%Y-%m-%d %H:%M:%S')} | "
                f"**End:** {end_dt.strftime('%Y-%m-%d %H:%M:%S')} | "
                f"**Duration:** {duration_hours:.3f} hours"
            )

            with st.form("timer_log_form"):
                project_t = st.text_input("Project", value="Personal")
                task_type_t = st.text_input("Task type", value="Coding")
                notes_t = st.text_area("Notes")
                focus_rating_t = st.slider("Focus (1–5)", 1, 5, 3)
                log_timer = st.form_submit_button("✅ Log Timer Session")

                if log_timer:
                    record = {
                        "id": uuid.uuid4().hex,
                        "created_at": datetime.utcnow().isoformat(),
                        "date": start_dt.date().isoformat(),
                        "start_time": start_dt.isoformat(),
                        "end_time": end_dt.isoformat(),
                        "duration_hours": duration_hours,
                        "project": project_t,
                        "task_type": task_type_t,
                        "notes": notes_t,
                        "focus_rating": int(focus_rating_t),
                    }
                    add_session(record)
                    st.success("✅ Timer session logged!")
                    st.session_state.timer_running = False
                    st.session_state.timer_stopped = False

# -----------------------------
# DASHBOARD PAGE
# -----------------------------
else:
    st.title("📊 Dashboard & Export")
    df = fetch_df()

    if df.empty:
        st.info("No sessions logged yet.")
    else:
        st.subheader("Recent Sessions")
        st.dataframe(df.sort_values("created_at", ascending=False).reset_index(drop=True))

        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        df["date_dt"] = pd.to_datetime(df["date"]).dt.date
        mask = (df["date_dt"] >= week_start) & (df["date_dt"] <= week_end)
        weekly_total = df.loc[mask, "duration_hours"].sum()
        st.metric("This week's total hours", f"{weekly_total:.2f} h")

        st.subheader("Daily Hours (Last 14 Days)")
        last_n_days = 14
        cutoff = today - timedelta(days=last_n_days - 1)
        df_recent = df[df["date_dt"] >= cutoff]
        daily = (
            df_recent.groupby("date_dt")["duration_hours"].sum().reindex(
                pd.date_range(cutoff, today).date, fill_value=0
            )
        )
        fig1, ax1 = plt.subplots()
        ax1.bar([d.strftime("%Y-%m-%d") for d in daily.index], daily.values)
        plt.xticks(rotation=45, ha="right")
        ax1.set_ylabel("Hours")
        ax1.set_title("Daily Hours")
        st.pyplot(fig1)

        st.subheader("Breakdown by Project")
        by_project = df.groupby("project")["duration_hours"].sum().sort_values(ascending=False)
        fig2, ax2 = plt.subplots()
        ax2.barh(by_project.index, by_project.values)
        ax2.set_xlabel("Hours")
        ax2.set_title("Hours by Project")
        st.pyplot(fig2)

        st.subheader("Breakdown by Task Type")
        by_task = df.groupby("task_type")["duration_hours"].sum().sort_values(ascending=False)
        fig3, ax3 = plt.subplots()
        ax3.barh(by_task.index, by_task.values)
        ax3.set_xlabel("Hours")
        ax3.set_title("Hours by Task Type")
        st.pyplot(fig3)

        st.subheader("Export")
        csv = df.to_csv(index=False)
        st.download_button("Download CSV", csv, file_name="time_logs.csv", mime="text/csv")

        if auth_mode == "guest":
            st.warning("⚠️ You are in Guest mode — data is temporary and not saved.")
        else:
            st.success("✅ Dashboard loaded from Google Sheets.")
