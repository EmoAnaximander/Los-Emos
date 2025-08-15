import streamlit as st
from datetime import datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import io

# --- Google Sheets setup ---
SHEET_KEY = "1JGAubxB_3rUvTdi7XlhHOguWyvuw_37igxRNBz_KDm8"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

if "GOOGLE_CREDENTIALS" in st.secrets:
    CREDS = Credentials.from_service_account_info(
        json.loads(st.secrets["GOOGLE_CREDENTIALS"]),
        scopes=SCOPES
    )
else:
    CREDS = Credentials.from_service_account_file(
        "service_account.json",
        scopes=SCOPES
    )

client = gspread.authorize(CREDS)
sheet = client.open_by_key(SHEET_KEY)
worksheet = sheet.worksheet("Signups")

# --- Load data safely ---
data = worksheet.get_all_records()
if data:
    df = pd.DataFrame(data)
else:
    header = worksheet.row_values(1)
    df = pd.DataFrame(columns=[col.strip().lower() for col in header])
df.columns = [col.strip().lower() for col in df.columns]

if "host_verified" not in st.session_state:
    st.session_state.host_verified = False
if "called" not in st.session_state:
    st.session_state.called = []

# --- Styling (Dark mode) ---
st.markdown("""
    <style>
    body, .main, .block-container { background-color: #1e1e1e; color: white; }
    .stTextInput > div > input, .stSelectbox > div > div, .stButton > button {
        background-color: #333;
        color: white;
    }
    </style>
""", unsafe_allow_html=True)

# --- Title ---
from PIL import Image
from pathlib import Path

logo_path = Path(__file__).parent / "logo.png"
logo = Image.open(logo_path)

col1, col2, col3 = st.columns([3, 4, 3])
with col2:
    st.image(logo, width=300)
st.markdown("""
<h1 style='text-align: center;'>Singer Signup</h1>
<p style='text-align: center; font-size: 16px;'>One song per person. Once it's claimed, it disappears. We'll call your name when it's your turn to scream.</p>
""", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-size: 16px;'><a href='https://instagram.com/losemoskaraoke' target='_blank' style='color: white; text-decoration: underline;'>Follow us on Instagram</a></p>", unsafe_allow_html=True)

# --- Signup Form ---
with st.form("signup_form"):
    name = st.text_input("Your name")
    phone_raw = st.text_input("Your phone number (10 digits)*")
    phone = ''.join(filter(str.isdigit, phone_raw))
    if len(phone) == 10:
        phone = f"{phone[:3]}-{phone[3:6]}-{phone[6:]}"
    elif phone:
        st.warning("Please enter a valid 10-digit phone number.")

    instagram = st.text_input("Your Instagram (optional, no @ needed)")
    suggestion = st.text_input("Suggest a song for next time (optional)")
    taken_songs = df["song"].tolist() if "song" in df.columns else []
    song_list_sheet = sheet.worksheet("Songs")
    song_list_data = song_list_sheet.col_values(1)
    SONG_LIST = [s for s in song_list_data if s.strip()]
    available_songs = [s for s in SONG_LIST if s not in taken_songs]
    selected_song = st.selectbox("Pick your song", available_songs)

    submit = st.form_submit_button("Sign me up!")

    if submit:
        if not name.strip() or not phone or len(phone) != 12:
            st.warning("Please fill in both your name and a valid phone number.")
        elif phone in df["phone"].tolist():
            st.error("You've already signed up for a song.")
        elif selected_song in taken_songs:
            st.error("That song is already taken.")
        else:
            now = datetime.now().isoformat()
            worksheet.append_row([
                now, name.strip(), phone, instagram.strip(),
                selected_song, suggestion.strip() if suggestion else ""
            ])
            st.success(f"🎉 {name}, you're locked in for '{selected_song}'!")
            st.rerun()

# --- Helper to delete signup by name ---
def delete_signup_by_name(name):
    records = worksheet.get_all_values()
    for i, row in enumerate(records):
        if len(row) >= 2 and row[1].strip().lower() == name.strip().lower():
            worksheet.delete_rows(i + 1)
            return True
    return False

# --- Undo Signup Button ---
if 'phone' in locals() and phone and "phone" in df.columns and phone in df["phone"].tolist():
    with st.expander("⚠️ Undo My Signup"):
        confirm_undo = st.checkbox("Yes, I want to remove my signup")
        if confirm_undo:
            if st.button("Undo My Signup"):
                match = df[df["phone"] == phone]
                if not match.empty:
                    song_to_delete = match.iloc[0]["song"]
                    name_to_delete = match.iloc[0]["name"]
                match_row = df[(df["name"] == name_to_delete) & (df["song"] == song_to_delete)]
                if not match_row.empty:
                    row_index = int(match_row.index[0])
                    records = worksheet.get_all_values()
                    worksheet.delete_rows(row_index + 2)
                    st.success("✅ Your signup has been removed.")
                    st.rerun()
                else:
                    st.error("⚠️ Could not find your signup to remove.")
                

# --- Song List ---
song_list_sheet = sheet.worksheet("Songs")
song_list_data = song_list_sheet.col_values(1)
SONG_LIST = [s for s in song_list_data if s.strip()]

st.subheader("🎶 Song List")
for song in SONG_LIST:
    if "song" in df.columns and song in df["song"].tolist():
        if st.session_state.host_verified:
            person = df[df["song"] == song]["name"].values[0]
            safe_song = song.replace('*', '\*').replace('_', '\_').replace('`', '\`')
            st.markdown(f"- ~~{safe_song}~~ (🎤 {person})")
        else:
            st.markdown(f"- ~~{song}~~")
    else:
        st.markdown(f"- {song}")

# --- Host Controls ---
st.subheader("🔐 Host Controls")
with st.expander("Enter Host PIN to unlock controls"):
    pin = st.text_input("Enter host PIN", type="password")
    if st.button("Unlock"):
        if pin == "gibsons2025":
            st.session_state.host_verified = True
            st.success("✅ Host access granted.")
        else:
            st.error("❌ Incorrect PIN.")

# --- Release Song for Host ---
if st.session_state.host_verified and "song" in df.columns:
    st.subheader("🎭 Release a Song")
    taken = df["song"].tolist()
    release_options = [f"{row['name']} – {row['song']}" for _, row in df.iterrows() if row["song"] in taken]
    selected_release = st.selectbox("Select a signup to remove", release_options, key="free_song")

    if " – " in selected_release:
        name_to_release, song_to_release = selected_release.split(" – ")
        with st.expander("⚠️ Confirm Song Removal"):
            confirm_release = st.checkbox("Yes, remove this signup from the sheet")

        if confirm_release and st.button("Remove Selected Signup"):
            match_row = df[(df["name"] == name_to_release) & (df["song"] == song_to_release)]
            if not match_row.empty:
                row_index = int(match_row.index[0])
                records = worksheet.get_all_values()
                worksheet.delete_rows(row_index + 2)
                st.success(f"✅ Removed '{song_to_release}' by {name_to_release}.")
                st.rerun()

    # --- Call Next Singer ---
    st.subheader("🎤 Call Next Singer")
    remaining = df[~df["song"].isin(st.session_state.called)].sort_values("timestamp")
    if st.button("Call Next Song"):
        if not remaining.empty:
            next_row = remaining.iloc[0]
            st.session_state.called.append(next_row["song"])
            name = next_row["name"]
            song = next_row["song"].replace("*", "\*").replace("_", "\_").replace("`", "\`")
            st.success(f"🎤 {name} — time to sing **{song}**!")
        else:
            st.info("✅ No more singers in the queue.")

    # --- Now Singing ---
    st.subheader("📢 Now Singing")
    if st.session_state.called:
        now_song = st.session_state.called[-1]
        now_row = df[df["song"] == now_song].iloc[0]
        st.write(f"🎶 {now_row['name']} is singing: {now_row['song']}")
    else:
        st.write("No one is singing yet.")

    # --- Next 3 in Queue ---
    st.subheader("⏭️ Next 3 in Queue")
    queued = df[~df["song"].isin(st.session_state.called)].sort_values("timestamp")
    for i, (_, row) in enumerate(queued.head(3).iterrows(), 1):
        safe_song = row['song'].replace("*", "\*").replace("_", "\_").replace("`", "\`")
        st.markdown(f"{i}. {row['name']} — {safe_song}")

    # --- Skip a Singer ---
    st.subheader("⏭️ Skip a Singer")
    skip_options = [f"{row['name']} – {row['song']}" for _, row in queued.iterrows()]
    if skip_options:
        to_skip_display = st.selectbox("Select a singer to skip", skip_options, key="skip_singer")
        if " – " in to_skip_display:
            name_part, song_part = to_skip_display.split(" – ")
            match_row = queued[(queued["name"] == name_part) & (queued["song"] == song_part)]
            if st.button("Skip Selected Singer"):
                if not match_row.empty:
                    idx = match_row.index[0]
                    reordered = list(queued.index)
                    if len(queued) > reordered.index(idx) + 3:
                        reordered.insert(reordered.index(idx) + 4, reordered.pop(reordered.index(idx)))
                        st.success(f"✅ {name_part} moved down 3 spots in the queue.")
                    else:
                        reordered.append(reordered.pop(reordered.index(idx)))
                        st.success(f"✅ {name_part} moved to the end of the queue.")
                    df = queued.loc[reordered].reset_index(drop=True)

    # --- View Full Signup List ---
    with st.expander("📋 View Full Signup List"):
        for _, row in df.iterrows():
            safe_song = row['song'].replace("*", "\*").replace("_", "\_").replace("`", "\`")
            st.markdown(f"- **{row['name']}** — {safe_song}")

    # --- Export to CSV ---
    st.subheader("⬇️ Export Signups to CSV")
    if st.button("Download CSV"):
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Click to download", csv, "karaoke_signups.csv", "text/csv")
      
    st.markdown("<p style='text-align: center; font-size: 12px;'>*We won't share your data or contact you outside this event. Phone numbers ensure everyone only signs up for one song.</p>", unsafe_allow_html=True)

    # --- Reset for Next Event ---
    st.subheader("♻️ Reset for Next Event")
    with st.expander("⚠️ Danger Zone: Clear All Signups"):
        confirm_clear = st.checkbox("Yes, clear the entire signup sheet")
        if confirm_clear and st.button("Clear All Signups"):
            worksheet.clear()
            worksheet.append_row(["timestamp", "name", "phone", "instagram", "song", "suggestion"])
            st.success("✅ All signups have been cleared.")
            st.rerun()
