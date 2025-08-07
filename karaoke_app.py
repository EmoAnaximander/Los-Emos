import streamlit as st
from datetime import datetime

# --- SONG LIST from "Second Try Correct Songs.xlsx" (42 songs) ---
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

# --- SESSION STATE ---
if "signups" not in st.session_state:
    st.session_state.signups = {}
if "called_queue" not in st.session_state:
    st.session_state.called_queue = []
if "host_verified" not in st.session_state:
    st.session_state.host_verified = False

st.title("🎤 Los Emos Karaoke Sign-Up Sheet")
st.markdown("One song per person. Signed-up songs are grayed out. Let's rock Ventura!")

# --- SIGNUP FORM ---
with st.form("signup_form"):
    name = st.text_input("Your name")
    instagram = st.text_input("Your Instagram (optional, no @ needed)")
    available_songs = [s for s in SONG_LIST if s not in st.session_state.signups]
    selected_song = st.selectbox("Pick your song", available_songs)
    submit = st.form_submit_button("Sign me up!")

    if submit:
        if not name.strip():
            st.warning("Please enter your name.")
        elif selected_song in st.session_state.signups:
            st.error("That song is already taken.")
        elif any(name == info["name"] for info in st.session_state.signups.values()):
            st.error("You've already signed up for a song.")
        else:
            st.session_state.signups[selected_song] = {
                "name": name,
                "timestamp": datetime.now(),
                "instagram": instagram.strip() if instagram else ""
            }
            st.success(f"{name}, you're locked in for '{selected_song}'!")

# --- SONG LIST ---
st.subheader("🎶 Song List")
for song in SONG_LIST:
    if song in st.session_state.signups:
        signer = st.session_state.signups[song]["name"]
        st.markdown(f"- ~~{song}~~ (🎤 {signer})")
    else:
        st.markdown(f"- {song}")

# --- HOST PIN ENTRY ---
st.subheader("🔐 Host Controls")

with st.expander("Enter Host PIN to Access Singer Queue", expanded=False):
    pin_input = st.text_input("Enter host PIN", type="password")
    if st.button("Unlock Controls"):
        if pin_input == "gibsons2025":  # Change PIN if needed
            st.session_state.host_verified = True
            st.success("Host controls unlocked!")
        else:
            st.error("Incorrect PIN.")

# --- CALL NEXT SINGER ---
if st.session_state.host_verified:
    st.subheader("📣 Call the Next Singer")
    if st.button("Call Next Song"):
        remaining = {
            song: info
            for song, info in st.session_state.signups.items()
            if (song, info["name"]) not in st.session_state.called_queue
        }
        if not remaining:
            st.info("No more singers in the queue.")
        else:
            next_song, info = sorted(remaining.items(), key=lambda x: x[1]["timestamp"])[0]
            st.session_state.called_queue.append((next_song, info["name"]))
            st.success(f"🎤 {info['name']}, you're up! Get ready to sing **{next_song}**.")

# --- DISPLAY CALLED LIST ---
if st.session_state.called_queue:
    st.subheader("✅ Already Called")
    for song, name in st.session_state.called_queue:
        info = st.session_state.signups[song]
        tag = f" (@{info['instagram']})" if info['instagram'] else ""
        st.markdown(f"- {name}{tag}: {song}")

# --- FINAL SIGNUP LIST (HOST ONLY) ---
if st.session_state.host_verified:
    with st.expander("📋 View All Signups"):
        if st.button("Show Signups"):
            if not st.session_state.signups:
                st.info("No signups yet.")
            else:
                st.write("### Final Signup List")
                for song, info in sorted(st.session_state.signups.items(), key=lambda x: x[1]["timestamp"]):
                    tag = f" (@{info['instagram']})" if info['instagram'] else ""
                    st.markdown(f"- **{info['name']}**{tag} – _{song}_")
