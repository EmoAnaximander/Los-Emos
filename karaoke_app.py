import os
import random
import re
import hashlib
from typing import Optional, List, Dict, Set
from datetime import datetime
from pathlib import Path

import streamlit as st
import pandas as pd
from google.cloud import firestore

st.set_page_config(page_title="Song Selection", layout="centered")

HEADERS = ["timestamp", "name", "phone", "instagram", "song", "suggestion"]
HOST_PIN = os.getenv("HOST_PIN")
FIRESTORE_PROJECT = os.getenv("FIRESTORE_PROJECT")


def normalize_us_phone(raw: str) -> str:
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def song_doc_id(song: str) -> str:
    s = (song or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60]
    h = hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]
    return f"{slug}-{h}" if slug else h


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
COL_SONG_CLAIMS = "song_claims"
COL_PERFORMED = "performed"


def host_state_doc():
    return db.collection(COL_APP).document(DOC_HOST_STATE)


def key_from_record(rec: Dict[str, str]) -> tuple:
    return (
        str(rec.get("name", "")).strip().lower(),
        "".join(ch for ch in str(rec.get("phone", "")) if ch.isdigit()),
        str(rec.get("song", "")).strip(),
    )


def key_to_obj(key_tup: tuple) -> Optional[dict]:
    if not key_tup:
        return None
    n, p, s = (key_tup + ("", "", ""))[:3]
    return {"n": n, "p": p, "s": s}


def obj_to_key(obj: Optional[dict]) -> Optional[tuple]:
    if not obj or not isinstance(obj, dict):
        return None
    return (str(obj.get("n", "")), str(obj.get("p", "")), str(obj.get("s", "")))


def keys_to_objs(keys: List[tuple]) -> List[dict]:
    return [key_to_obj(k) for k in keys if k]


def objs_to_keys(objs: List[dict]) -> List[tuple]:
    out = []
    for o in objs or []:
        if isinstance(o, list) and len(o) >= 3:
            out.append((str(o[0]), str(o[1]), str(o[2])))
        elif isinstance(o, dict):
            k = obj_to_key(o)
            if k:
                out.append(k)
    return [k for k in out if k]


def fs_read_state(transaction=None) -> dict:
    doc = host_state_doc().get(transaction=transaction) if transaction else host_state_doc().get()

    if not doc.exists:
        state = {
            "version": 0,
            "now_key": None,
            "used_keys": [],
            "order_keys": [],
            "updated_at": datetime.utcnow().isoformat(),
        }
        if not transaction:
            host_state_doc().set(state)
        return {"version": 0, "now_key": None, "used_keys": [], "order_keys": []}

    data = doc.to_dict() or {}

    raw_now = data.get("now_key")
    if isinstance(raw_now, list) and len(raw_now) >= 3:
        now_key = (str(raw_now[0]), str(raw_now[1]), str(raw_now[2]))
    else:
        now_key = obj_to_key(raw_now)

    return {
        "version": int(data.get("version", 0)),
        "now_key": now_key,
        "used_keys": objs_to_keys(data.get("used_keys", [])),
        "order_keys": objs_to_keys(data.get("order_keys", [])),
    }


def fs_write_state(state: dict, transaction=None):
    payload = {
        "version": int(state.get("version", 0)),
        "now_key": key_to_obj(state.get("now_key")) if state.get("now_key") else None,
        "used_keys": keys_to_objs(state.get("used_keys", [])),
        "order_keys": keys_to_objs(state.get("order_keys", [])),
        "updated_at": datetime.utcnow().isoformat(),
    }

    if transaction:
        transaction.set(host_state_doc(), payload, merge=True)
    else:
        host_state_doc().set(payload, merge=True)


def bump_version(state: dict):
    state["version"] = int(state.get("version", 0)) + 1


@st.cache_data(ttl=120, show_spinner=False)
def fs_load_songs() -> List[str]:
    docs = list(db.collection(COL_SONGS).stream())
    titles = []

    for d in docs:
        data = d.to_dict() or {}
        title = str(data.get("title", "")).strip()
        if title:
            titles.append(title)

    seen, out = set(), []
    for title in titles:
        if title not in seen:
            seen.add(title)
            out.append(title)

    return sorted(out, key=lambda x: x.lower())


@st.cache_data(ttl=10, show_spinner=False)
def fs_signups_df() -> pd.DataFrame:
    docs = list(db.collection(COL_SIGNUPS).stream())
    rows = []

    for d in docs:
        data = d.to_dict() or {}
        rows.append(
            {
                "id": d.id,
                "timestamp": data.get("timestamp", ""),
                "name": str(data.get("name", "")),
                "phone": "".join(ch for ch in str(data.get("phone", "")) if ch.isdigit()),
                "instagram": str(data.get("instagram", "")),
                "song": str(data.get("song", "")),
                "suggestion": str(data.get("suggestion", "")),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["id"] + HEADERS)

    df = pd.DataFrame(rows)

    for col in ["id"] + HEADERS:
        if col not in df.columns:
            df[col] = ""

    return df[["id"] + HEADERS]


@st.cache_data(ttl=10, show_spinner=False)
def fs_performed_df() -> pd.DataFrame:
    docs = list(db.collection(COL_PERFORMED).stream())
    rows = []

    for d in docs:
        data = d.to_dict() or {}
        rows.append(
            {
                "id": d.id,
                "timestamp": data.get("timestamp", ""),
                "name": str(data.get("name", "")),
                "name_lower": str(data.get("name_lower", "")),
                "phone": "".join(ch for ch in str(data.get("phone", "")) if ch.isdigit()),
                "instagram": str(data.get("instagram", "")),
                "song": str(data.get("song", "")),
                "suggestion": str(data.get("suggestion", "")),
                "status": "performed",
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "id",
                "timestamp",
                "name",
                "name_lower",
                "phone",
                "instagram",
                "song",
                "suggestion",
                "status",
            ]
        )

    return pd.DataFrame(rows)


@st.cache_data(ttl=2, show_spinner=False, max_entries=8)
def fs_claimed_songs() -> Set[str]:
    q = db.collection(COL_SONG_CLAIMS).select(["song"]).stream()
    out: Set[str] = set()

    for d in q:
        song = str((d.to_dict() or {}).get("song", "")).strip()
        if song:
            out.add(song)

    return out


def fs_find_signup_by_phone(phone_digits: str) -> Optional[Dict[str, str]]:
    if not phone_digits:
        return None

    snap = db.collection(COL_SIGNUPS).document(phone_digits).get()
    if snap.exists:
        rec = snap.to_dict() or {}
        rec["id"] = snap.id
        return rec

    q = db.collection(COL_SIGNUPS).where("phone", "==", phone_digits).limit(1).stream()
    for d in q:
        rec = d.to_dict() or {}
        rec["id"] = d.id
        return rec

    return None


def fs_is_song_claimed(song_title: str) -> bool:
    if not song_title:
        return False
    return db.collection(COL_SONG_CLAIMS).document(song_doc_id(song_title)).get().exists


@firestore.transactional
def add_signup_txn(transaction, name: str, phone_digits: str, instagram: str, song: str, suggestion: str) -> bool:
    signup_ref = db.collection(COL_SIGNUPS).document(phone_digits)
    claim_ref = db.collection(COL_SONG_CLAIMS).document(song_doc_id(song))

    transaction.create(
        signup_ref,
        {
            "timestamp": datetime.utcnow().isoformat(),
            "name": name,
            "phone": phone_digits,
            "instagram": instagram,
            "song": song,
            "suggestion": suggestion,
        },
    )

    transaction.create(
        claim_ref,
        {
            "song": song,
            "phone": phone_digits,
            "created_at": datetime.utcnow().isoformat(),
        },
    )

    return True


def fs_add_signup(name: str, phone_digits: str, instagram: str, song: str, suggestion: str) -> bool:
    try:
        if not phone_digits or not song:
            return False
        transaction = db.transaction()
        add_signup_txn(transaction, name, phone_digits, instagram, song, suggestion)
        return True
    except Exception:
        return False


def fs_delete_signup_by_id(doc_id: str, release_song_claim: bool = True) -> bool:
    """
    Deletes an active signup.

    release_song_claim=True:
      Used for Undo / host release before performance. Song becomes available again.

    release_song_claim=False:
      Used only after a singer has performed. Phone is freed, but song stays claimed.
    """
    try:
        ref = db.collection(COL_SIGNUPS).document(doc_id)
        snap = ref.get()

        if not snap.exists:
            return False

        data = snap.to_dict() or {}
        song = str(data.get("song", "")).strip()

        batch = db.batch()
        batch.delete(ref)

        if release_song_claim and song:
            batch.delete(db.collection(COL_SONG_CLAIMS).document(song_doc_id(song)))

        batch.commit()
        return True
    except Exception:
        return False


def _invalidate_data_caches():
    for fn in [fs_signups_df, fs_claimed_songs, fs_performed_df]:
        try:
            fn.clear()
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
    "<p style='text-align:center;margin:0;'>One song at a time per person. Songs can only be chosen once per night.</p>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='text-align:center;margin:6px 0;'><a href='https://instagram.com/losemoskaraoke' target='_blank'>Follow us on Instagram</a></p>",
    unsafe_allow_html=True,
)
st.divider()

if st.session_state.get("signup_success"):
    msg = st.session_state["signup_success"]
    if isinstance(msg, dict) and msg.get("song"):
        who = f" {msg.get('name', '')}" if msg.get("name") else ""
        st.success(f"You're in{who}! You've signed up to sing '{msg['song']}'.")
        if st.button("Dismiss", key="dismiss_success"):
            st.session_state["signup_success"] = None
            st.rerun()

if st.session_state.get("undo_success"):
    msg = st.session_state["undo_success"]
    if isinstance(msg, dict) and msg.get("song"):
        name_txt = f" for {msg.get('name', '')}" if msg.get("name") else ""
        st.success(f"Removed your signup{name_txt}: '{msg['song']}'. That song is available again.")
        if st.button("Dismiss", key="dismiss_undo_success"):
            st.session_state["undo_success"] = None
            st.rerun()

st.divider()

# ------------ Public Signup Form ------------
all_songs = fs_load_songs()
if not all_songs:
    st.warning("No songs found in the songs collection.")

claimed_songs = fs_claimed_songs()
available_songs = [s for s in all_songs if s and s not in claimed_songs]

with st.form("signup_form", clear_on_submit=False):
    name = st.text_input("Your Name", max_chars=60)

    phone_raw = st.text_input("Phone (US, 10 digits)")
    digits = normalize_us_phone(phone_raw)

    if phone_raw:
        if len(digits) >= 10:
            st.caption(f"Digits: {digits[0:3]}-{digits[3:6]}-{digits[6:10]}")
        else:
            st.caption(f"Digits so far: {digits}")

    instagram = st.text_input("Instagram (optional)", placeholder="@yourhandle")
    instagram = instagram.strip().lstrip("@").strip().lower() if instagram else ""

    # Safe widget clearing:
    # This modifies song_select only before the selectbox widget is instantiated.
    if st.session_state.pop("clear_song_select_next_run", False):
        st.session_state["song_select"] = None

    prev_choice = st.session_state.get("song_select", "")

    if available_songs:
        st.selectbox(
            "Pick your song",
            options=available_songs,
            index=None,
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

    suggestion = st.text_input(
        "Don't see your favorite song? Suggest it and we might add it in the future!",
        placeholder="Optional: suggest a song",
    )

    current_choice = st.session_state.get("song_select", "")
    attempted_song = current_choice or prev_choice
    vanished = bool(prev_choice and (prev_choice not in available_songs) and (current_choice in ("", None)))

    submit = st.form_submit_button("Submit Signup")

    errs = []

    if submit:
        if not name.strip():
            errs.append("Please enter your name.")
        if len(digits) != 10:
            errs.append("Please enter a valid US phone (10 digits; country code '1' is OK).")

        if vanished:
            errs.append(f"Sorry, '{prev_choice}' was just claimed. Pick another.")
        else:
            if not attempted_song:
                errs.append("Please select a song.")
            elif (attempted_song in claimed_songs) or fs_is_song_claimed(attempted_song):
                errs.append(f"Sorry, '{attempted_song}' was already claimed tonight. Pick another.")

            if not errs and fs_find_signup_by_phone(digits):
                errs.append("This phone number already has an active signup. Wait until you sing, then sign up again!")

        if errs:
            for e in errs:
                st.error(e)
        else:
            ok = fs_add_signup(name.strip(), digits, instagram.strip(), attempted_song, suggestion.strip())
            if ok:
                st.session_state["signup_success"] = {"song": attempted_song, "name": name.strip()}
                st.session_state["clear_song_select_next_run"] = True
                _invalidate_data_caches()
                st.rerun()
            else:
                st.error(
                    f"Could not save your signup — either your phone already has an active signup, or '{attempted_song}' was already claimed tonight."
                )

    if (not submit) and vanished and not st.session_state.get("signup_success"):
        st.warning(f"Looks like '{prev_choice}' was just claimed by another singer. Please pick another.")


# ------------ Undo Signup ------------
with st.expander("Undo My Signup"):
    undo_phone_raw = st.text_input("Enter the phone number you signed up with (10 digits)", key="undo_phone")
    u_digits = normalize_us_phone(undo_phone_raw)

    if st.button("Undo My Signup"):
        if len(u_digits) != 10:
            st.error("Please enter a valid US phone (10 digits).")
        else:
            rec = fs_find_signup_by_phone(u_digits)

            if rec and rec.get("id"):
                if fs_delete_signup_by_id(rec["id"], release_song_claim=True):
                    st.session_state["undo_success"] = {
                        "song": rec.get("song", ""),
                        "name": rec.get("name", ""),
                    }

                    state_cleanup = fs_read_state()
                    key_to_release = key_from_record(
                        {
                            "name": rec.get("name", ""),
                            "phone": rec.get("phone", ""),
                            "song": rec.get("song", ""),
                        }
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

                    _invalidate_data_caches()
                    st.rerun()
                else:
                    st.error("Could not remove your signup. Please try again.")
            else:
                st.error("No active signup found for that phone number.")

st.divider()
st.info("We won't share your data. Phone numbers ensure fairness and prevent duplicate active signups.")

st.subheader("All Songs")
if all_songs:
    lines = []
    for s in all_songs:
        lines.append(f"- ~~{s}~~" if s in claimed_songs else f"- {s}")
    st.markdown("\n".join(lines))
else:
    st.caption("No songs found yet.")


# ------------ Host Helpers ------------
def _row_key(rec: Dict[str, str]) -> tuple:
    return key_from_record(rec)


def _df_with_keys(dfin: pd.DataFrame) -> pd.DataFrame:
    df2 = dfin.copy()
    df2["__key__"] = df2.apply(lambda r: _row_key(r), axis=1)
    return df2


def _keys_from_df(df_keys: pd.DataFrame, keys: List[tuple]) -> List[Dict[str, str]]:
    pool = {k: rec for k, rec in zip(df_keys["__key__"], df_keys.to_dict("records"))}
    return [pool[k] for k in keys if k in pool]


@firestore.transactional
def normalize_queue_txn(transaction, all_keys_set: Set[tuple]):
    state = fs_read_state(transaction=transaction)
    used_set = set(state.get("used_keys", []))
    now_key = state.get("now_key")
    order_keys = list(state.get("order_keys", []))

    order_keys_normalized = [
        k for k in order_keys if (k in all_keys_set and k not in used_set and k != now_key)
    ]

    new_candidates = list(
        all_keys_set
        - used_set
        - ({now_key} if now_key else set())
        - set(order_keys_normalized)
    )

    changed = bool(new_candidates) or (len(order_keys_normalized) != len(order_keys))

    if changed:
        rng = random.Random(int(state.get("version", 0)))
        rng.shuffle(new_candidates)
        order_keys_normalized.extend(new_candidates)

        state["order_keys"] = order_keys_normalized
        bump_version(state)
        fs_write_state(state, transaction=transaction)

    return state


@firestore.transactional
def call_next_singer_txn(transaction, all_keys_set: Set[tuple]):
    state = fs_read_state(transaction=transaction)

    now_key = state.get("now_key")
    used_keys = list(state.get("used_keys", []))
    order_keys = list(state.get("order_keys", []))
    used_set = set(used_keys)

    order_keys = [
        k for k in order_keys if (k in all_keys_set and k not in used_set and k != now_key)
    ]

    if now_key and now_key not in used_set:
        used_keys.append(now_key)

        name_lower, phone_digits, song = now_key

        signup_ref = db.collection(COL_SIGNUPS).document(phone_digits)
        signup_snap = signup_ref.get(transaction=transaction)
        signup_data = signup_snap.to_dict() if signup_snap.exists else {}

        # Delete active signup so the singer can sign up again.
        transaction.delete(signup_ref)

        # Do NOT delete song claim here. Completed songs stay blocked for the night.
        perf_ref = db.collection(COL_PERFORMED).document()
        transaction.set(
            perf_ref,
            {
                "timestamp": datetime.utcnow().isoformat(),
                "name": str(signup_data.get("name", "")),
                "name_lower": name_lower,
                "phone": phone_digits,
                "instagram": str(signup_data.get("instagram", "")),
                "song": song,
                "suggestion": str(signup_data.get("suggestion", "")),
                "status": "performed",
            },
        )

    new_now_key = order_keys.pop(0) if order_keys else None

    state["now_key"] = new_now_key
    state["used_keys"] = used_keys
    state["order_keys"] = order_keys

    bump_version(state)
    fs_write_state(state, transaction=transaction)

    return new_now_key


@firestore.transactional
def skip_singer_txn(transaction, choice_type, choice_key):
    state = fs_read_state(transaction=transaction)
    order_keys = list(state.get("order_keys", []))
    now_key = state.get("now_key")

    if choice_type == "current":
        if now_key != choice_key:
            raise ValueError("Current key mismatch during skip transaction.")

        order_keys = [k for k in order_keys if k != choice_key]
        order_keys.insert(min(2, len(order_keys)), choice_key)

        state["now_key"] = None
        state["order_keys"] = order_keys
        bump_version(state)
        fs_write_state(state, transaction=transaction)
        return "current"

    if choice_key in order_keys:
        old_pos = order_keys.index(choice_key)
        new_pos = min(old_pos + 2, len(order_keys))
        order_keys.pop(old_pos)
        order_keys.insert(new_pos, choice_key)

        state["order_keys"] = order_keys
        bump_version(state)
        fs_write_state(state, transaction=transaction)
        return "next"

    return None


@firestore.transactional
def promote_to_now_txn(transaction, choice_key: tuple):
    state = fs_read_state(transaction=transaction)
    now_key = state.get("now_key")
    order_keys = list(state.get("order_keys", []))

    if choice_key == now_key:
        return "already_now"

    order_keys = [k for k in order_keys if k != choice_key]

    if now_key:
        order_keys = [k for k in order_keys if k != now_key]
        order_keys.insert(0, now_key)

    state["now_key"] = choice_key
    state["order_keys"] = order_keys

    bump_version(state)
    fs_write_state(state, transaction=transaction)

    return "ok"


@firestore.transactional
def shuffle_remaining_txn(transaction):
    state = fs_read_state(transaction=transaction)
    order_keys = list(state.get("order_keys", []))

    random.shuffle(order_keys)

    state["order_keys"] = order_keys
    bump_version(state)
    fs_write_state(state, transaction=transaction)

    return len(order_keys)


# ------------ Host Controls ------------
with st.expander("Host Controls"):
    if not HOST_PIN or not HOST_PIN.strip() or HOST_PIN.strip().lower() == "changeme":
        st.error("Host PIN is not configured. Set HOST_PIN in the environment to unlock host controls.")
    else:
        pin = st.text_input("Enter host PIN", type="password")
        if st.button("Unlock Host Panel"):
            st.session_state["host_unlocked"] = pin == HOST_PIN
            if not st.session_state["host_unlocked"]:
                st.error("Incorrect PIN.")

    if st.session_state.get("host_unlocked"):
        if st.button("Refresh host view"):
            _invalidate_data_caches()
            st.rerun()

        df_all = fs_signups_df()
        queue_df = df_all[df_all["song"].astype(str).str.len() > 0].fillna("")
        queue_df_k = _df_with_keys(queue_df)
        all_keys_set = set(queue_df_k["__key__"])

        state = fs_read_state()
        used_keys = list(state["used_keys"]) if state else []
        used_set = set(used_keys)
        now_key = state.get("now_key") if state else None
        order_keys = list(state["order_keys"]) if state else []

        order_keys_normalized = [
            k for k in order_keys if (k in all_keys_set and k not in used_set and k != now_key)
        ]

        new_candidates = list(
            all_keys_set
            - used_set
            - ({now_key} if now_key else set())
            - set(order_keys_normalized)
        )

        if new_candidates or len(order_keys_normalized) != len(order_keys):
            try:
                transaction = db.transaction()
                state = normalize_queue_txn(transaction, all_keys_set)
                used_keys = list(state.get("used_keys", []))
                used_set = set(used_keys)
                now_key = state.get("now_key")
                order_keys = list(state.get("order_keys", []))
            except Exception:
                order_keys = order_keys_normalized + new_candidates

        order_records = _keys_from_df(queue_df_k, order_keys)
        record_pool = {k: rec for k, rec in zip(queue_df_k["__key__"], queue_df_k.to_dict("records"))}
        now_record = record_pool.get(now_key) if now_key else None

        st.subheader("Now Singing")
        if now_record:
            st.markdown(f"**{now_record.get('name', '')}** — *{now_record.get('song', '')}*")
        else:
            st.caption("No one is currently singing.")

        next_slice = order_records[:3]

        if next_slice:
            st.subheader("Up Next (Next 3)")
            st.markdown(
                "\n".join(
                    [f"- {i + 1}. {r.get('name', '')} — {r.get('song', '')}" for i, r in enumerate(next_slice)]
                )
            )
        else:
            st.caption("No upcoming singers.")

        if st.button("Call Next Singer"):
            try:
                transaction = db.transaction()
                new_now_key = call_next_singer_txn(transaction, all_keys_set)
                _invalidate_data_caches()

                if new_now_key:
                    rec = record_pool.get(new_now_key)
                    if rec:
                        st.success(f"Now calling {rec.get('name', '')} — {rec.get('song', '')}")
                    else:
                        st.success("Now calling the next singer.")
                else:
                    st.success("Queue is empty. Cleared 'Now Singing' slot.")

                st.rerun()
            except Exception as e:
                st.error(f"Error calling next singer (transaction failed): {e}")

        st.subheader("Skip")
        skip_options = []
        skip_keys = []

        if now_record and now_key:
            skip_options.append(f"Current: {now_record.get('name', '')} — {now_record.get('song', '')}")
            skip_keys.append(("current", now_key))

        for i, r in enumerate(next_slice):
            skip_options.append(f"Next {i + 1}: {r.get('name', '')} — {r.get('song', '')}")
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

                    st.rerun()
                except Exception as e:
                    st.error(f"Error skipping singer (transaction failed): {e}")
        else:
            st.caption("No one available to skip.")

        st.subheader("Call Someone Now (Manual)")
        manual_options = []
        manual_keys = []

        for r in order_records:
            ph = str(r.get("phone", ""))
            last4 = f" (…{ph[-4:]})" if ph else ""
            manual_options.append(f"{r.get('name', '')} — {r.get('song', '')}{last4}")
            manual_keys.append(key_from_record(r))

        if manual_options:
            sel_manual = st.selectbox(
                "Choose a singer to call now",
                options=["— select —"] + manual_options,
                index=0,
                key="manual_call_choice",
            )

            if sel_manual != "— select —" and st.button("Call Selected Now"):
                try:
                    choice_key = manual_keys[manual_options.index(sel_manual)]
                    transaction = db.transaction()
                    result = promote_to_now_txn(transaction, choice_key)

                    if result == "already_now":
                        st.info("That singer is already marked as Now Singing.")
                    else:
                        st.success("Moved selected singer to Now Singing and kept the rest of the order intact.")

                    st.rerun()
                except Exception as e:
                    st.error(f"Error calling selected singer (transaction failed): {e}")
        else:
            st.caption("No remaining singers to call manually.")

        st.subheader("Shuffle Remaining")
        st.caption("Randomize the order of everyone who hasn’t sung yet. Current singer and already-performed are unchanged.")

        if st.button("Shuffle Remaining Singers"):
            try:
                transaction = db.transaction()
                n = shuffle_remaining_txn(transaction)
                st.success(f"Shuffled {n} remaining singers.")
                st.rerun()
            except Exception as e:
                st.error(f"Error shuffling remaining singers (transaction failed): {e}")

        showing = st.session_state.get("show_full_list", False)
        label = "Hide Remaining Signup List" if showing else "Show Remaining Signup List"

        if st.button(label, key="toggle_full_list"):
            st.session_state["show_full_list"] = not showing
            showing = st.session_state["show_full_list"]

        if showing:
            remaining = _keys_from_df(queue_df_k, order_keys)
            if remaining:
                st.subheader("Remaining (in order)")
                st.markdown(
                    "\n".join(
                        [f"- {i + 1}. {r.get('name', '')} — {r.get('song', '')}" for i, r in enumerate(remaining)]
                    )
                )
            else:
                st.caption("No remaining signups.")

        st.subheader("Release a Signup")
        st.caption("Use this for mistakes/no-shows before someone performs. This releases the song back into the available list.")

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

            confirm_release = st.checkbox("Yes, remove this signup and release the song", key="confirm_release_signup")

            if release_choice and confirm_release and st.button("Remove Selected Signup"):
                key_to_release = id_to_data[release_choice]["key"]
                ok = fs_delete_signup_by_id(release_choice, release_song_claim=True)

                if ok:
                    state_cleanup = fs_read_state()
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

                    st.success("Signup removed and song released.")
                    _invalidate_data_caches()
                    st.rerun()
                else:
                    st.error("Could not delete the signup. Try again.")
        else:
            st.caption("No signups yet.")

        st.subheader("Download CSV")

        performed_df = fs_performed_df()

        active_df = queue_df[["timestamp", "name", "phone", "instagram", "song", "suggestion"]].copy()
        active_df["status"] = "active"

        if not performed_df.empty:
            performed_export = performed_df[
                ["timestamp", "name", "phone", "instagram", "song", "suggestion", "status"]
            ].copy()
        else:
            performed_export = pd.DataFrame(
                columns=["timestamp", "name", "phone", "instagram", "song", "suggestion", "status"]
            )

        full_night_df = pd.concat([performed_export, active_df], ignore_index=True)
        full_night_df = full_night_df.sort_values("timestamp", na_position="last")

        st.download_button(
            "Download Full Night CSV",
            data=full_night_df.to_csv(index=False),
            file_name="karaoke_full_night.csv",
            mime="text/csv",
        )

        st.subheader("Reset for Next Event")
        st.warning("This will permanently delete all active signups, song claims, performed history, and host state!")

        if st.checkbox("Yes, clear everything for a new event", key="confirm_reset_checkbox"):
            if st.button("Reset Now", key="final_reset_button"):
                for collection_name in [COL_SIGNUPS, COL_SONG_CLAIMS, COL_PERFORMED]:
                    batch = db.batch()
                    for d in db.collection(collection_name).stream():
                        batch.delete(d.reference)
                    batch.commit()

                fs_write_state(
                    {
                        "version": 0,
                        "now_key": None,
                        "used_keys": [],
                        "order_keys": [],
                    }
                )

                _invalidate_data_caches()

                st.success("Cleared. Ready for the next event.")
                st.rerun()

st.caption("Los Emos Karaoke — built with Streamlit.")
st.caption(f"Build revision: {os.getenv('K_REVISION', 'unknown')}")
