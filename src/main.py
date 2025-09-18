import os, time, json, hashlib, sqlite3, pathlib, datetime
from urllib.parse import urlencode
import requests
from feedgen.feed import FeedGenerator

from config import (
    STATES, TICKETMASTER_API_KEY, FRESH_WINDOW_HOURS,
    SITE_TITLE, SITE_LINK, SITE_DESC, OUTPUT_DIR, DB_PATH
)

TM_BASE = "https://app.ticketmaster.com/discovery/v2/events.json"

def now_utc():
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)

def ts_iso(dt):
    return dt.astimezone(datetime.timezone.utc).isoformat()

def ensure_db(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS events (
      id TEXT PRIMARY KEY,             -- stable TM id
      headline TEXT,
      start_utc TEXT,
      venue TEXT,
      city TEXT,
      state TEXT,
      url TEXT,
      source TEXT,                     -- 'ticketmaster'
      first_seen_utc TEXT,             -- when we first stored it
      raw JSON
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_state_start ON events(state, start_utc);")
    conn.commit()

def fetch_ticketmaster(state_code, page_size=200):
    params = {
        "apikey": TICKETMASTER_API_KEY,
        "countryCode": "US",
        "stateCode": state_code,
        "classificationName": "music",
        "size": page_size,
        "sort": "date,asc"
    }
    url = f"{TM_BASE}?{urlencode(params)}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    events = data.get("_embedded", {}).get("events", [])
    out = []
    for e in events:
        # normalize
        start = e.get("dates", {}).get("start", {})
        start_dt = start.get("dateTime") or (start.get("localDate") + "T00:00:00Z" if start.get("localDate") else None)

        venues = e.get("_embedded", {}).get("venues", [])
        v = venues[0] if venues else {}
        out.append({
            "id": e.get("id"),
            "headline": e.get("name"),
            "start_utc": start_dt,
            "venue": v.get("name"),
            "city": v.get("city", {}).get("name"),
            "state": v.get("state", {}).get("stateCode") or state_code,
            "url": e.get("url"),
            "source": "ticketmaster",
            "raw": e
        })
    return out

def upsert_events(conn, events):
    cur = conn.cursor()
    inserted = 0
    for ev in events:
        cur.execute("SELECT id FROM events WHERE id = ?", (ev["id"],))
        exists = cur.fetchone()
        if not exists:
            cur.execute("""
                INSERT INTO events(id, headline, start_utc, venue, city, state, url, source, first_seen_utc, raw)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ev["id"], ev["headline"], ev["start_utc"], ev["venue"], ev["city"], ev["state"], ev["url"],
                ev["source"], ts_iso(now_utc()), json.dumps(ev["raw"])
            ))
            inserted += 1
        else:
            # Optional: keep first_seen_utc stable; update metadata if you want
            pass
    conn.commit()
    return inserted

def query_recent(conn, state=None, fresh_hours=48):
    cutoff = now_utc() - datetime.timedelta(hours=fresh_hours)
    if state:
        rows = conn.execute("""
            SELECT id, headline, start_utc, venue, city, state, url, source, first_seen_utc
            FROM events
            WHERE state = ? AND first_seen_utc >= ?
            ORDER BY first_seen_utc DESC
        """, (state, ts_iso(cutoff))).fetchall()
    else:
        rows = conn.execute("""
            SELECT id, headline, start_utc, venue, city, state, url, source, first_seen_utc
            FROM events
            WHERE first_seen_utc >= ?
            ORDER BY first_seen_utc DESC
        """, (ts_iso(cutoff),)).fetchall()
    return rows

def ensure_output():
    pathlib.Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

def build_feed(rows, title_suffix, filename):
    ensure_output()
    fg = FeedGenerator()
    fg.load_extension('podcast')  # harmless; ensures full RSS
    fg.title(f"{SITE_TITLE} – {title_suffix}")
    fg.link(href=SITE_LINK, rel='alternate')
    fg.description(SITE_DESC)
    fg.language('en')

    for r in rows:
        (id_, headline, start_utc, venue, city, state, url, source, first_seen) = r
        fe = fg.add_entry()
        fe.id(id_)
        fe.title(headline or "New event")
        summary_bits = []
        if venue: summary_bits.append(venue)
        if city and state: summary_bits.append(f"{city}, {state}")
        if start_utc: summary_bits.append(f"Starts: {start_utc}")
        fe.link(href=url or SITE_LINK)
        fe.published(first_seen)
        fe.updated(first_seen)
        fe.description(" • ".join(summary_bits))

    rss_bytes = fg.rss_str(pretty=True)
    with open(os.path.join(OUTPUT_DIR, filename), "wb") as f:
        f.write(rss_bytes)

def main():
    conn = sqlite3.connect(DB_PATH)
    ensure_db(conn)

    total_new = 0
    for st in STATES:
        try:
            events = fetch_ticketmaster(st)
            total_new += upsert_events(conn, events)
            time.sleep(0.5)  # be nice
        except Exception as ex:
            print(f"[WARN] {st} fetch failed: {ex}")

    # Build feeds
    all_rows = query_recent(conn, None, FRESH_WINDOW_HOURS)
    build_feed(all_rows, "All States", "all.xml")

    for st in STATES:
        rows = query_recent(conn, st, FRESH_WINDOW_HOURS)
        build_feed(rows, st, f"{st.lower()}.xml")

    print(f"Done. Inserted new events: {total_new}")

if __name__ == "__main__":
    main()
