import streamlit as st
from datetime import datetime

# --- Real Song List from Jenn's spreadsheet ---
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

# --- Session State Initialization ---
if "signups" not in st.session_state:
    st.session_state.signups = {}
if "called_queue" not in st.session_state:
    st.session_state.called_queue = []
if "host_verified" not in st.session_state:
    st.session_state.host_verified = False

st.title("🎤 Gibsons Karaoke Night")
st.markdown("One song per person. Signed-up songs are grayed out. Let's rock Ventura!")

# --- Signup Form ---
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
        elif any(name == n for (_, (n, _)) in st.session_state.signups.items()):
            st.error("You've already signed up for a song.")
        else:
                     st.session_state.signups[selected_song] = {
                "name": name,
                "timestamp": datetime.now(),
                "instagram": instagram.strip() if instagram else ""
            }

            st.success(f"{name}, you're locked in for '{selected_song}'!")

# --- Song List Display ---
st.subheader("🎶 Song List")
for song in SONG_LIST:
    if song in st.session_state.signups:
        signer = st.session_state.signups[song][0]
        st.markdown(f"- ~~{song}~~ (🎤 {signer})")
    else:
        st.markdown(f"- {song}")

# --- Host-only controls ---
st.subheader("🔐 Host Controls")

with st.expander("Enter Host PIN to Access Singer Queue", expanded=False):
    pin_input = st.text_input("Enter host PIN", type="password")
    if st.button("Unlock Controls"):
        if pin_input == "gibsons2025":  # 🔒 Set your own PIN here
            st.session_state.host_verified = True
            st.success("Host controls unlocked!")
        else:
            st.error("Incorrect PIN.")

# --- Call Next Singer (host only) ---
if st.session_state.host_verified:
    st.subheader("📣 Call the Next Singer")
    if st.button("Call Next Song"):
        remaining = {
            song: (name, time)
            for song, (name, time) in st.session_state.signups.items()
            if (song, name) not in st.session_state.called_queue
        }
        if not remaining:
            st.info("No more singers in the queue.")
        else:
            next_song, (next_name, _) = sorted(remaining.items(), key=lambda x: x[1][1])[0]
            st.session_state.called_queue.append((next_song, next_name))
            st.success(f"🎤 {next_name}, you're up! Get ready to sing **{next_song}**.")

# --- Called List ---
if st.session_state.called_queue:
    st.subheader("✅ Already Called")
    for song, name in st.session_state.called_queue:
        insta = st.session_state.signups[song].get("instagram", "")
        tag_text = f" (@{insta})" if insta else ""
        st.markdown(f"- {name}{tag_text}: {song}")

        st.markdown(f"- {name}: {song}")
# --- Show all signups (host only) ---
if st.session_state.host_verified:
    with st.expander("📋 View All Signups"):
        if st.button("Show Signups"):
            if not st.session_state.signups:
                st.info("No signups yet.")
            else:
                st.write("### Final Signup List")
                for song, info in sorted(st.session_state.signups.items(), key=lambda x: x[1]["timestamp"]):
                    insta = info.get("instagram", "")
                    tag = f" (@{insta})" if insta else ""
                    st.markdown(f"- **{info['name']}**{tag} – _{song}_")

