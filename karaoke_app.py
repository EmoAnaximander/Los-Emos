import os
import json
import random
from typing import Optional, Tuple, List, Dict
from datetime import datetime

import streamlit as st
import pandas as pd
from google.cloud import firestore

# --- Page config MUST be first ---
st.set_page_config(page_title="Song Selection", layout="centered")

# ------------ Config / Secrets ------------
HEADERS = ["timestamp", "name", "phone", "instagram", "song", "suggestion"]
HOST_PIN = os.getenv("HOST_PIN", "changeme")
FIRESTORE_PROJECT = os.getenv("FIRESTORE_PROJECT")  # optional; defaults to current project

# ------------ Firestore client ------------
@st.cache_resource
def fs_client():
    if FIRESTORE_PROJECT:
        return firestore.Client(project=FIRESTORE_PROJECT)
    return firestore.Client()

db = fs_client()
COL_SIGNUPS = "signups"
COL_SONGS = "songs"
COL_APP = "karaoke"
DOC_HOST_STATE = "host_state"

def host_state_doc():
    return db.collection(COL_APP).document(DOC_HOST_STATE)

# ------------ Host-state key (tuple) <-> Firestore object (map) ------------
def key_from_record(rec: Dict[str, str]) -> tuple:
    """Normalize a record into our stable queue key: (name_lower, digits_phone, song)."""
    return (
        str(rec.get("name", "")).strip().lower(),
        "".join(ch for ch in str(rec.get("phone", "")) if ch.isdigit()),
        str(rec.get("song", "")).strip(),
    )

def key_to_obj(key_tup: tuple) -> Optional[dict]:
    """('name','phone','song') -> {'n':..., 'p':..., 's':...} or None."""
    if not key_tup:
        return None
    n, p, s = (key_tup + ("", "", ""))[:3]
    return {"n": n, "p": p, "s": s}

def obj_to_key(obj: Optional[dict]) -> Optional[tuple]:
    """{'n':...,'p':...,'s':...} -> ('name','phone','song') or None."""
    if not obj or not isinstance(obj, dict):
        return None
    return (str(obj.get("n", "")), str(obj.get("p", "")), str(obj.get("s", "")))

def keys_to_objs(keys: List[tuple]) -> List[dict]:
    return [key_to_obj(k) for k in keys if k]

def objs_to_keys(objs: List[dict]) -> List[tuple]:
    """Accepts both new (map) and stray old (list) formats for backward-compat."""
    out = []
    for o in objs or []:
        if isinstance(o, list) and len(o) >= 3:
            out.append((str(o[0]), str(o[1]), str(o[2])))
        elif isinstance(o, dict):
            out.append(obj_to_key(o))
    return [k for k in out if k]

# ------------ Firestore Host State ------------
def fs_read_state() -> dict:
    doc = host_state_doc().get()
    if not doc.exists:
        state = {
            "version": 0,
            "now_key": None,          # stored as map or null
            "used_keys": [],          # array of maps
            "order_keys": [],         # array of maps
            "updated_at": datetime.utcnow().isoformat(),
        }
        host_state_doc().set(state)
        return {"version": 0, "now_key": None, "used_keys": [], "order_keys": []}

    data = doc.to_dict() or {}

    # now_key can be map (new) or list (legacy)
    raw_now = data.get("now_key")
    if isinstance(raw_now, list) and len(raw_now) >= 3:
        now_key = (str(raw_now[0]), str(raw_now[1]), str(raw_now[2]))
    else:
        now_key = obj_to_key(raw_now)

    used_keys = objs_to_keys(data.get("used_keys", []))
    order_keys = objs_to_keys(data.get("order_keys", []))

    return {
        "version": int(data.get("version", 0)),
        "now_key": now_key,
        "used_keys": used_keys,
        "order_keys": order_keys,
    }

def fs_write_state(state: dict):
    payload = {
        "version": int(state.get("version", 0)),
        "now_key": key_to_obj(state.get("now_key")) if state.get("now_key") else None,
        "used_keys": keys_to_objs(state.get("used_keys", [])),
        "order_keys": keys_to_objs(state.get("order_keys", [])),
        "updated_at": datetime.utcnow().isoformat(),
    }
    host_state_doc().set(payload, merge=True)

def bump_version(state: dict):
    state["version"] = int(state.get("version", 0)) + 1

# ------------ Songs (Firestore) ------------
@st.cache_data(ttl=120, show_spinner=False)
def fs_load_songs() -> List[str]:
    docs = list(db.collection(COL_SONGS).stream())
    titles = []
    for d in docs:
        data = d.to_dict() or {}
        t = str(data.get("title", "")).strip()
        if t:
            titles.append(t)
    # de-dup while preserving order
    seen, out = set(), []
    for t in titles:
        if t not in seen:
            seen.add(t); out.append(t)
    return out

# ------------ Signups (Firestore) ------------
@st.cache_data(ttl=30, show_spinner=False)
def fs_signups_df() -> pd.DataFrame:
    """Return all current signups as a DataFrame."""
    docs = list(db.collection(COL_SIGNUPS).stream())
    rows = []
    for d in docs:
        data = d.to_dict() or {}
        row = {
            "id": d.id,
            "timestamp": data.get("timestamp", ""),
            "name": str(data.get("name", "")),
            "phone": "".join(ch for ch in str(data.get("phone", "")) if ch.isdigit()),
            "instagram": str(data.get("instagram", "")),
            "song": str(data.get("song", "")),
            "suggestion": str(data.get("suggestion", "")),
        }
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=["id"] + HEADERS)
    df = pd.DataFrame(rows)
    for col in ["id"] + HEADERS:
        if col not in df.columns:
            df[col] = ""
    return df[["id"] + HEADERS]

def fs_find_signup_by_phone(phone_digits: str) -> Optional[Dict[str, str]]:
    q = db.collection(COL_SIGNUPS).where("phone", "==", phone_digits).limit(1).stream()
    for d in q:
        rec = d.to_dict(); rec["id"] = d.id
        return rec
    return None

def fs_add_signup(name: str, phone_digits: str, instagram: str, song: str, suggestion: str) -> bool:
    try:
        db.collection(COL_SIGNUPS).add({
            "timestamp": datetime.utcnow().isoformat(),
            "name": name, "phone": phone_digits, "instagram": instagram,
            "song": song, "suggestion": suggestion
        })
        return True
    except Exception:
        return False

def fs_delete_signup_by_id(doc_id: str) -> bool:
    try:
        db.collection(COL_SIGNUPS).document(doc_id).delete()
        return True
    except Exception:
        return False

# ------------ UI Header ------------
col_l, col_c, col_r = st.columns([1, 2, 1])
with col_c:
    try:
        st.image("logo.png", caption=None)
    except Exception:
        pass

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

# ------------ Public Signup Form ------------
df = fs_signups_df()
claimed_songs = set(df["song"].dropna().astype(str).tolist())

all_songs = fs_load_songs()
if not all_songs:
    st.warning("No songs found in the songs collection.")
available_songs = [s for s in all_songs if s and s not in claimed_songs]

with st.form("signup_form", clear_on_submit=True):
    name = st.text_input("Your Name", max_chars=60)
    phone_raw = st.text_input("Phone (10 digits)")
    digits = "".join(ch for ch in phone_raw if ch.isdigit())
    if phone_raw and 4 <= len(digits) <= 10:
        st.caption(f"Formatted: {digits[0:3]}-{digits[3:6]}-{digits[6:10]}" if len(digits) >= 10 else phone_raw)

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
        if not errs and fs_find_signup_by_phone(digits):
            errs.append("This phone number already signed up.")
        if not errs and song in claimed_songs:
            errs.append("Sorry, that song was just claimed. Pick another.")

        if errs:
            for e in errs:
                st.error(e)
        else:
            ok = fs_add_signup(name.strip(), digits, instagram.strip(), song, suggestion.strip())
            if ok:
                st.session_state["signup_success"] = {"song": song, "name": name.strip()}
                st.cache_data.clear()
                st.rerun()
            else:
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
            rec = fs_find_signup_by_phone(u_digits)
            if rec and rec.get("id"):
                if fs_delete_signup_by_id(rec["id"]):
                    st.success("Your signup has been removed.")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Could not remove your signup. Please try again.")
            else:
                st.error("No signup found for that phone number.")

st.divider()
st.info("We won't share your data. Phone numbers ensure everyone only signs up for one song.")

# Full song list with claimed struck through
st.subheader("All Songs")
if all_songs:
    lines = []
    for s in all_songs:
        if s in claimed_songs:
            lines.append(f"- ~~{s}~~")
        else:
            lines.append(f"- {s}")
    st.markdown("\n".join(lines))
else:
    st.caption("No songs found yet.")

# ------------ Host Controls (shared via Firestore) ------------
def _row_key(rec: Dict[str, str]) -> tuple:
    return key_from_record(rec)

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
        # Manual refresh
        if st.button("Refresh host view"):
            st.cache_data.clear()
            st.rerun()

        # Current signups and keys
        df_all = fs_signups_df()
        queue_df = df_all[df_all["song"].astype(str).str.len() > 0].fillna("")
        queue_df_k = _df_with_keys(queue_df)
        all_keys_set = set(queue_df_k["__key__"])

        # Load shared state
        state = fs_read_state()
        used_keys = list(state["used_keys"])
        used_set = set(used_keys)
        now_key = state["now_key"]
        order_keys: List[tuple] = list(state["order_keys"])

        # Normalize order: drop missing/used/now; add new signups at end (random order if many)
        order_keys = [k for k in order_keys if (k in all_keys_set and k not in used_set and k != now_key)]
        new_candidates = list(all_keys_set - used_set - ({now_key} if now_key else set()) - set(order_keys))
        if new_candidates:
            random.shuffle(new_candidates)
            order_keys.extend(new_candidates)

        if order_keys != state["order_keys"]:
            state["order_keys"] = order_keys
            bump_version(state)
            fs_write_state(state)

        # Build records
        order_records = _keys_from_df(queue_df_k, order_keys)
        now_record = None
        if now_key:
            rp = {k: rec for k, rec in zip(queue_df_k["__key__"], queue_df_k.to_dict("records"))}
            now_record = rp.get(now_key)

        # Now Singing
        st.subheader("Now Singing")
        if now_record:
            n = str(now_record.get("name", "")).strip()
            s = str(now_record.get("song", "")).strip()
            st.markdown(f"**{n}** — *{s}*")
        else:
            st.caption("No one is currently singing.")

        # Up Next — first three in order_keys
        next_slice = order_records[:3]
        if next_slice:
            st.subheader("Up Next (Next 3)")
            lines_up = [f"- {i+1}. {r.get('name','')} — {r.get('song','')}" for i, r in enumerate(next_slice)]
            st.markdown("\n".join(lines_up))
        else:
            st.caption("No upcoming singers.")

        # CALL NEXT SINGER — move slot #1 to NOW SINGING automatically
        if next_slice:
            first = next_slice[0]
            name_next = str(first.get("name", "")).strip()
            song_next = str(first.get("song", "")).strip()

            if st.button("Call Next Singer"):
                # previous now becomes used
                if now_key and now_key not in used_set:
                    used_set.add(now_key)
                    used_keys.append(now_key)

                # pop first from order to become now
                if order_keys:
                    now_key = order_keys.pop(0)

                # save & refresh
                state["now_key"] = now_key
                state["used_keys"] = used_keys
                state["order_keys"] = order_keys
                bump_version(state)
                fs_write_state(state)
                st.success(f"Now calling {name_next} — {song_next}")
                st.rerun()

        # UNIFIED SKIP (current or one of Next 3) — moves down two places
        st.subheader("Skip")
        skip_options = []
        skip_keys = []

        # option: current singer
        if now_record and now_key:
            label_cur = f"Current: {now_record.get('name','')} — {now_record.get('song','')}"
            skip_options.append(label_cur)
            skip_keys.append(("current", now_key))

        # options: next 3
        for i, r in enumerate(next_slice):
            label_n = f"Next {i+1}: {r.get('name','')} — {r.get('song','')}"
            skip_options.append(label_n)
            skip_keys.append(("next", key_from_record(r)))

        if skip_options:
            sel = st.selectbox("Choose who to skip", options=skip_options, index=0, key="unified_skip_choice")
            if st.button("Skip Selected"):
                choice_type, choice_key = skip_keys[skip_options.index(sel)]
                order_keys = list(state.get("order_keys", []))

                if choice_type == "current":
                    # Insert current singer two spots down from the front of the queue
                    insert_at = min(2, len(order_keys))
                    order_keys.insert(insert_at, choice_key)
                    # Clear now
                    now_key = None

                    state["now_key"] = now_key
                    state["order_keys"] = order_keys
                    bump_version(state)
                    fs_write_state(state)
                    st.success("Skipped current singer — moved them down two places.")
                    st.rerun()

                else:  # skipping from Next 3
                    if choice_key in order_keys:
                        old_pos = order_keys.index(choice_key)
                        new_pos = min(old_pos + 2, len(order_keys) - 1)
                        order_keys.pop(old_pos)
                        order_keys.insert(new_pos, choice_key)

                        state["order_keys"] = order_keys
                        bump_version(state)
                        fs_write_state(state)
                        st.success("Skipped — moved that singer down two places.")
                        st.rerun()
        else:
            st.caption("No one available to skip.")

        # SHOW REMAINING (only those who have not performed), in order
        showing = st.session_state.get("show_full_list", False)
        label = "Hide Remaining Signup List" if showing else "Show Remaining Signup List"
        if st.button(label, key="toggle_full_list"):
            st.session_state["show_full_list"] = not showing
            showing = st.session_state["show_full_list"]

        if showing:
            remaining = _keys_from_df(queue_df_k, order_keys)
            if remaining:
                st.subheader("Remaining (in order)")
                lines = [f"- {i+1}. {r.get('name','')} — {r.get('song','')}" for i, r in enumerate(remaining)]
                st.markdown("\n".join(lines))
            else:
                st.caption("No remaining signups.")

        # RELEASE A SONG (delete signup) — remove from state if present
        st.subheader("Release a Song")
        if not queue_df.empty:
            df_disp = queue_df.copy()
            df_disp["label"] = df_disp.apply(
                lambda r: f"{r['name']} — {r['song']} (…{str(r['phone'])[-4:]})", axis=1
            )
            # map label -> doc_id
            label_to_id = {}
            for _, r in df_disp.iterrows():
                matches = df_all[(df_all["phone"] == r["phone"]) & (df_all["song"] == r["song"])]
                doc_id = matches.iloc[0]["id"] if not matches.empty else ""
                label_to_id[r["label"]] = doc_id

            release_label = st.selectbox("Select signup to remove", options=[""] + df_disp["label"].tolist(), index=0)
            confirm_release = st.checkbox("Yes, remove this signup")
            if release_label and confirm_release and st.button("Remove Selected Signup"):
                doc_id = label_to_id.get(release_label, "")
                if doc_id:
                    ok = fs_delete_signup_by_id(doc_id)
                    if ok:
                        # also clean from state if present
                        try:
                            name_to_release, tail = release_label.split(" — ", 1)
                            song_to_release = tail.split(" (", 1)[0]
                        except Exception:
                            name_to_release, song_to_release = "", ""
                        rk = key_from_record({"name": name_to_release, "phone": "", "song": song_to_release})
                        changed = False
                        if state.get("now_key") == rk:
                            state["now_key"] = None; changed = True
                        if rk in state.get("order_keys", []):
                            state["order_keys"] = [k for k in state["order_keys"] if k != rk]; changed = True
                        if rk in state.get("used_keys", []):
                            state["used_keys"] = [k for k in state["used_keys"] if k != rk]; changed = True
                        if changed:
                            bump_version(state)
                            fs_write_state(state)

                        st.success("Signup removed.")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("Could not delete the signup. Try again.")
                else:
                    st.error("Could not find that signup anymore.")
        else:
            st.caption("No signups yet.")

        # DOWNLOAD CSV
        csv_df = queue_df[["timestamp","name","phone","instagram","song","suggestion"]].copy()
        st.download_button("Download CSV", data=csv_df.to_csv(index=False), file_name="signups.csv", mime="text/csv")

        # RESET FOR NEXT EVENT — clears Signups and HostState
        st.subheader("Reset for Next Event")
        if st.checkbox("Yes, clear all signups and host state"):
            if st.button("Reset Now"):
                # delete all signups (batch)
                batch = db.batch()
                for d in db.collection(COL_SIGNUPS).stream():
                    batch.delete(d.reference)
                batch.commit()
                # reset host state
                fs_write_state({
                    "version": 0,
                    "now_key": None,
                    "used_keys": [],
                    "order_keys": [],
                })
                st.cache_data.clear()
                st.success("Cleared. Ready for the next event.")
                st.rerun()

# Footer
st.caption("Los Emos Karaoke — built with Streamlit.")
st.caption(f"Build revision: {os.getenv('K_REVISION','unknown')}")

