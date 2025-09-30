import os
import json
import random
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

# Sidebar diagnostics
st.sidebar.expander("Diagnostics (host)").write({
    "HAS_GOOGLE_CREDENTIALS": bool(GOOGLE_CREDS_RAW),
    "HAS_SHEET_KEY": bool(SHEET_KEY),
    "HAS_HOST_PIN": bool(HOST_PIN and HOST_PIN != "changeme"),
})

#############################
# Credentials & Sheets      #
#############################
creds: Optional[service_account.Credentials] = None
client = None
sheet = None

if GOOGLE_CREDS_RAW:
    try:
        info = json.loads(GOOGLE_CREDS_RAW)
        st.sidebar.write({"SERVICE_ACCOUNT_EMAIL": info.get("client_email", "(not found)")})
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
# Host Controls (PIN) — rolling “Next 3”
#############################
def _row_key(rec: Dict[str, str]) -> tuple:
    # Stable identity so row shifts don’t break the lineup
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

with st.expander("Host Controls"):
    pin = st.text_input("Enter host PIN", type="password")
    if st.button("Unlock Host Panel"):
        st.session_state["host_unlocked"] = (pin == HOST_PIN)
        if not st.session_state["host_unlocked"]:
            st.error("Incorrect PIN.")

    if st.session_state.get("host_unlocked"):
        # Current signups (includes NEW signups every rerun)
        df_all = load_signups()
        queue_df = df_all[df_all["song"].astype(str).str.len() > 0].fillna("")
        queue_df_k = _df_with_keys(queue_df)

        # Session state
        used_keys = set(st.session_state.get("used_keys", []))          # already sang
        now_key = st.session_state.get("now_singing_key")               # current singer key (or None)
        next_keys = st.session_state.get("up_next_keys", [])            # list of up to 3 keys

        # Build the available pool (exclude used, now, and already-in-next)
        all_keys = set(queue_df_k["__key__"])
        unavailable = used_keys.union(set(next_keys))
        if now_key:
            unavailable.add(now_key)
        available_keys = list(all_keys - unavailable)

        # Fill the "Next 3" window up to 3, randomly from what's available
        while len(next_keys) < 3 and available_keys:
            pick = random.choice(available_keys)
            next_keys.append(pick)
            available_keys.remove(pick)

        # Records for display
        next_records = _keys_from_df(queue_df_k, next_keys)
        now_record = None
        if now_key:
            now_pool = {k: rec for k, rec in zip(queue_df_k["__key__"], queue_df_k.to_dict("records"))}
            now_record = now_pool.get(now_key)

        # Now Singing
        st.subheader("Now Singing")
        if now_record:
            n = str(now_record.get("name", "")).strip()
            s = str(now_record.get("song", "")).strip()
            st.markdown(f"**{n}** — *{s}*")
        else:
            st.caption("No one is currently singing.")

        # Call Next Singer: promote 1, slide 2→1 & 3→2, then refill #3 randomly
        if next_records:
            display_next = next_records[0]
            name_next = str(display_next.get("name", "")).strip()
            song_next = str(display_next.get("song", "")).strip()

            if st.button("Call Next Singer"):
                # previous "now" becomes used
                if now_key:
                    used_keys.add(now_key)

                # promote first up-next to now
                now_key = next_keys.pop(0)

                # Rebuild pool (include any NEW signups)
                df_all = load_signups()
                queue_df = df_all[df_all["song"].astype(str).str.len() > 0].fillna("")
                queue_df_k = _df_with_keys(queue_df)
                all_keys = set(queue_df_k["__key__"])
                unavailable = used_keys.union(set(next_keys))
                unavailable.add(now_key)
                available_keys = list(all_keys - unavailable)

                # Backfill spot #3 randomly (if possible)
                if len(next_keys) < 3 and available_keys:
                    next_keys.append(random.choice(available_keys))

                st.success(f"Now calling {name_next} — {song_next}")

        else:
            st.info("No one in the queue yet.")

        # Up Next (Next 3)
        if next_records:
            st.subheader("Up Next (Next 3)")
            show = next_records[:3]
            lines_up = [f"- {i+1}. {r.get('name','')} — {r.get('song','')}" for i, r in enumerate(show)]
            st.markdown("\n".join(lines_up))
        else:
            st.caption("No upcoming singers.")

        # Optional: Show Full Signup List
        showing = st.session_state.get("show_full_list", False)
        label = "Hide Full Signup List" if showing else "Show Full Signup List"
        if st.button(label, key="toggle_full_list"):
            st.session_state["show_full_list"] = not showing
            showing = st.session_state["show_full_list"]
        if showing:
            q = safe_queue(queue_df)[["name", "song"]].fillna("")
            if not q.empty:
                lines = [f"- {i+1}. {r['name']} — {r['song']}" for i, r in q.iterrows()]
                st.markdown("\n".join(lines))
            else:
                st.caption("No signups yet.")

        # Skip a Singer (remove from Next 3 and backfill)
        st.subheader("Skip a Singer")
        if next_records:
            options = [f"{i+1}: {r['name']} — {r['song']}" for i, r in enumerate(next_records)]
            skip_choice = st.selectbox("Choose someone to skip (from the 'Next 3')", options=options, index=0)
            if st.button("Skip Selected"):
                idx = int(skip_choice.split(":", 1)[0]) - 1
                if 0 <= idx < len(next_keys):
                    removed_key = next_keys.pop(idx)
                    # Recompute availability and refill to keep 3 if possible
                    df_all = load_signups()
                    queue_df = df_all[df_all["song"].astype(str).str.len() > 0].fillna("")
                    queue_df_k = _df_with_keys(queue_df)
                    all_keys = set(queue_df_k["__key__"])
                    unavailable = used_keys.union(set(next_keys))
                    if now_key:
                        unavailable.add(now_key)
                    available_keys = list(all_keys - unavailable)
                    if len(next_keys) < 3 and available_keys:
                        next_keys.append(random.choice(available_keys))
                    st.success("Skipped. Filled the open spot at random from the remaining pool.")
        else:
            st.caption("No one to skip.")

        # Release a Song (delete row)
        st.subheader("Release a Song")
        if not queue_df.empty:
            df_disp = safe_queue(queue_df).fillna("")
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
                        # Clean from session state if present
                        rk = _row_key({"name": name_to_release, "phone": "", "song": song_to_release})
                        if st.session_state.get("now_singing_key") == rk:
                            st.session_state["now_singing_key"] = None
                        st.session_state["up_next_keys"] = [k for k in st.session_state.get("up_next_keys", []) if k != rk]
                        st.success(f"Removed '{song_to_release}' by {name_to_release}.")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not delete the row. ({e})")
                else:
                    st.error("Could not find that signup anymore.")
        else:
            st.caption("No signups yet.")

        # Download CSV
        csv = safe_queue(queue_df).to_csv(index=False)
        st.download_button("Download CSV", data=csv, file_name="signups.csv", mime="text/csv")

        # Reset for Next Event (also clears state)
        st.subheader("Reset for Next Event")
        if st.checkbox("Yes, clear all signups and keep headers"):
            if st.button("Reset Now"):
                try:
                    worksheet.clear()
                    worksheet.update("A1:F1", [HEADERS])
                    st.session_state.pop("up_next_keys", None)
                    st.session_state.pop("now_singing_key", None)
                    st.session_state.pop("used_keys", None)
                    st.cache_data.clear()
                    st.success("Sheet reset. Ready for the next event.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not reset the sheet. ({e})")

        # Persist updated session state
        st.session_state["up_next_keys"] = next_keys
        st.session_state["now_singing_key"] = now_key
        st.session_state["used_keys"] = list(used_keys)

# Footer + revision stamp
st.caption("Los Emos Karaoke — built with Streamlit.")
st.caption(f"Build revision: {os.getenv('K_REVISION','unknown')}")
