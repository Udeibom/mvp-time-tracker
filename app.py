import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import uuid
from datetime import datetime, date, timedelta, timezone
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
            try:
                correct_user = st.secrets["auth"]["owner_user"]
                correct_pass = st.secrets["auth"]["owner_pass"]
            except Exception:
                st.error("App secrets for [auth] are missing or malformed. Please add them in Streamlit Secrets.")
                return

            if user == correct_user and password == correct_pass:
                st.session_state["auth_mode"] = "owner"
                st.success("✅ Logged in as Owner")
                st.experimental_rerun()
            else:
                st.error("❌ Invalid credentials. Try again.")
    else:
        if st.button("Continue as Guest"):
            st.session_state["auth_mode"] = "guest"
            st.success("👋 Logged in as Guest (session data only)")
            st.experimental_rerun()


if "auth_mode" not in st.session_state:
    login_page()
    st.stop()

# -----------------------------
# Cached Google Sheets connection (Owner)
# -----------------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

@st.cache_resource
def get_sheet_connection():
    """Open and return the 'sessions' worksheet (cached to avoid repeated API calls)."""
    # This function expects the proper secrets to exist. It will raise KeyError if they don't.
    SHEET_URL = st.secrets["sheet"]["url"]
    CREDS = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    gc = gspread.authorize(CREDS)
    sh = gc.open_by_url(SHEET_URL)
    try:
        ws_local = sh.worksheet("sessions")
    except gspread.exceptions.WorksheetNotFound:
        ws_local = sh.add_worksheet(title="sessions", rows="100", cols="10")
        ws_local.append_row(
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
    return ws_local

# -----------------------------
# Database Setup (Owner / Guest)
# -----------------------------
auth_mode = st.session_state["auth_mode"]

# Add a logout button (useful)
with st.sidebar:
    st.markdown("---")
    if st.button("🔓 Logout"):
        # Clear session state safely
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.success("✅ Logged out")
        st.experimental_rerun()

if auth_mode == "owner":
    st.sidebar.success("🟢 Owner mode (Google Sheets connected)")

    # Try to get the cached connection, but handle errors gracefully so login doesn't crash
    try:
        ws = get_sheet_connection()
    except KeyError as e:
        # Missing secrets key
        st.error(
            "Streamlit secrets missing required keys. Please add the following in Secrets:\n\n"
            " - [gcp_service_account] (your JSON service account) \n"
            " - [sheet] url = \"https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/...\"\n\n"
            "After updating Secrets, log in again."
        )
        # Reset auth_mode so user goes back to login
        st.session_state.pop("auth_mode", None)
        st.stop()
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(
            "Could not find the spreadsheet at the configured URL. "
            "Check st.secrets['sheet']['url'] and ensure the sheet exists."
        )
        st.session_state.pop("auth_mode", None)
        st.stop()
    except gspread.exceptions.APIError as e:
        st.error(
            "Google Sheets API error when accessing the spreadsheet.\n"
            "Common causes: the service account hasn't been shared on the sheet, or API quota was exceeded.\n\n"
            "Error summary: " + str(e)
        )
        st.session_state.pop("auth_mode", None)
        st.stop()
    except Exception as e:
        st.error(f"Unexpected error connecting to Google Sheets: {e}")
        st.session_state.pop("auth_mode", None)
        st.stop()

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
                    "created_at": datetime.now(timezone.utc).isoformat(),
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

        # START: set start time and immediately rerun so UI switches to timer display right away
        if not st.session_state.timer_running:
            if st.button("Start Timer"):
                st.session_state.timer_start = datetime.now(timezone.utc)
                st.session_state.timer_running = True
                st.session_state.timer_stopped = False
                st.session_state.timer_end = None
                st.session_state.timer_duration = 0.0
                st.success("⏱ Timer started!")
                # immediate rerun so the else branch shows elapsed
                st.experimental_rerun()
        else:
            start_dt = st.session_state.timer_start
            placeholder = st.empty()
            # compute elapsed based on timezone-aware now
            elapsed = datetime.now(timezone.utc) - start_dt
            hours = elapsed.total_seconds() / 3600
            placeholder.info(f"⏳ Elapsed time: **{hours:.3f} hours**")

            # Stop button shown while running
            if st.button("Stop Timer"):
                end_dt = datetime.now(timezone.utc)
                duration_hours = compute_duration_hours(start_dt, end_dt)
                st.session_state.timer_end = end_dt
                st.session_state.timer_duration = duration_hours
                st.session_state.timer_running = False
                st.session_state.timer_stopped = True
                st.success(f"✅ Timer stopped. Duration: {duration_hours:.3f} hours")
                # rerun to refresh UI (now shows the log form)
                st.experimental_rerun()
            else:
                # lightweight pause then rerun to update elapsed display
                time.sleep(1)
                st.experimental_rerun()

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
                        "created_at": datetime.now(timezone.utc).isoformat(),
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
                    # reset timer state
                    st.session_state.timer_running = False
                    st.session_state.timer_stopped = False
                    st.session_state.timer_start = None
                    st.session_state.timer_end = None
                    st.session_state.timer_duration = 0.0

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
