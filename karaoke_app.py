import os
import json
from typing import Optional, Tuple, List
from datetime import datetime

import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account

#############################
# Configuration & Secrets   #
#############################
# Required secrets (set in hosting platform):
# - GOOGLE_CREDENTIALS: the FULL service-account JSON (string)
# - SHEET_KEY: the Google Sheet key (string)
# - HOST_PIN: PIN for host controls

# Fallbacks for local dev only
HOST_PIN = st.secrets.get("HOST_PIN", os.getenv("HOST_PIN", "changeme"))
SHEET_KEY = st.secrets.get("SHEET_KEY", os.getenv("SHEET_KEY", ""))
GOOGLE_CREDS_RAW = st.secrets.get("GOOGLE_CREDENTIALS", os.getenv("GOOGLE_CREDENTIALS", ""))

# Build credentials (prefer secrets, fallback to local file for dev)
creds: service_account.Credentials
if GOOGLE_CREDS_RAW:
    try:
        info = json.loads(GOOGLE_CREDS_RAW)
        creds = service_account.Credentials.from_service_account_info(info, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ])
    except Exception as e:
        st.stop()
else:
    # Local dev: use service_account.json in project root if present
    if os.path.exists("service_account.json"):
        creds = service_account.Credentials.from_service_account_file(
            "service_account.json",
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
    else:
        st.error("Google credentials not configured. Set GOOGLE_CREDENTIALS secret or provide service_account.json for local dev.")
        st.stop()

# Connect gspread
client = gspread.authorize(creds)
try:
    if not SHEET_KEY:
        st.error("SHEET_KEY is not set. Add it to secrets or env.")
        st.stop()
    sheet = client.open_by_key(SHEET_KEY)
except Exception as e:
    st.error("Failed to open Google Sheet. Check SHEET_KEY and credentials.")
    st.stop()

# Ensure worksheets
try:
    worksheet = sheet.worksheet("Signups")
except gspread.WorksheetNotFound:
    worksheet = sheet.add_worksheet(title="Signups", rows=1000, cols=10)
    worksheet.update("A1:F1", [["timestamp", "name", "phone", "instagram", "song", "suggestion"]])

try:
    songs_ws = sheet.worksheet("Songs")
except gspread.WorksheetNotFound:
    songs_ws = sheet.add_worksheet(title="Songs", rows=1000, cols=1)
    songs_ws.update("A1", "Song Title")

# Canonical headers used across the app
HEADERS = ["timestamp", "name", "phone", "instagram", "song", "suggestion"]

#############################
# Performance: cached IO    #
#############################
CACHE_SIGNUPS_TTL = 3    # seconds: short but reduces hammering
CACHE_SONGS_TTL = 30     # seconds: song list relatively static

@st.cache_data(ttl=CACHE_SIGNUPS_TTL, show_spinner=False)
def load_signups() -> pd.DataFrame:
    records = worksheet.get_all_records()  # header-aware
    if records:
        df = pd.DataFrame(records)
    else:
        header = worksheet.row_values(1) or []
        df = pd.DataFrame(columns=[c.strip().lower() for c in header])
    df.columns = [c.strip().lower() for c in df.columns]
    # normalize expected columns
    for col in ["timestamp","name","phone","instagram","song","suggestion"]:
        if col not in df.columns:
            df[col] = ""
    return df

@st.cache_data(ttl=CACHE_SONGS_TTL, show_spinner=False)
def load_song_list() -> List[str]:
    vals = songs_ws.col_values(1)
    vals = [v for v in vals if v and v.strip() and v.strip().lower() != "song title"]
    return vals

def safe_queue(df: pd.DataFrame) -> pd.DataFrame:
    if "timestamp" in df.columns:
        try:
            # ensure sortable timestamp
            tmp = df.copy()
            tmp["_ts"] = pd.to_datetime(tmp["timestamp"], errors="coerce")
            tmp = tmp.sort_values(["_ts"], kind="stable")
            return tmp.drop(columns=["_ts"], errors="ignore")
        except Exception:
            return df
    return df

#############################
# Exact row-location helpers #
#############################
from typing import Dict

def get_rows_matrix() -> List[List[str]]:
    return worksheet.get_all_values() or []

def find_row_by_name_song(name: str, song: str) -> Optional[int]:
    """Return 1-based worksheet row (including header as row 1), or None."""
    rows = get_rows_matrix()
    name_l = name.strip().lower()
    song_s = song.strip()
    for i, row in enumerate(rows[1:], start=2):
        # Columns: timestamp, name, phone, instagram, song, suggestion
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
        if rec.get("phone", "") == phone:
            return i, rec
    return None, {}

#############################
# UI: page config & header  #
#############################
st.set_page_config(page_title="LoseMos Karaoke Signup", page_icon="🎤", layout="centered")

# Header brand block
col_logo, col_title = st.columns([1,3], vertical_alignment="center")
with col_logo:
    try:
        st.image("logo.png", caption=None)
    except Exception:
        pass
with col_title:
    st.title("LoseMos Karaoke Signup 🎤")
    st.caption("One song per person. Once it's claimed, it disappears. We'll call your name when it's your turn to scream.")
    st.markdown("Instagram: **[@losemoskaraoke](https://instagram.com/losemoskaraoke)**")

st.divider()

#############################
# Public signup form        #
#############################
df = load_signups()
claimed_songs = set(df["song"].dropna().astype(str).tolist())
all_songs = load_song_list()
available_songs = [s for s in all_songs if s not in claimed_songs]

with st.form("signup_form", clear_on_submit=True):
    name = st.text_input("Your Name", max_chars=60)

    # Phone: accept digits; display formatted; store as 10-digit string
    phone_raw = st.text_input("Phone (10 digits)", help="We use this only to ensure one signup per person.")
    digits = "".join(ch for ch in phone_raw if ch.isdigit())
    formatted = (
        f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}" if len(digits) >= 10 else phone_raw
    )
    if phone_raw and len(digits) <= 10 and len(digits) >= 4:
        st.caption(f"Formatted: {formatted}")

    instagram = st.text_input("Instagram (optional)", placeholder="@yourhandle")
    # Normalize instagram: drop leading '@'
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
        # Validate
        errs = []
        if not name.strip():
            errs.append("Please enter your name.")
        if len(digits) != 10:
            errs.append("Phone must be exactly 10 digits.")
        if not song:
            errs.append("Please select a song.")

        # Prevent duplicate by phone
        if not errs and digits in df["phone"].tolist():
            errs.append("This phone number already signed up.")

        # Ensure song still free (race)
        if not errs and song in claimed_songs:
            errs.append("Sorry, that song was just claimed. Pick another.")

        if errs:
            for e in errs:
                st.error(e)
        else:
            # Append row
            now = datetime.utcnow().isoformat()
            row = [now, name.strip(), digits, instagram.strip(), song, suggestion.strip()]
            try:
                worksheet.append_row(row, table_range="A1")
                st.success("You're in! We'll call your name when it's your turn.")
                st.cache_data.clear()  # refresh caches across users
                st.rerun()
            except Exception as e:
                st.error("Could not save your signup. Please try again.")

# Privacy disclaimer
st.info("We won't share your data or contact you outside this event. Phone numbers ensure everyone only signs up for one song.")

#############################
# Public: Undo My Signup    #
#############################
with st.expander("⚠️ Undo My Signup"):
    undo_phone_raw = st.text_input("Enter the same phone number you signed up with (10 digits)", key="undo_phone")
    u_digits = "".join(ch for ch in undo_phone_raw if ch.isdigit())
    do_undo = st.button("Undo My Signup")
    if do_undo:
        if len(u_digits) != 10:
            st.error("Phone must be exactly 10 digits.")
        else:
            row_idx, rec = find_row_by_phone(u_digits)
            if row_idx:
                # Double-check exact row by name+song
                exact_row = find_row_by_name_song(rec.get("name", ""), rec.get("song", ""))
                try:
                    if exact_row:
                        worksheet.delete_rows(exact_row)
                    else:
                        # Fallback to phone-only deletion
                        worksheet.delete_rows(row_idx)
                    st.success("✅ Your signup has been removed.")
                    st.cache_data.clear()
                    st.rerun()
                except Exception:
                    st.error("Could not remove your signup. Please try again.")
            else:
                st.error("No signup found for that phone number.")

st.divider()

#############################
# Host Controls (PIN)       #
#############################
with st.expander("🔐 Host Controls"):
    pin = st.text_input("Enter host PIN", type="password")
    if st.button("Unlock Host Panel"):
        st.session_state["host_unlocked"] = (pin == HOST_PIN)
        if not st.session_state["host_unlocked"]:
            st.error("Incorrect PIN.")
    if st.session_state.get("host_unlocked"):
        st.success("Host panel unlocked.")

        # Current queue snapshot
        df = load_signups()
        queue_df = safe_queue(df[df["song"].astype(str).str.len() > 0])

        # Call Next Singer
        st.subheader("📣 Call Next Singer")
        if not queue_df.empty:
            next_row = queue_df.iloc[0]
            name_next = str(next_row.get("name", "")).strip()
            song_next = str(next_row.get("song", "")).strip()
            if st.button("Call Next"):
                st.session_state["now_singing"] = (name_next, song_next)
                st.success(f"Now calling **{name_next}** — *{song_next}*")
        else:
            st.info("No one in the queue yet.")

        # Now Singing
        st.subheader("🎶 Now Singing")
        if "now_singing" in st.session_state and st.session_state["now_singing"]:
            n, s = st.session_state["now_singing"]
            st.markdown(f"**{n}** — *{s}*")
        else:
            st.caption("No one is currently singing.")

        # View Next 3
        st.subheader("👀 Up Next")
        if len(queue_df) > 1:
            upcoming = queue_df.iloc[1:4][["name","song"]].reset_index(drop=True)
            st.dataframe(upcoming, use_container_width=True, hide_index=True)
        else:
            st.caption("Fewer than 2 people in the queue.")

        # Skip a Singer (session-only priority)
        st.subheader("⏭️ Skip a Singer (session only)")
        if not queue_df.empty:
            options = [f"{r.name}: {r['name']} — {r['song']}" for _, r in queue_df.reset_index().iterrows()]
            skip_choice = st.selectbox("Choose to move to end (session-only order)", options=options, index=0)
            if st.button("Skip Selected"):
                # session-state reorder by storing a list of skipped (to deprioritize visually)
                idx = int(skip_choice.split(":", 1)[0])
                st.session_state.setdefault("skipped_ids", [])
                st.session_state["skipped_ids"].append(idx)
                st.success("Moved selected singer to the end (visual only).")
        else:
            st.caption("No one to skip.")

        # Release a Song (delete row)
        st.subheader("🗑️ Release a Song")
        if not df.empty:
            df_disp = safe_queue(df)
            df_disp["label"] = df_disp.apply(lambda r: f"{r['name']} — {r['song']}", axis=1)
            release_label = st.selectbox("Select signup to remove", options=[""] + df_disp["label"].tolist(), index=0)
            confirm_release = st.checkbox("Yes, remove this signup")
            if release_label and confirm_release and st.button("Remove Selected Signup"):
                # parse name and song back
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
                    except Exception:
                        st.error("Could not delete the row. Try again.")
                else:
                    st.error("Could not find that signup anymore.")
        else:
            st.caption("No signups yet.")

        # View Full Signup List
        with st.expander("📋 View Full Signup List"):
            st.dataframe(safe_queue(df)[["timestamp","name","phone","instagram","song","suggestion"]], use_container_width=True)

        # Download CSV
        csv = safe_queue(df).to_csv(index=False)
        st.download_button("⬇️ Download CSV", data=csv, file_name="signups.csv", mime="text/csv")

        # Reset for Next Event
st.subheader("🧹 Reset for Next Event")
if st.checkbox("Yes, clear all signups and keep headers"):
    if st.button("Reset Now"):
        try:
            worksheet.clear()
            worksheet.update("A1:F1", [HEADERS])
            st.cache_data.clear()
            st.success("Sheet reset. Ready for the next event.")
            st.rerun()
        except Exception as e:
            st.error(f"Could not reset the sheet. Try again. ({e})")

# Footer
st.caption("© LoseMos Karaoke — built with Streamlit. ")
st.caption("© LoseMos Karaoke — built with Streamlit. ")
