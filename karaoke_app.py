import os
import json
import random
from typing import Optional, Tuple, List, Dict, Set
from datetime import datetime
from pathlib import Path  # for robust logo path

import streamlit as st
import pandas as pd
from google.cloud import firestore

# --- Page config MUST be first ---
st.set_page_config(page_title="Song Selection", layout="centered")

# ------------ Config / Secrets ------------
HEADERS = ["timestamp", "name", "phone", "instagram", "song", "suggestion"]
HOST_PIN = os.getenv("HOST_PIN")  # Fail-closed if not provided
FIRESTORE_PROJECT = os.getenv("FIRESTORE_PROJECT")  # optional; defaults to current project

# ------------ Helpers ------------
def normalize_us_phone(raw: str) -> str:
    """Return a 10-digit US number. Accepts 11-digit NANP with leading '1'."""
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits

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
    # We use the raw values from Firestore here, which should be normalized strings
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
            k = obj_to_key(o)
            if k:
                out.append(k)
    return [k for k in out if k]


# ------------ Firestore Host State (Transaction Ready) ------------
def fs_read_state(transaction=None) -> dict:
    doc = (host_state_doc().get(transaction=transaction) if transaction else host_state_doc().get())

    if not doc.exists:
        # Initial state setup (can be done outside a transaction)
        state = {
            "version": 0,
            "now_key": None,
            "used_keys": [],
            "order_keys": [],
            "updated_at": datetime.utcnow().isoformat(),
        }
        if not transaction:  # Only write if not inside a transaction
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


def fs_write_state(state: dict, transaction=None):
    payload = {
        "version": int(state.get("version", 0)),
        "now_key": key_to_obj(state.get("now_key")) if state.get("now_key") else None,
        "used_keys": keys_to_objs(state.get("used_keys", [])),
        "order_keys": keys_to_objs(state.get("order_keys", [])),
        "updated_at": datetime.utcnow().isoformat(),
    }
    target_doc = host_state_doc()
    if transaction:
        transaction.set(target_doc, payload, merge=True)
    else:
        target_doc.set(payload, merge=True)


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
            seen.add(t)
            out.append(t)
    # sort alphabetically (case-insensitive)
    return sorted(out, key=lambda x: x.lower())


# ------------ Signups (Firestore) ------------
@st.cache_data(ttl=10, show_spinner=False)
def fs_signups_df() -> pd.DataFrame:
    """Return all current signups as a DataFrame (host view)."""
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


@st.cache_data(ttl=2, show_spinner=False, max_entries=8)
def fs_claimed_songs() -> Set[str]:
    """Lightweight set of currently claimed song titles for the public view."""
    q = db.collection(COL_SIGNUPS).select(["song"]).stream()
    out: Set[str] = set()
    for d in q:
        s = str((d.to_dict() or {}).get("song", "")).strip()
        if s:
            out.add(s)
    return out


def fs_find_signup_by_phone(phone_digits: str) -> Optional[Dict[str, str]]:
    """
    NOTE: Requires a single-field index on 'phone' in the 'signups' collection
    for optimal performance.
    """
    q = db.collection(COL_SIGNUPS).where("phone", "==", phone_digits).limit(1).stream()
    for d in q:
        rec = d.to_dict()
        rec["id"] = d.id
        return rec
    return None


def fs_is_song_claimed(song_title: str) -> bool:
    """Fresh check to reduce double-claim race (best-effort; not fully atomic)."""
    if not song_title:
        return False
    q = db.collection(COL_SIGNUPS).where("song", "==", song_title).limit(1).stream()
    for _ in q:
        return True
    return False


def fs_add_signup(name: str, phone_digits: str, instagram: str, song: str, suggestion: str) -> bool:
    """Best-effort safe add: re-checks phone + song just before write."""
    try:
        if fs_find_signup_by_phone(phone_digits):
            return False
        if fs_is_song_claimed(song):
            return False
        db.collection(COL_SIGNUPS).add(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "name": name,
                "phone": phone_digits,
                "instagram": instagram,
                "song": song,
                "suggestion": suggestion,
            }
        )
        return True
    except Exception:
        return False


def fs_delete_signup_by_id(doc_id: str) -> bool:
    try:
        db.collection(COL_SIGNUPS).document(doc_id).delete()
        return True
    except Exception:
        return False


# ------------ Targeted cache invalidation ------------
def _invalidate_data_caches():
    """Only clear the data caches that reflect signups/claimed songs."""
    try:
        fs_signups_df.clear()
    except Exception:
        pass
    try:
        fs_claimed_songs.clear()
    except Exception:
        pass


# ------------ UI Header ------------
col_l, col_c, col_r = st.columns([1, 2, 1])
with col_c:
    logo_path = Path(__file__).resolve().parent / "logo.png"
    if logo_path.exists():
        st.image(str(logo_path))
    else:
        st.caption(" ")
        st.warning(f"Logo not found at {logo_path.name}. Put logo.png next to karaoke_app.py or update the path.")

st.markdown("<h1 style='text-align:center;margin:0;'>Song Selection</h1>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;margin:0;'>One song per person. Once it's claimed, it disappears.</p>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='text-align:center;margin:6px 0;'><a href='https://instagram.com/losemoskaraoke' target='_blank'>Follow us on Instagram</a></p>",
    unsafe_allow_html=True,
)
st.divider()

# Persistent success banner (signup) — lingers until dismissed
if st.session_state.get("signup_success"):
    _msg = st.session_state["signup_success"]
    if isinstance(_msg, dict) and _msg.get("song"):
        who = f" { _msg.get('name','') }" if _msg.get("name") else ""
        st.success(f"You're in{who}! You've signed up to sing '{_msg['song']}'.")
        if st.button("Dismiss", key="dismiss_success"):
            st.session_state["signup_success"] = None
            st.rerun()

# Persistent undo banner — lingers until dismissed
if st.session_state.get("undo_success"):
    _umsg = st.session_state["undo_success"]
    if isinstance(_umsg, dict) and _umsg.get("song"):
        name_txt = f" for {_umsg.get('name','')}" if _umsg.get("name") else ""
        st.success(f"Removed your signup{name_txt}: '{_umsg['song']}'.")
        if st.button("Dismiss", key="dismiss_undo_success"):
            st.session_state["undo_success"] = None
            st.rerun()

st.divider()


# ------------ Public Signup Form ------------
# Load static lists + lightweight claimed songs for the public view
all_songs = fs_load_songs()
if not all_songs:
    st.warning("No songs found in the songs collection.")
claimed_songs = fs_claimed_songs()
available_songs = [s for s in all_songs if s and s not in claimed_songs]

with st.form("signup_form", clear_on_submit=False):
    # --- Pick song FIRST so mobile keyboard isn't up ---
    # Preserve user's last selection even if it disappears on rerun
    prev_choice = st.session_state.get("song_select", "")

    if available_songs:
        st.selectbox(
            "Pick your song",
            options=available_songs,
            index=None,                      # start unselected, no dummy ""
            placeholder="— select a song —",
            key="song_select",
        )
    else:
        st.selectbox(
            "Pick your song",
            options=[],
            index=None,
            placeholder="No songs available",
            key="song_select",
            disabled=True,
        )

    current_choice = st.session_state.get("song_select", "")
    attempted_song = current_choice or prev_choice

    # Detect “vanished” selection (someone else claimed it) AFTER rendering widget
    vanished = bool(prev_choice and (prev_choice not in available_songs) and (current_choice in ("", None)))

    # --- Then collect text inputs (keyboard opens AFTER the select interaction) ---
    name = st.text_input("Your Name", max_chars=60)

    phone_raw = st.text_input("Phone (US, 10 digits)")
    digits = normalize_us_phone(phone_raw)
    if phone_raw:
        # Always show sanitized preview
        if len(digits) >= 10:
            st.caption(f"Digits: {digits[0:3]}-{digits[3:6]}-{digits[6:10]}")
        else:
            st.caption(f"Digits so far: {digits}")

    instagram = st.text_input("Instagram (optional)", placeholder="@yourhandle")
    instagram = instagram.strip().lstrip("@").strip().lower() if instagram else ""

    suggestion = st.text_input("Song suggestion (optional)")

    submit = st.form_submit_button("Submit Signup")

    errs = []
    if submit:
        if not name.strip():
            errs.append("Please enter your name.")
        if len(digits) != 10:
            errs.append("Please enter a valid US phone (10 digits; country code '1' is OK).")

        if vanished:
            # User tried to submit a song that vanished; show one clear error.
            errs.append(f"Sorry, '{prev_choice}' was just claimed. Pick another.")
        else:
            if not attempted_song:
                errs.append("Please select a song.")
            elif (attempted_song in claimed_songs) or fs_is_song_claimed(attempted_song):
                errs.append(f"Sorry, '{attempted_song}' was just claimed. Pick another.")

            if not errs and fs_find_signup_by_phone(digits):
                errs.append("This phone number already signed up.")

        if errs:
            for e in errs:
                st.error(e)
        else:
            ok = fs_add_signup(name.strip(), digits, instagram.strip(), attempted_song, suggestion.strip())
            if ok:
                st.session_state["signup_success"] = {"song": attempted_song, "name": name.strip()}
                _invalidate_data_caches()  # targeted cache clear
                st.rerun()
            else:
                st.error(
                    f"Could not save your signup — '{attempted_song}' may have just been claimed. Please pick another."
                )

    # Show the “vanished” heads-up only when NOT submitting and not after success.
    if (not submit) and vanished and not st.session_state.get("signup_success"):
        st.warning(f"Looks like '{prev_choice}' was just claimed by another singer. Please pick another.")


# Undo signup
with st.expander("Undo My Signup"):
    undo_phone_raw = st.text_input(
        "Enter the phone number you signed up with (10 digits)", key="undo_phone"
    )
    u_digits = normalize_us_phone(undo_phone_raw)
    do_undo = st.button("Undo My Signup")
    if do_undo:
        if len(u_digits) != 10:
            st.error("Please enter a valid US phone (10 digits).")
        else:
            rec = fs_find_signup_by_phone(u_digits)
            if rec and rec.get("id"):
                if fs_delete_signup_by_id(rec["id"]):
                    # Prepare persistent success message that lingers until dismissed
                    st.session_state["undo_success"] = {
                        "song": rec.get("song", ""),
                        "name": rec.get("name", ""),
                    }

                    # Clean from state (mirror Release cleanup)
                    state_cleanup = fs_read_state()
                    key_to_release = key_from_record(
                        {"name": rec.get("name", ""), "phone": rec.get("phone", ""), "song": rec.get("song", "")}
                    )
                    changed = False
                    if state_cleanup.get("now_key") == key_to_release:
                        state_cleanup["now_key"] = None
                        changed = True
                    if key_to_release in state_cleanup.get("order_keys", []):
                        state_cleanup["order_keys"] = [
                            k for k in state_cleanup["order_keys"] if k != key_to_release
                        ]
                        changed = True
                    if key_to_release in state_cleanup.get("used_keys", []):
                        state_cleanup["used_keys"] = [
                            k for k in state_cleanup["used_keys"] if k != key_to_release
                        ]
                        changed = True
                    if changed:
                        bump_version(state_cleanup)
                        fs_write_state(state_cleanup)

                    _invalidate_data_caches()  # targeted cache clear
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


# Transactional function for calling the next singer
@firestore.transactional
def call_next_singer_txn(transaction, all_keys_set):
    """Atomically moves the next singer to 'now_key' and moves 'now_key' to 'used_keys'."""
    state = fs_read_state(transaction=transaction)

    now_key = state.get("now_key")
    used_keys = list(state.get("used_keys", []))
    order_keys = list(state.get("order_keys", []))
    used_set = set(used_keys)

    # 1. Normalize the queue (re-run as part of transaction)
    order_keys = [k for k in order_keys if (k in all_keys_set and k not in used_set and k != now_key)]

    # 2. Previous 'now' becomes 'used'
    if now_key and now_key not in used_set:
        used_keys.append(now_key)

    # 3. Pop first from order to become new 'now'
    new_now_key = order_keys.pop(0) if order_keys else None

    # 4. Save and bump version
    state["now_key"] = new_now_key
    state["used_keys"] = used_keys
    state["order_keys"] = order_keys
    bump_version(state)

    fs_write_state(state, transaction=transaction)
    return new_now_key  # Return the new now_key for UI message


# Transactional function for skipping a singer
@firestore.transactional
def skip_singer_txn(transaction, choice_type, choice_key):
    """Atomically moves the selected singer down two places in the queue."""
    state = fs_read_state(transaction=transaction)
    order_keys = list(state.get("order_keys", []))
    now_key = state.get("now_key")

    if choice_type == "current":
        if now_key != choice_key:
            raise ValueError("Current key mismatch during skip transaction.")

        # Remove any stray occurrence of current in order_keys to prevent duplicates
        order_keys = [k for k in order_keys if k != choice_key]

        insert_at = min(2, len(order_keys))
        order_keys.insert(insert_at, choice_key)
        new_now_key = None

        state["now_key"] = new_now_key
        state["order_keys"] = order_keys
        bump_version(state)
        fs_write_state(state, transaction=transaction)
        return "current"

    else:  # skipping from Next 3
        if choice_key in order_keys:
            old_pos = order_keys.index(choice_key)
            new_pos = min(old_pos + 2, len(order_keys))  # insert allows len() for end
            order_keys.pop(old_pos)
            order_keys.insert(new_pos, choice_key)

            state["order_keys"] = order_keys
            bump_version(state)
            fs_write_state(state, transaction=transaction)
            return "next"
        else:
            return None


with st.expander("Host Controls"):
    # Host PIN must be configured; fail-closed
    if not HOST_PIN or not HOST_PIN.strip() or HOST_PIN.strip().lower() == "changeme":
        st.error("Host PIN is not configured. Set HOST_PIN in the environment to unlock host controls.")
    else:
        pin = st.text_input("Enter host PIN", type="password")
        if st.button("Unlock Host Panel"):
            st.session_state["host_unlocked"] = (pin == HOST_PIN)
            if not st.session_state["host_unlocked"]:
                st.error("Incorrect PIN.")

    if st.session_state.get("host_unlocked"):
        # Manual refresh: only invalidate relevant data caches
        if st.button("Refresh host view"):
            _invalidate_data_caches()
            st.rerun()

        # Current signups and keys (host needs full rows)
        df_all = fs_signups_df()
        queue_df = df_all[df_all["song"].astype(str).str.len() > 0].fillna("")
        queue_df_k = _df_with_keys(queue_df)
        all_keys_set = set(queue_df_k["__key__"])

        # Load shared state
        state = fs_read_state()
        used_keys = list(state["used_keys"]) if state else []
        used_set = set(used_keys)
        now_key = state.get("now_key") if state else None
        order_keys: List[tuple] = list(state["order_keys"]) if state else []

        # Normalize order: drop missing/used/now; add new signups at end (random order if many)
        order_keys_normalized = [k for k in order_keys if (k in all_keys_set and k not in used_set and k != now_key)]
        new_candidates = list(all_keys_set - used_set - ({now_key} if now_key else set()) - set(order_keys_normalized))

        if new_candidates or len(order_keys_normalized) != len(order_keys):
            if new_candidates:
                random.shuffle(new_candidates)
                order_keys_normalized.extend(new_candidates)

            # Background normalization write
            state["order_keys"] = order_keys_normalized
            bump_version(state)
            fs_write_state(state)
            order_keys = order_keys_normalized

        # Build records
        order_records = _keys_from_df(queue_df_k, order_keys)
        if now_key:
            rp = {k: rec for k, rec in zip(queue_df_k["__key__"], queue_df_k.to_dict("records"))}
            now_record = rp.get(now_key)
        else:
            rp = {k: rec for k, rec in zip(queue_df_k["__key__"], queue_df_k.to_dict("records"))}
            now_record = None

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

        # CALL NEXT SINGER (Transactional)
        if next_slice and st.button("Call Next Singer"):
            try:
                transaction = db.transaction()
                new_now_key = call_next_singer_txn(transaction, all_keys_set)

                if new_now_key:
                    rec = rp.get(new_now_key)
                    if rec:
                        st.success(f"Now calling {str(rec.get('name','')).strip()} — {str(rec.get('song','')).strip()}")
                    else:
                        st.success("Now calling the next singer.")
                else:
                    st.success("Queue is empty. Cleared 'Now Singing' slot.")

                # No data cache invalidation needed (host state changed only)
                st.rerun()
            except Exception as e:
                st.error(f"Error calling next singer (transaction failed): {e}")

        # UNIFIED SKIP (Transactional)
        st.subheader("Skip")
        skip_options = []
        skip_keys = []

        if now_record and now_key:
            label_cur = f"Current: {now_record.get('name','')} — {now_record.get('song','')}"
            skip_options.append(label_cur)
            skip_keys.append(("current", now_key))

        for i, r in enumerate(next_slice):
            label_n = f"Next {i+1}: {r.get('name','')} — {r.get('song','')}"
            skip_options.append(label_n)
            skip_keys.append(("next", key_from_record(r)))

        if skip_options:
            sel = st.selectbox("Choose who to skip", options=skip_options, index=0, key="unified_skip_choice")
            if st.button("Skip Selected"):
                try:
                    choice_type, choice_key = skip_keys[skip_options.index(sel)]
                    transaction = db.transaction()
                    result = skip_singer_txn(transaction, choice_type, choice_key)

                    if result:
                        st.success("Skipped — moved that singer down two places.")
                    else:
                        st.error("Could not find the singer in the current queue to skip.")

                    # No data cache invalidation needed (host state changed only)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error skipping singer (transaction failed): {e}")
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

        # RELEASE A SONG (delete signup)
        st.subheader("Release a Song")
        if not queue_df.empty:
            id_to_data = {}
            for _, r in queue_df.iterrows():
                doc_id = r["id"]
                display_label = f"{r['name']} — {r['song']} (…{str(r['phone'])[-4:]})"
                id_to_data[doc_id] = {
                    "label": display_label,
                    "key": key_from_record({"name": r["name"], "phone": r["phone"], "song": r["song"]}),
                }

            options = [""] + list(id_to_data.keys())
            release_choice = st.selectbox(
                "Select signup to remove",
                options=options,
                index=0,
                format_func=lambda doc_id: "— select —" if doc_id == "" else id_to_data[doc_id]["label"],
            )

            confirm_release = st.checkbox("Yes, remove this signup")
            if release_choice and confirm_release and st.button("Remove Selected Signup"):
                doc_id_to_release = release_choice
                key_to_release = id_to_data[doc_id_to_release]["key"]
                ok = fs_delete_signup_by_id(doc_id_to_release)
                if ok:
                    state_cleanup = fs_read_state()
                    changed = False
                    if state_cleanup.get("now_key") == key_to_release:
                        state_cleanup["now_key"] = None
                        changed = True
                    if key_to_release in state_cleanup.get("order_keys", []):
                        state_cleanup["order_keys"] = [k for k in state_cleanup["order_keys"] if k != key_to_release]
                        changed = True
                    if key_to_release in state_cleanup.get("used_keys", []):
                        state_cleanup["used_keys"] = [k for k in state_cleanup["used_keys"] if k != key_to_release]
                        changed = True

                    if changed:
                        bump_version(state_cleanup)
                        fs_write_state(state_cleanup)

                    st.success("Signup removed.")
                    _invalidate_data_caches()  # targeted cache clear
                    st.rerun()
                else:
                    st.error("Could not delete the signup. Try again.")
        else:
            st.caption("No signups yet.")

        # DOWNLOAD CSV
        csv_df = queue_df[["timestamp", "name", "phone", "instagram", "song", "suggestion"]].copy()
        st.download_button(
            "Download CSV", data=csv_df.to_csv(index=False), file_name="signups.csv", mime="text/csv"
        )

        # RESET FOR NEXT EVENT (Non-transactional, but highly destructive)
        st.subheader("Reset for Next Event")
        st.warning("This will permanently delete all signups and host history!")
        if st.checkbox("Yes, clear all signups and host state", key="confirm_reset_checkbox"):
            if st.button("Reset Now", key="final_reset_button"):
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

                # Targeted cache clears (and resources if desired)
                try:
                    _invalidate_data_caches()
                except Exception:
                    pass
                try:
                    st.cache_resource.clear()
                except Exception:
                    pass

                st.success("Cleared. Ready for the next event.")
                st.rerun()

# Footer
st.caption("Los Emos Karaoke — built with Streamlit.")
st.caption(f"Build revision: {os.getenv('K_REVISION','unknown')}")
