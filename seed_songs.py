from google.cloud import firestore

# Connect to Firestore (uses your Cloud Run service account if run in Cloud Shell,
# or your gcloud auth if run locally)
db = firestore.Client()

songs = [
    "A Day To Remember - The Downfall Of Us All",
    "AFI - Miss Murder",
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
    "Panic! At The Disco - I Write Sins Not Tragedies",
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
    "Yellowcard - Only One",
]

for title in songs:
    db.collection("songs").add({"title": title})

print(f"✅ Added {len(songs)} songs to Firestore collection 'songs'")
