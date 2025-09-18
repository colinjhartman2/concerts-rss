# States to track
STATES = ["CA", "TX", "OR", "WA", "HI", "AK"]

# Ticketmaster API
# Get a free key at https://developer.ticketmaster.com/
TICKETMASTER_API_KEY = "YOUR_TICKETMASTER_KEY"

# How many hours count as "fresh/new" in RSS items
FRESH_WINDOW_HOURS = 48

# Your site/feed metadata
SITE_TITLE = "New Concert & Festival Announcements"
SITE_LINK  = "https://<your-username>.github.io/state-concerts-rss/"
SITE_DESC  = "Newly announced shows from Ticketmaster for CA, TX, OR, WA, HI, AK."

# Output folder (GitHub Pages serves /docs by default)
OUTPUT_DIR = "docs"

# SQLite database file
DB_PATH = "events.db"
