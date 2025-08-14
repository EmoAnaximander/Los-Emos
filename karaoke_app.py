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
st.markdown("<h1 style='text-align: center;'>Singer Signup</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-size: 16px;'>Follow us on Instagram</p>", unsafe_allow_html=True)

# --- Helper to delete signup by name ---
def delete_signup_by_name(name):
    records = worksheet.get_all_values()
    for i, row in enumerate(records):
        if len(row) >= 2 and row[1].strip().lower() == name.strip().lower():
            worksheet.delete_rows(i + 1)
            return True
    return False

# --- Song List ---
SONG_LIST = [
    "Alkaline Trio - Stupid Kid", "All Time Low - Dear Maria, Count Me In", "Avril Lavigne - Sk8er Boi",
    "Blink-182 - All the Small Things", "Blink-182 - What's My Age Again?", "Bowling for Soup - 1985",
    "Brand New - Mix Tape", "Brand New - The Quiet Things That No One Ever Knows",
    "Dashboard Confessional - Vindicated", "Fall Out Boy - Dance Dance", "Fall Out Boy - Sugar, We're Goin Down",
    "Good Charlotte - Girls & Boys", "Good Charlotte - The Anthem", "Hawthorne Heights - Ohio Is for Lovers",
    "Jimmy Eat World - The Middle", "Mayday Parade - Jamie All Over", "My Chemical Romance - Helena",
    "My Chemical Romance - I'm Not Okay (I Promise)", "New Found Glory - My Friends Over You",
    "New Found Glory - Understatement", "Panic! At The Disco - Lying Is the Most Fun a Girl Can Have Without Taking Her Clothes Off",
    "Papa Roach - Last Resort", "Paramore - Misery Business", "Paramore - Still Into You",
    "Paramore - That's What You Get", "Saves The Day - My Sweet Fracture", "Say Anything - Wow, I Can Get Sexual Too",
    "Simple Plan - I'd Do Anything", "Something Corporate - Punk Rock Princess",
    "Story of the Year - Until the Day I Die", "Sugarcult - Memory",
    "Taking Back Sunday - Cute Without the 'E' (Cut From the Team)", "Taking Back Sunday - MakeDamnSure",
    "The All-American Rejects - Dirty Little Secret", "The Starting Line - The Best of Me",
    "The Story So Far - Empty Space", "The Story So Far - Roam", "The Used - Buried Myself Alive",
    "The Used - The Taste of Ink", "Wheatus - Teenage Dirtbag", "Yellowcard - Ocean Avenue",
    "Yellowcard - Only One"
]

# --- Signup Form ---
with st.form("signup_form"):
    name = st.text_input("Your name")
    phone = st.text_input("Your phone number")
    instagram = st.text_input("Your Instagram (optional, no @ needed)")
    suggestion = st.text_input("Suggest a song for next time (optional)")
    taken_songs = df["song"].tolist() if "song" in df.columns else []
    available_songs = [s for s in SONG_LIST if s not in taken_songs]
    selected_song = st.selectbox("Pick your song", available_songs)
    submit = st.form_submit_button("Sign me up!")

    if submit:
        if not name.strip():
            st.warning("Please enter your name.")
        elif selected_song in taken_songs:
            st.error("That song is already taken.")
        elif "phone" in df.columns and phone in df["phone"].tolist():
            st.error("You've already signed up for a song.")
        else:
            now = datetime.now().isoformat()
            worksheet.append_row([now, name, phone.strip(), instagram.strip(), selected_song, suggestion.strip() if suggestion else ""])
            st.success(f"🎉 {name}, you're locked in for '{selected_song}'!")

# --- Undo Signup Button ---
if name and "name" in df.columns and name in df["name"].tolist():
    with st.expander("⚠️ Undo My Signup"):
        confirm_undo = st.checkbox("Yes, I want to remove my signup")
        if st.button("Undo My Signup") and confirm_undo:
            if delete_signup_by_name(name):
                st.success("✅ Your signup has been removed.")
                st.rerun()
            else:
                st.error("⚠️ Could not find your signup to remove.")

# --- Now Singing Display ---
if st.session_state.called:
    current_song = st.session_state.called[-1]
    row = df[df["song"] == current_song].iloc[0]
safe_song = current_song.replace('*', '\*').replace('_', '\_').replace('`', '\`')
st.markdown(f"## 🎤 NOW SINGING: **{row['name']}** – _{safe_song}_")

# --- Song List ---
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
    song_to_free = st.selectbox("Select a song to free up", taken, key="free_song")
    with st.expander("⚠️ Confirm Song Removal"):
        confirm_release = st.checkbox("Yes, remove this signup from the sheet")
        if st.button("Remove Selected Signup") and confirm_release:
            match_row = df[df["song"] == song_to_free]
            if not match_row.empty:
                name_to_delete = match_row.iloc[0]["name"]
                if delete_signup_by_name(name_to_delete):
                    st.success(f"✅ Removed '{song_to_free}' from the queue.")
                    st.rerun()
                else:
                    st.error("⚠️ Could not remove signup.")

# --- Skip Button (Move down 3 spots) ---
if st.session_state.host_verified and "song" in df.columns:
    st.subheader("⏭️ Skip a Singer")
    all_called = st.session_state.called
    queued = df[~df["song"].isin(all_called)].sort_values("timestamp")
    skip_options = queued["name"].tolist()
    if skip_options:
        to_skip = st.selectbox("Select a singer to skip", skip_options, key="skip_singer")
        if st.button("Skip Selected Singer"):
            idx = queued["name"].tolist().index(to_skip)
            if len(queued) > idx + 3:
                reordered = list(queued.index)
                reordered.insert(idx + 4, reordered.pop(idx))
                df = queued.loc[reordered].reset_index(drop=True)
                st.success(f"✅ {to_skip} moved down 3 spots in the queue.")
            else:
                st.warning("⚠️ Not enough people left in the queue to skip that far.")

# --- Queue Viewer ---
if st.session_state.host_verified and "song" in df.columns:
    st.subheader("🧾 Next 3 In Queue")
    queue = df.sort_values("timestamp")
    remaining = queue[~queue["song"].isin(st.session_state.called)]
    for _, row in remaining.head(3).iterrows():
        safe_song = row['song'].replace('*', '\*').replace('_', '\_').replace('`', '\`')
        st.markdown(f"- **{row['name']}** → _{safe_song}_")

    if st.button("Call Next Song"):
        if not remaining.empty:
            next_row = remaining.iloc[0]
            st.session_state.called.append(next_row["song"])
            name = next_row["name"]
            song = next_row["song"].replace('*', '\*').replace('_', '\_').replace('`', '\`')
            st.success(f"🎤 {name} — time to sing **{song}**!")
        else:
            st.info("✅ No more singers in the queue.")

    if st.button("View Full Signup List"):
        st.subheader("📋 Full Signup List")
        for _, row in queue.iterrows():
            tag = f" (@{row['instagram']})" if row['instagram'] else ""
            safe_song = row['song'].replace('*', '\*').replace('_', '\_').replace('`', '\`')
            st.markdown(f"- **{row['name']}**{tag} – _{safe_song}_")

# --- Export to CSV ---
if st.session_state.host_verified and not df.empty:
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Download Signups as CSV", csv, "signups.csv", "text/csv")

# --- Reset for Next Event ---
if st.session_state.host_verified:
    st.subheader("🧹 Reset for Next Event")
    with st.expander("⚠️ Confirm Reset"):
        confirm_clear = st.checkbox("Yes, clear the entire signup sheet")
    if st.button("Clear All Signups") and confirm_clear:
        worksheet.clear()
        worksheet.append_row(["timestamp", "name", "phone", "instagram", "song", "suggestion"])
        st.session_state.called = []
        st.success("✅ All signups and queue cleared.")
