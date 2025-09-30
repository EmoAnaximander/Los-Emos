import os
import json
import random
import time
from typing import Optional, Tuple, List, Dict
from datetime import datetime

import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account

# --- Page config MUST be first ---
st.set_page_config(page_title="Song Selection", layout="centered")

#############################
# Configuration & Secrets   #
#############################
HEADERS = ["timestamp", "name", "phone", "instagram", "song", "suggestion"]

HOST_PIN = os.getenv("HOST_PIN", "changeme")
SHEET_KEY = os.getenv("SHEET_KEY", "")
GOOGLE_CREDS_RAW = os.getenv("GOOGLE_CREDENTIALS", "")

#############################
# Credentials & Sheets      #
#############################
creds: Optional[service_account.Credentials] = None
client = None
sheet = None

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
        client = gspread.authorize(creds)
    except Exception as e:
        st.error(f"Invalid GOOGLE_CREDENTIALS JSON: {e}")
else:
    st.error("GOOGLE_CREDENTIALS secret is not set.")

if client and SHEET_KEY:
    try:
        sheet = client.open_by_key(SHEET_KEY)
    except Exception as e:
        msg = str(e)
        if "404" in msg or "NOT_FOUND" in msg or "not found" in msg.lower():
            st.error(
                "Could not open the Google Sheet (404).\n\n"
                "✅ Check these:\n"
                "1) SHEET_KEY is the ID between /d/ and /edit in the Sheet URL.\n"
                "2) The Sheet is shared with your service account email (as Editor).\n"
                "3) If it’s a Shared Drive, the service account is added to that Drive.\n"
            )
        else:
            st.error(f"Failed to open Google Sheet: {e}")
else:
    if not SHEET_KEY:
        st.error("SHEET_KEY secret is not set.")

if not sheet:
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
# Header (logo + intro)     #
#############################
col_l, col_c, col_r = st.columns([1, 2, 1])
with col_c:
    try:
        st.image("logo.png", caption=None)
    except FileNotFoundError:
        st.error("Error: logo.png not found in the container.")
    except Exception as e:
        st.error(f"Image load failed: {e}")

st.markdown("<h1 style='text-align:center;margin:0;'>Song Selection</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center;margin:0;'>One song per person. Once it's claimed, it disappears.</p>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center;margin:6px 0;'><a href='https://instagram.com/losemoskaraoke' target='_blank'>Follow us on Instagram</a></p>", unsafe_allow_html=True)

st.divider()

# Persistent success banner
if st.session_state.get("signup_success"):
    _msg = st.session_state["signup_success"]
    if isinstance(_msg, dict) and _msg.get("song"):
        st.success(f"You're in! You've signed up to sing '{_msg['song']}'.")
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
    phone_raw = st.text_input("Phone (10 digits)")
    digits = "".join(ch for ch in phone_raw if ch.isdigit())
    formatted = (f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}" if len(digits) >= 10 else phone_raw)
    if phone_raw and 4 <= len(digits) <= 10:
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

# Undo signup
with st.expander("Undo My Signup"):
    undo_phone_raw = st.text_input("Enter the phone number you signed up with (10 digits)", key="undo_phone")
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
st.info("We won't share your data. Phone numbers ensure everyone only signs up for one song.")

# Full song list
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
# Host Controls (shared + always-on refresh)
#############################
def _row_key(rec: Dict[str, str]) -> tuple:
    return (
        str(rec.get("name", "")).strip().lower(),
        "".join(ch for ch in str(rec.get("phone", "")) if ch.isdigit()),
        str(rec.get("song", "")).strip(),
    )

def _df_with_keys(dfin: pd.DataFrame) -> pd.DataFrame:
    df2 = dfin.copy()
    df2["__key__"] = df2.apply(lambda r: _row_key(r), axis=1)
    return df2

def _keys_from_df(df_keys: pd.DataFrame, keys: List[tuple]) -> List[Dict[str, str]]:
    pool = {k: rec for k, rec in zip(df_keys["__key__"], df_keys.to_dict("records"))}
    return [pool[k] for k in keys if k in pool]

def _serialize_keys(keys: List[tuple]) -> str:
    return json.dumps([list(k) for k in keys])

def _deserialize_keys(s: str) -> List[tuple]:
    try:
        raw = json.loads(s or "[]")
        return [tuple(x) for x in raw]
    except Exception:
        return []

def ensure_host_state_sheet():
    try:
        return sheet.worksheet("HostState")
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title="HostState", rows=2, cols=6)
        ws.update("A1:F1", [[
            "version", "now_key", "next_keys_json", "used_keys_json", "updated_at", "note"
        ]])
        ws.update("A2:F2", [[ "0", "[]", "[]", "[]", datetime.utcnow().isoformat(), "" ]])
        return ws

def read_state(ws) -> dict:
    values = ws.get("A2:F2")[0]
    state = {
        "version": int(values[0] or "0"),
        "now_key": _deserialize_keys(values[1])[0] if _deserialize_keys(values[1]) else None,
        "next_keys": _deserialize_keys(values[2]),
        "used_keys": _deserialize_keys(values[3]),
    }
    return state

def write_state(ws, state: dict):
    ws.update("A2:F2", [[
        str(int(state.get("version", 0))),
        _serialize_keys([state["now_key"]] if state.get("now_key") else []),
        _serialize_keys(state.get("next_keys", [])),
        _serialize_keys(state.get("used_keys", [])),
        datetime.utcnow().isoformat(),
        ""
    ]])

def bump_version(state: dict):
    state["version"] = int(state.get("version", 0)) + 1

with st.expander("Host Controls"):
    pin = st.text_input("Enter host PIN", type="password")
    if st.button("Unlock Host Panel"):
        st.session_state["host_unlocked"] = (pin == HOST_PIN)
        if not st.session_state["host_unlocked"]:
            st.error("Incorrect PIN.")

    if st.session_state.get("host_unlocked"):
        # Current signups (new signups included)
        df_all = load_signups()
        queue_df = df_all[df_all["song"].astype(str).str.len() > 0].fillna("")
        queue_df_k = _df_with_keys(queue_df)

        # Shared state sheet
        host_ws = ensure_host_state_sheet()
        state = read_state(host_ws)
        used_keys = set(state["used_keys"])
        now_key = state["now_key"]
        next_keys = list(state["next_keys"])

        # Compute available keys
        all_keys = set(queue_df_k["__key__"])
        unavailable = used_keys.union(set(next_keys))
        if now_key:
            unavailable.add(now_key)
        available_keys = list(all_keys - unavailable)

        # Fill Next 3
        while len(next_keys) < 3 and available_keys:
            choice = random.choice(available_keys)
            next_keys.append(choice)
            available_keys.remove(choice)

        # Display records
        next_records = _keys_from_df(queue_df_k, next_keys)
        now_record = None
        if now_key:
            rp = {k: rec for k, rec in zip(queue_df_k["__key__"], queue_df_k.to_dict("records"))}
            now_record = rp.get(now_key)

        st.subheader("Now Singing")
        if now_record:
            n = str(now_record.get("name", "")).strip()
            s = str(now_record.get("song", "")).strip()
            st.markdown(f"**{n}** — *{s}*")
        else:
            st.caption("No one is currently singing.")

        if next_records:
            display_next = next_records[0]
            name_next = str(display_next.get("name", "")).strip()
            song_next = str(display_next.get("song", "")).strip()

            if st.button("Call Next Singer"):
                if now_key:
                    used_keys.add(now_key)
                now_key = next_keys.pop(0)

                df_all = load_signups()
                queue_df = df_all[df_all["song"].astype(str).str.len() > 0].fillna("")
                queue_df_k = _df_with_keys(queue_df)
                all_keys = set(queue_df_k["__key__"])
                unavailable = used_keys.union(set(next_keys))
                unavailable.add(now_key)
                available_keys = list(all_keys - unavailable)

                if len(next_keys) < 3 and available_keys:
                    next_keys.append(random.choice(available_keys))

                state["now_key"] = now_key
                state["next_keys"] = next_keys
                state["used_keys"] = list(used_keys)
                bump_version(state)
                write_state(host_ws, state)

                st.success(f"Now calling {name_next} — {song_next}")
        else:
            st.info("No one in the queue yet.")

        if next_records:
            st.subheader("Up Next (Next 3)")
            show = next_records[:3]
            lines_up = [f"- {i+1}. {r.get('name','')} — {r.get('song','')}" for i, r in enumerate(show)]
            st.markdown("\n".join(lines_up))
        else:
            st.caption("No upcoming singers.")

        # Reset for Next Event
        st.subheader("Reset for Next Event")
        if st.checkbox("Yes, clear all signups and keep headers"):
            if st.button("Reset Now"):
                try:
                    worksheet.clear()
                    worksheet.update("A1:F1", [HEADERS])
                    write_state(host_ws, {
                        "version": 0,
                        "now_key": None,
                        "next_keys": [],
                        "used_keys": [],
                    })
                    st.cache_data.clear()
                    st.success("Sheet reset. Ready for the next event.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not reset the sheet. ({e})")

        # 🔄 Always-on refresh every 3s
        time.sleep(3)
        st.experimental_rerun()

# Footer
st.caption("Los Emos Karaoke — built with Streamlit.")

