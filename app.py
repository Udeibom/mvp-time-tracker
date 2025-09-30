import streamlit as st
import pandas as pd
import sqlite3
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path
import matplotlib.pyplot as plt
import time  # standard library module (used for sleep)

# -----------------------------
# Configuration
# -----------------------------
DB_PATH = Path("data") / "sessions.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# -----------------------------
# Database helpers
# -----------------------------
def init_db(db_path=DB_PATH):
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            created_at TEXT,
            date TEXT,
            start_time TEXT,
            end_time TEXT,
            duration_hours REAL,
            project TEXT,
            task_type TEXT,
            notes TEXT,
            focus_rating INTEGER
        )
        """
    )
    conn.commit()
    conn.close()


def add_session(record, db_path=DB_PATH):
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute(
        "INSERT INTO sessions (id, created_at, date, start_time, end_time, duration_hours, project, task_type, notes, focus_rating) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            record["id"],
            record["created_at"],
            record["date"],
            record["start_time"],
            record["end_time"],
            float(record["duration_hours"]),
            record.get("project"),
            record.get("task_type"),
            record.get("notes"),
            record.get("focus_rating"),
        ),
    )
    conn.commit()
    conn.close()


def fetch_df(db_path=DB_PATH):
    conn = sqlite3.connect(str(db_path))
    try:
        df = pd.read_sql_query("SELECT * FROM sessions", conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    if df.empty:
        return df

    df["created_at"] = pd.to_datetime(df["created_at"])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
    df["end_time"] = pd.to_datetime(df["end_time"], errors="coerce")
    df["duration_hours"] = pd.to_numeric(df["duration_hours"])
    return df

# -----------------------------
# Utilities
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
# UI
# -----------------------------
init_db()
st.set_page_config(page_title="MVP Time Tracker", layout="wide")
st.title("MVP Time Tracker")

page = st.sidebar.radio("Go to", ["Log session", "Dashboard & Export"])

# Ensure session state keys for timer
for key, val in {
    "timer_running": False,
    "timer_start": None,
    "timer_end": None,
    "timer_duration": 0.0,
    "timer_stopped": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# --- LOG SESSION PAGE ---
if page == "Log session":
    st.header("Log a session")
    col1, col2 = st.columns([2, 1])

    # Manual entry
    with col1:
        st.subheader("Manual entry")
        with st.form("manual_form"):
            d = st.date_input("Date", value=date.today())

            # compute a stable default "now" once per session
            if "manual_default_time" not in st.session_state:
                st.session_state.manual_default_time = datetime.now().time().replace(microsecond=0)

            # give widgets unique keys
            s_time = st.time_input(
                "Start time",
                value=st.session_state.manual_default_time,
                key="manual_start_time",
            )

            # sensible end-time default (30 mins after start) if not yet set
            if "manual_end_time" not in st.session_state:
                default_end_dt = datetime.combine(d, st.session_state.manual_default_time) + timedelta(minutes=30)
                st.session_state.manual_end_time = default_end_dt.time().replace(microsecond=0)

            e_time = st.time_input(
                "End time",
                value=st.session_state.manual_end_time,
                key="manual_end_time",
            )

            project = st.text_input("Project", value="Personal")
            task_type = st.text_input("Task type", value="Coding")
            notes = st.text_area("Notes", value="")
            focus_rating = st.slider("Focus (1–5)", 1, 5, 3)

            start_dt = combine_date_time(d, s_time)
            end_dt = combine_date_time(d, e_time)
            duration_preview = compute_duration_hours(start_dt, end_dt)
            st.markdown(f"**Duration (hours):** {duration_preview}")

            submitted = st.form_submit_button("Log session")
            if submitted:
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
                st.success("✅ Saved session to local SQLite DB.")

    # Quick timer
    with col2:
        st.subheader("Quick timer")

        if not st.session_state.timer_running:
            if st.button("Start Timer"):
                st.session_state.timer_start = datetime.utcnow()
                st.session_state.timer_running = True
                st.session_state.timer_stopped = False
                st.session_state.timer_end = None
                st.session_state.timer_duration = 0.0
                st.success(f"⏱ Timer started at {st.session_state.timer_start.strftime('%H:%M:%S')} (UTC)")
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

        # Show log form when stopped
        if st.session_state.get("timer_stopped", False):
            st.subheader("Log this timer session")
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
                log_timer = st.form_submit_button("✅ Log timer session")

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
                    st.success("✅ Timer session saved to DB.")
                    st.session_state.timer_running = False
                    st.session_state.timer_stopped = False
                    st.session_state.timer_start = None
                    st.session_state.timer_end = None
                    st.session_state.timer_duration = 0.0

# --- DASHBOARD PAGE ---
else:
    st.header("Dashboard & Export")
    df = fetch_df()
    if df.empty:
        st.info("No sessions logged yet. Go to 'Log session' to add one.")
    else:
        st.subheader("Recent sessions")
        st.dataframe(df.sort_values("created_at", ascending=False).reset_index(drop=True))

        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        df["date_dt"] = pd.to_datetime(df["date"]).dt.date
        mask = (df["date_dt"] >= week_start) & (df["date_dt"] <= week_end)
        weekly_total = df.loc[mask, "duration_hours"].sum()
        st.metric("This week's total hours", f"{weekly_total:.2f} h")

        st.subheader("Daily hours (last 14 days)")
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
        ax1.set_xticks(range(0, len(daily.index), max(1, len(daily.index)//7)))
        ax1.set_ylabel("Hours")
        ax1.set_title("Daily hours")
        plt.xticks(rotation=45, ha="right")
        st.pyplot(fig1)

        st.subheader("Breakdown by project")
        by_project = df.groupby("project")["duration_hours"].sum().sort_values(ascending=False)
        fig2, ax2 = plt.subplots()
        ax2.barh(by_project.index, by_project.values)
        ax2.set_xlabel("Hours")
        ax2.set_title("Hours by project")
        st.pyplot(fig2)

        st.subheader("Breakdown by task type")
        by_task = df.groupby("task_type")["duration_hours"].sum().sort_values(ascending=False)
        fig3, ax3 = plt.subplots()
        ax3.barh(by_task.index, by_task.values)
        ax3.set_xlabel("Hours")
        ax3.set_title("Hours by task type")
        st.pyplot(fig3)

        st.subheader("Export")
        csv = df.to_csv(index=False)
        st.download_button("Download CSV", csv, file_name="time_logs.csv", mime="text/csv")

        with open(str(DB_PATH), "rb") as f:
            db_bytes = f.read()
        st.download_button("Download SQLite DB", db_bytes, file_name="sessions.db", mime="application/octet-stream")

        st.success("✅ Dashboard generated from local DB.")
