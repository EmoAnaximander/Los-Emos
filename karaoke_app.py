import os
import json
from typing import Optional, Tuple, List, Dict
from datetime import datetime

import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account

# --- Page config MUST be first ---
st.set_page_config(page_title="Song Selection", layout="centered")

import pathlib
cfg = pathlib.Path("/app/.streamlit/config.toml")
st.caption(f"Config exists: {cfg.exists()}  —  {cfg}")

# TEMP heartbeat so you can tell the app started (remove once stable)
st.write("App starting…")

# --- Diagnostics mode: set DIAGNOSTICS_MODE=1 in Cloud Run to avoid stopping early ---
DIAGNOSTICS_MODE = os.getenv("DIAGNOSTICS_MODE", "0") == "1"

def _safe_bool_env(name: str) -> bool:
    return bool(os.getenv(name))

def _service_account_email() -> str:
    raw = os.getenv("GOOGLE_CREDENTIALS", "")
    try:
        info = json.loads(raw)
        return info.get("client_email", "(no client_email)")
    except Exception:
        return "(GOOGLE_CREDENTIALS not valid JSON)"

st.sidebar.expander("Diagnostics (host)").write({
    "HAS_GOOGLE_CREDENTIALS": _safe_bool_env("GOOGLE_CREDENTIALS"),
    "HAS_SHEET_KEY": _safe_bool_env("SHEET_KEY"),
    "HAS_HOST_PIN": _safe_bool_env("HOST_PIN"),
    "SERVICE_ACCOUNT_EMAIL": _service_account_email(),
    "DIAGNOSTICS_MODE": DIAGNOSTICS_MODE,
})

#############################
# Configuration & Secrets   #
#############################
HEADERS = ["timestamp", "name", "phone", "instagram", "song", "suggestion"]

HOST_PIN = st.secrets.get("HOST_PIN", os.getenv("HOST_PIN", "changeme"))
SHEET_KEY = st.secrets.get("SHEET_KEY", os.getenv("SHEET_KEY", ""))
GOOGLE_CREDS_RAW = st.secrets.get("GOOGLE_CREDENTIALS", os.getenv("GOOGLE_CREDENTIALS", ""))

# Credentials (robust + show exceptions)
creds: service_account.Credentials
if GOOGLE_CREDS_RAW:
    try:
        info = json.loads(GOOGLE_CREDS_RAW)
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
    except Exception as e:
        st.error("Invalid GOOGLE_CREDENTIALS secret. Use triple single quotes in secrets so \\n are preserved.")
        if not DIAGNOSTICS_MODE:
            st.exception(e)
            st.stop()
else:
    if os.path.exists("service_account.json"):
        creds = service_account.Credentials.from_service_account_file(
            "service_account.json",
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
    else:
        st.error("Google credentials not configured. Set GOOGLE_CREDENTIALS or provide service_account.json for local dev.")
        if not DIAGNOSTICS_MODE:
            st.stop()

# Sheets client & open
client = gspread.authorize(creds)
try:
    if not SHEET_KEY:
        st.error("SHEET_KEY is not set.")
        if not DIAGNOSTICS_MODE:
            st.stop()
    sheet = client.open_by_key(SHEET_KEY)
except Exception as e:
    st.error("Failed to open Google Sheet. Check SHEET_KEY and permissions.")
    if not DIAGNOSTICS_MODE:
        st.exception(e)
        st.stop()

# Ensure worksheets
try:
    worksheet = sheet.worksheet("Signups")
except gspread.WorksheetNotFound:
    worksheet = sheet.add_worksheet(title="Signups", rows=1000, cols=10)
    worksheet.update("A1:F1", [HEADERS])

try:
    songs_ws = sheet.worksheet("Songs")
except gspread.WorksheetNotFound:
    # Create the Songs sheet if missing (no header required)
    songs_ws = sheet.add_worksheet(title="Songs", rows=1000, cols=1)

#############################
# Cached IO helpers         #
#############################
CACHE_SIGNUPS_TTL = 3
CACHE_SONGS_TTL = 30

@st.cache_data(ttl=CACHE_SIGNUPS_TTL, show_spinner=False)
def load_signups() -> pd.DataFrame:
    records = worksheet.get_all_records()
    if records:
        df = pd.DataFrame(records)
    else:
        header = worksheet.row_values(1) or []
        df = pd.DataFrame(columns=[c.strip().lower() for c in header])
    df.columns = [c.strip().lower() for c in df.columns]
    for col in HEADERS:
        if col not in df.columns:
            df[col] = ""
    return df

@st.cache_data(ttl=CACHE_SONGS_TTL, show_spinner=False)
def load_song_list() -> List[str]:
    vals = songs_ws.col_values(1)
    # Accept any first row as valid; trim empties and de-dup while preserving order
    cleaned = [v.strip() for v in vals if isinstance(v, str) and v.strip()]
    deduped = list(dict.fromkeys(cleaned))
    return deduped

def safe_queue(df: pd.DataFrame) -> pd.DataFrame:
    if "timestamp" in df.columns:
        try:
            tmp = df.copy()
            tmp["_ts"] = pd.to_datetime(tmp["timestamp"], errors="coerce")
            tmp = tmp.sort_values(["_ts"], kind="stable")
            return tmp.drop(columns=["_ts"], errors="ignore")
        except Exception:
            return df
    return df

def get_rows_matrix() -> List[List[str]]:
    return worksheet.get_all_values() or []

def find_row_by_name_song(name: str, song: str) -> Optional[int]:
    rows = get_rows_matrix()
    name_l = name.strip().lower()
    song_s = song.strip()
    for i, row in enumerate(rows[1:], start=2):
        if len(row) >= 5:
            r_name = row[1].strip().lower()
            r_song = row[4].strip()
            if r_name == name_l and r_song == song_s:
                return i
    return None

def find_row_by_phone(phone: str) -> Tuple[Optional[int], Dict[str, str]]:
    rows = get_rows_matrix()
    if not rows:
        return None, {}
    header = [h.strip().lower() for h in rows[0]]
    for i, row in enumerate(rows[1:], start=2):
        rec = {header[j]: (row[j] if j < len(row) else "") for j in range(len(header))}
        phone_val = "".join(ch for ch in str(rec.get("phone", "")) if ch.isdigit())
        if phone_val == phone:
            return i, rec
    return None, {}

#############################
# Header (centered logo)    #
#############################
col_l, col_c, col_r = st.columns([1, 2, 1])
with col_c:
    try:
        st.image("logo.png", caption=None)
    except Exception:
        pass
st.markdown("""<h1 style='text-align:center;margin:0;'>Song Selection</h1>""", unsafe_allow_html=True)
st.markdown(
    """<p style='text-align:center;margin:0;'>One song per person. Once it's claimed, it disappears. We'll call your name when it's your turn to scream.</p>""",
    unsafe_allow_html=True,
)
st.markdown(
    """<p style='text-align:center;margin:6px 0;'><a href='https://instagram.com/losemoskaraoke' target='_blank'>Follow us on Instagram</a></p>""",
    unsafe_allow_html=True,
)

st.divider()

# Persistent success banner (survives reruns)
if st.session_state.get("signup_success"):
    _msg = st.session_state["signup_success"]
    if isinstance(_msg, dict) and _msg.get("song"):
        st.success(f"You're in! You've signed up to sing '{_msg['song']}'. We'll call your name when it's your turn.")
        if st.button("Dismiss", key="dismiss_success"):
            st.session_state["signup_success"] = None
            st.rerun()

#############################
# Public signup form        #
#############################
df = load_signups()
claimed_songs = set(df["song"].dropna().astype(str).tolist())
all_songs = load_song_list()
if not all_songs:
    st.warning("No songs found in the 'Songs' worksheet.")
available_songs = [s.strip() for s in all_songs if s and s.strip() and s.strip() not in claimed_songs]

with st.form("signup_form", clear_on_submit=True):
    name = st.text_input("Your Name", max_chars=60)
    phone_raw = st.text_input("Phone (10 digits)", help="We use this only to ensure one signup per person.")
    digits = "".join(ch for ch in phone_raw if ch.isdigit())
    formatted = (f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}" if len(digits) >= 10 else phone_raw)
    if phone_raw and len(digits) <= 10 and len(digits) >= 4:
        st.caption(f"Formatted: {formatted}")

    instagram = st.text_input("Instagram (optional)", placeholder="@yourhandle")
    if instagram.strip().startswith("@"):
        instagram = instagram.strip()[1:]

    suggestion = st.text_input("Song suggestion (optional)")
    if available_songs:
        song = st.selectbox("Pick your song", options=[""] + available_songs, index=0)
    else:
        song = ""
        st.info("All songs are currently claimed. Check back soon!")

    submit = st.form_submit_button("Submit Signup")
    if submit:
        errs = []
        if not name.strip():
            errs.append("Please enter your name.")
        if len(digits) != 10:
            errs.append("Phone must be exactly 10 digits.")
        if not song:
            errs.append("Please select a song.")
        if not errs and digits in df["phone"].astype(str).tolist():
            errs.append("This phone number already signed up.")
        if not errs and song in claimed_songs:
            errs.append("Sorry, that song was just claimed. Pick another.")

        if errs:
            for e in errs:
                st.error(e)
        else:
            now = datetime.utcnow().isoformat()
            row = [now, name.strip(), digits, instagram.strip(), song, suggestion.strip()]
            try:
                worksheet.append_row(row, table_range="A1")
                st.session_state["signup_success"] = {"song": song, "name": name.strip()}
                st.cache_data.clear()
                st.rerun()
            except Exception:
                st.error("Could not save your signup. Please try again.")

# Public: Undo My Signup (moved right under signup)
with st.expander("Undo My Signup"):
    undo_phone_raw = st.text_input("Enter the same phone number you signed up with (10 digits)", key="undo_phone")
    u_digits = "".join(ch for ch in undo_phone_raw if ch.isdigit())
    do_undo = st.button("Undo My Signup")
    if do_undo:
        if len(u_digits) != 10:
            st.error("Phone must be exactly 10 digits.")
        else:
            row_idx, rec = find_row_by_phone(u_digits)
            if row_idx:
                exact_row = find_row_by_name_song(rec.get("name", ""), rec.get("song", ""))
                try:
                    if exact_row:
                        worksheet.delete_rows(exact_row)
                    else:
                        worksheet.delete_rows(row_idx)
                    st.success("Your signup has been removed.")
                    st.cache_data.clear()
                    st.rerun()
                except Exception:
                    st.error("Could not remove your signup. Please try again.")
            else:
                st.error("No signup found for that phone number.")

st.divider()

# Privacy disclaimer
st.info("We won't share your data or contact you outside this event. Phone numbers ensure everyone only signs up for one song.")

# Full song list (below the picker) with strikethrough for claimed
st.subheader("All Songs")
all_list = load_song_list()
if all_list:
    lines = []
    for s in all_list:
        title = (s or "").strip()
        if not title:
            continue
        if title in claimed_songs:
            lines.append(f"- ~~{title}~~")
        else:
            lines.append(f"- {title}")
    st.markdown("\n".join(lines))
else:
    st.caption("No songs found yet in the Songs sheet.")

#############################
# Host Controls (PIN)       #
#############################
with st.expander("Host Controls"):
    pin = st.text_input("Enter host PIN", type="password")
    if st.button("Unlock Host Panel"):
        st.session_state["host_unlocked"] = (pin == HOST_PIN)
        if not st.session_state["host_unlocked"]:
            st.error("Incorrect PIN.")
    if st.session_state.get("host_unlocked"):
        # Reduced clutter (no permanent unlocked blurb)

        df = load_signups()
        queue_df = safe_queue(df[df["song"].astype(str).str.len() > 0])

        # Now Singing (before Call Next)
        st.subheader("Now Singing")
        if "now_singing" in st.session_state and st.session_state["now_singing"]:
            n, s = st.session_state["now_singing"]
            st.markdown(f"**{n}** — *{s}*")
        else:
            st.caption("No one is currently singing.")

        # Call Next Singer (advances through queue; stops at last)
        if not queue_df.empty:
            if "queue_pos" not in st.session_state:
                st.session_state["queue_pos"] = 0
            qp = st.session_state["queue_pos"]
            if qp >= len(queue_df):
                st.info("You've reached the end of the queue.")
            else:
                next_row = queue_df.iloc[qp]
                name_next = str(next_row.get("name", "")).strip()
                song_next = str(next_row.get("song", "")).strip()
                if st.button("Call Next Singer"):
                    st.session_state["now_singing"] = (name_next, song_next)
                    st.session_state["queue_pos"] = qp + 1
                    st.success(f"Now calling {name_next} — {song_next}")

            # Up Next (Next 3)
            qp2 = st.session_state.get("queue_pos", 0)
            if qp2 < len(queue_df):
                upcoming = queue_df.iloc[qp2:qp2+3][["name", "song"]].fillna("")
                if not upcoming.empty:
                    st.subheader("Up Next (Next 3)")
                    lines_up = [
                        f"- {i+1}. {r['name']} — {r['song']}"
                        for i, r in upcoming.reset_index(drop=True).iterrows()
                    ]
                    st.markdown("\n".join(lines_up))
        else:
            st.info("No one in the queue yet.")

        # Show Full Signup List (toggle, friendly list)
        showing = st.session_state.get("show_full_list", False)
        label = "Hide Full Signup List" if showing else "Show Full Signup List"
        if st.button(label, key="toggle_full_list"):
            st.session_state["show_full_list"] = not showing
            showing = st.session_state["show_full_list"]
        if showing:
            q = safe_queue(df)[["name", "song"]].fillna("")
            if not q.empty:
                lines = [f"- {i+1}. {r['name']} — {r['song']}" for i, r in q.iterrows()]
                st.markdown("\n".join(lines))
            else:
                st.caption("No signups yet.")

        # Skip a Singer (bump 3 spots down or to end)
        st.subheader("Skip a Singer")
        if not queue_df.empty:
            options = [f"{r.name}: {r['name']} — {r['song']}" for _, r in queue_df.reset_index().iterrows()]
            skip_choice = st.selectbox("Choose a singer to skip", options=options, index=0)
            if st.button("Skip Selected"):
                idx = int(skip_choice.split(":", 1)[0])
                df_reset = queue_df.reset_index(drop=True)
                if len(df_reset) > 3 and idx < len(df_reset):
                    row_to_move = df_reset.iloc[idx]
                    df_reset = df_reset.drop(idx)
                    insert_at = min(idx + 3, len(df_reset))
                    top = df_reset.iloc[:insert_at]
                    bottom = df_reset.iloc[insert_at:]
                    df_reset = pd.concat([top, pd.DataFrame([row_to_move]), bottom]).reset_index(drop=True)
                    st.success("Singer bumped 3 spots down the list.")
                else:
                    st.success("Fewer than 3 signups; singer moved to end.")
        else:
            st.caption("No one to skip.")

        # Release a Song
        st.subheader("Release a Song")
        if not df.empty:
            df_disp = safe_queue(df).fillna("")
            df_disp["label"] = df_disp.apply(lambda r: f"{r['name']} — {r['song']}", axis=1)
            release_label = st.selectbox("Select signup to remove", options=[""] + df_disp["label"].tolist(), index=0)
            confirm_release = st.checkbox("Yes, remove this signup")
            if release_label and confirm_release and st.button("Remove Selected Signup"):
                try:
                    name_to_release, song_to_release = release_label.split(" — ", 1)
                except ValueError:
                    name_to_release, song_to_release = release_label, ""
                exact_row = find_row_by_name_song(name_to_release, song_to_release)
                if exact_row:
                    try:
                        worksheet.delete_rows(exact_row)
                        st.success(f"Removed '{song_to_release}' by {name_to_release}.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not delete the row. Try again. ({e})")
                else:
                    st.error("Could not find that signup anymore.")
        else:
            st.caption("No signups yet.")

        # Download CSV
        csv = safe_queue(df).to_csv(index=False)
        st.download_button("Download CSV", data=csv, file_name="signups.csv", mime="text/csv")

        # Reset for Next Event
        st.subheader("Reset for Next Event")
        if st.checkbox("Yes, clear all signups and keep headers"):
            if st.button("Reset Now"):
                try:
                    worksheet.clear()
                    worksheet.update("A1:F1", [HEADERS])
                    # also reset local session pointers
                    st.session_state.pop("queue_pos", None)
                    st.session_state.pop("now_singing", None)
                    st.cache_data.clear()
                    st.success("Sheet reset. Ready for the next event.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not reset the sheet. Try again. ({e})")

# Footer
st.caption("Los Emos Karaoke — built with Streamlit.")

