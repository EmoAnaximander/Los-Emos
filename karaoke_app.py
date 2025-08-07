import streamlit as st
from datetime import datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

# --- Google Sheets setup ---
SHEET_KEY = "1JGAubxB_3rUvTdi7XlhHOguWyvuw_37igxRNBz_KDm8"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Load credentials from secrets (Streamlit Cloud) or local file
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

# Connect to Google Sheet
client = gspread.authorize(CREDS)

try:
    sheet = client.open_by_key(SHEET_KEY)
    worksheet = sheet.worksheet("Signups")
except Exception as e:
    st.error(f"❌ Could not open Google Sheet: {e}")
    st.stop()

try:
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
except Exception as e:
    st.error(f"❌ Could not read from worksheet: {e}")
    st.stop()

# --- Streamlit session state ---
if "host_verified" not in st.session_state:
    st.session_state.host_verified = False
if "called" not in st.session_state:
    st.session_state.called = []

# --- App Title ---
st.title("🎤 Gibsons Karaoke Night")
st.markdown("One song per person. Signed-up songs are hidden once taken. Let's rock Ventura!")

# --- Song List ---
SONG_LIST = [
    "Alkaline Trio - Stupid Kid",
    "All Time Low - Dear Maria, Count Me In",
    "Avril Lavigne - Sk8er Boi",
    "Blink-182 - All the Small Things",
    "Blink-182 - What's My Age Again?",
    "Bowling for Soup - 1985",
    "Brand New - Mix Tape",
    "Brand New - The Quiet Things That No One Ever Knows",
    "Dashboard Confessional - Vindicated",
    "Fall Out Boy - Dance Dance",
    "Fall Out Boy - Sugar, We're Goin Down",
    "Good Charlotte - Girls & Boys",
    "Good Charlotte - The Anthem",
    "Hawthorne Heights - Ohio Is for Lovers",
    "Jimmy Eat World - The Middle",
    "Mayday Parade - Jamie All Over",
    "My Chemical Romance - Helena",
    "My Chemical Romance - I'm Not Okay (I Promise)",
    "New Found Glory - My Friends Over You",
    "New Found Glory - Understatement",
    "Panic! At The Disco - Lying Is the Most Fun a Girl Can Have Without Taking Her Clothes Off",
    "Papa Roach - Last Resort",
    "Paramore - Misery Business",
    "Paramore - Still Into You",
    "Paramore - That's What You Get",
    "Saves The Day - My Sweet Fracture",
    "Say Anything - Wow, I Can Get Sexual Too",
    "Simple Plan - I'd Do Anything",
    "Something Corporate - Punk Rock Princess",
    "Story of the Year - Until the Day I Die",
    "Sugarcult - Memory",
    "Taking Back Sunday - Cute Without the 'E' (Cut From the Team)",
    "Taking Back Sunday - MakeDamnSure",
    "The All-American Rejects - Dirty Little Secret",
    "The Starting Line - The Best of Me",
    "The Story So Far - Empty Space",
    "The Story So Far - Roam",
    "The Used - Buried Myself Alive",
    "The Used - The Taste of Ink",
    "Wheatus - Teenage Dirtbag",
    "Yellowcard - Ocean Avenue",
    "Yellowcard - Only One"
]

# --- Signup Form ---
with st.form("signup_form"):
    name = st.text_input("Your name")
    instagram = st.text_input("Your Instagram (optional, no @ needed)")
    taken_songs = df["song"].tolist()
    available_songs = [s for s in SONG_LIST if s not in taken_songs]
    selected_song = st.selectbox("Pick your song", available_songs)
    submit = st.form_submit_button("Sign me up!")

    if submit:
        if not name.strip():
            st.warning("Please enter your name.")
        elif selected_song in taken_songs:
            st.error("That song is already taken.")
        elif name in df["name"].tolist():
            st.error("You've already signed up for a song.")
        else:
            now = datetime.now().isoformat()
            worksheet.append_row([now, name, instagram.strip(), selected_song])
            st.success(f"🎉 {name}, you're locked in for '{selected_song}'!")

# --- Display Song List ---
st.subheader("🎶 Song List")
for song in SONG_LIST:
    if song in df["song"].tolist():
        if st.session_state.host_verified:
            person = df[df["song"] == song]["name"].values[0]
            st.markdown(f"- ~~{song}~~ (🎤 {person})")
        else:
            st.markdown(f"- ~~{song}~~")
    else:
        st.markdown(f"- {song}")

# --- Host Login ---
st.subheader("🔐 Host Controls")
with st.expander("Enter Host PIN to unlock controls"):
    pin = st.text_input("Enter host PIN", type="password")
    if st.button("Unlock"):
        if pin == "gibsons2025":
            st.session_state.host_verified = True
            st.success("✅ Host access granted.")
        else:
            st.error("❌ Incorrect PIN.")

# --- Call Next Singer ---
if st.session_state.host_verified:
    st.subheader("📣 Call Next Singer")
    queue = df.sort_values("timestamp")
    remaining = queue[~queue["song"].isin(st.session_state.called)]

    if st.button("Call Next Song"):
        if not remaining.empty:
            next_row = remaining.iloc[0]
            st.session_state.called.append(next_row["song"])
            st.success(f"🎤 {next_row['name']} — time to sing **{next_row['song']}**!")
        else:
            st.info("✅ No more singers in the queue.")

# --- View All Signups ---
if st.session_state.host_verified:
    with st.expander("📋 View All Signups"):
        for _, row in df.iterrows():
            tag = f" (@{row['instagram']})" if row['instagram'] else ""
            st.markdown(f"- **{row['name']}**{tag} – _{row['song']}_")

# --- Reset for Next Event ---
if st.session_state.host_verified:
    st.subheader("🧹 Reset for Next Event")
    if st.button("Clear All Signups"):
        worksheet.clear()
        worksheet.append_row(["timestamp", "name", "instagram", "song"])
        st.session_state.called = []
        st.success("✅ All signups and queue cleared.")