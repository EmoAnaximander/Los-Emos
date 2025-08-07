import streamlit as st
from datetime import datetime
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import os
import json

# --- Google Sheets setup ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1JGAubxB_3rUvTdi7XlhHOguWyvuw_37igxRNBz_KDm8/edit"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

if "GOOGLE_CREDENTIALS" in st.secrets:
    # Running on Streamlit Cloud
    CREDS = Credentials.from_service_account_info(
        json.loads(st.secrets["GOOGLE_CREDENTIALS"]),
        scopes=SCOPES
    )
else:
    # Running locally
    CREDS = Credentials.from_service_account_file(
        "service_account.json",
        scopes=SCOPES
    )

client = gspread.authorize(CREDS)
sheet = client.open_by_url(SHEET_URL).worksheet("Signups")

# --- Load data ---
data = sheet.get_all_records()
df = pd.DataFrame(data)

if "host_verified" not in st.session_state:
    st.session_state.host_verified = False

if "called" not in st.session_state:
    st.session_state.called = []

st.title("🎤 Gibsons Karaoke Night")
st.markdown("One song per person. Signed-up songs are hidden once taken. Let's rock Ventura!")

# --- Song List ---
SONG_LIST = [
    "Alkaline Trio - Stupid Kid",
    "All Time Low - Dear Maria, Count Me In",
    "Avril Lavigne - Sk8er Boi",
    "Blink-182 - All the Small Th
