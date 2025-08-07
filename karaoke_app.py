import streamlit as st
from datetime import datetime

# --- SONG LIST FROM FILE ---
SONG_LIST = [
    "Mayday Parade - Jamie All Over",
    "Sugarcult - Memory",
    "Simple Plan - I'd Do Anything",
    "Brand New - The Quiet Things That No One Ever Knows",
    "Say Anything - Wow, I Can Get Sexual Too",
    "Good Charlotte - Girls & Boys",
    "The Story So Far - Empty Space",
    "Brand New - Mix Tape",
    "Something Corporate - Punk Rock Princess",
    "Hawthorne Heights - Ohio Is for Lovers",
    "Paramore - Misery Business",
    "Taking Back Sunday - Cute Without the 'E' (Cut from the Team)",
    "Fall Out Boy - Sugar, We're Goin Down",
    "Motion City Soundtrack - Everything Is Alright",
    "All Time Low - Dear Maria, Count Me In",
    "A Day to Remember - If It Means a Lot to You",
    "Dashboard Confessional - Screaming Infidelities",
    "The Used - The Taste of Ink",
    "Blink-182 - I Miss You",
    "Jimmy Eat World - The Middle",
    "The Ataris - In This Diary",
    "Panic! At The Disco - I Write Sins Not Tragedies",
    "Yellowcard - Ocean Avenue",
    "Pierce the Veil - King for a Day",
    "My Chemical Romance - I'm Not Okay (I Promise)",
    "Green Day - Basket Case",
    "AFI - Miss Murder",
    "The All-American Rejects - Swing, Swing",
    "Sum 41 - Fat Lip",
    "The Red Jumpsuit Apparatus - Face Down",
    "Boys Like Girls - The Great Escape",
    "Cute Is What We Aim For - The Curse of Curves",
    "We The Kings - Check Yes Juliet",
    "Cartel - Honestly",
    "The Academy Is... - About a Girl",
    "New Found Glory - My Friends Over You",
    "Relient K - Be My Escape",
    "Escape the Fate - Situations",
    "Senses Fail - Buried a Lie",
    "Armor for Sleep - Car Underwater",
    "Matchbook Romance - My Eyes Burn",
    "The Starting Line - Best of Me",
    "Anberlin - Feel Good Drag",
    "Plain White T's - Hate (I Really Don't Like You)",
    "The Maine - Into Your Arms",
    "Forever the Sickest Kids - Woah Oh! (Me vs. Everyone)",
    "Red Hot Chili Peppers - Dani California",
    "The Killers - Mr. Brightside",
    "Paramore - That's What You Get",
    "Fountains of Wayne - Stacy's Mom"
]

# --- SESSION STATE ---
if "signups" not in st.session_state:
    st.session_state.signups = {}
if "called_queue" not in st.session_state:
    st.session_state.called_queue = []
if "host_verified" not in st.session_state:
    st.session_state.host_verified = False

st.title("🎤 Gibsons Karaoke Night")
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
        if pin_input == "gibsons2025":  # <-- You can change this
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
            # Sort by earliest signup
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
