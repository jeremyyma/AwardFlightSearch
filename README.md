# Delta Award Flight Scraper

Scans Delta's live award inventory across a range of dates and destination hubs, reporting any itinerary where **3+ seats** are available at or below your chosen mile ceiling — no account login required.

## How it works

Delta's flight-search app calls an internal GraphQL API (`offer-api-prd.delta.com`). This scraper replays those calls using your browser's session cookies, which avoids bot-detection while requiring no credentials or API key.

## Requirements

- Python 3.10+
- Google Chrome

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/AwardFlightSearch.git
cd AwardFlightSearch
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Getting your session cookies (every ~30 min)

1. Open **Chrome** and go to [delta.com](https://www.delta.com/flightsearch/book-a-flight).
2. Run any multi-city award search — pick any date, set **3 passengers**, enable **Shop with Miles**.
3. Open **DevTools** (`Cmd+Option+I` on Mac, `F12` on Windows) → **Network** tab.
4. In the filter box, type `rm-offer-gql` and wait for a request to appear.
5. Right-click the request → **Copy** → **Copy as cURL (bash)**.
6. Paste the copied text into a file named `delta_curl.txt` in the project folder:

```bash
pbpaste > delta_curl.txt     # Mac
# or just open delta_curl.txt in a text editor and paste
```

## Running

```bash
source .venv/bin/activate
python scraper.py
```

You will be prompted for:

| Prompt | Example | Default |
|---|---|---|
| Start date | `08/28/2026` | `08/28/2026` |
| End date | `09/13/2026` | `09/13/2026` |
| Max miles per direction | `60000` | `30000` |

Press **Enter** to accept any default.

## Sample output

```
Reading session from delta_curl.txt ...
Start date (MM/DD/YYYY) [default 08/28/2026]: 08/28/2026
End date   (MM/DD/YYYY) [default 09/13/2026]: 09/07/2026
Max miles per direction [default 30,000]: 60000

11 days x 3 hubs = 33 searches
Looking for 3 seats <= 60,000 miles

--- 08/28/2026 out / 09/07/2026 back ---
    PDX->AMS: no fares <= 60,000 miles
    PDX->CDG: no fares <= 60,000 miles
    PDX->MXP: no fares <= 60,000 miles
--- 08/29/2026 out / 09/08/2026 back ---
  FOUND 08/29/2026/09/08/2026 | PDX->CDG->PDX | 57,500 miles | MAIN | 4+ seats
--- 08/30/2026 out / 09/09/2026 back ---
    PDX->AMS: no fares <= 60,000 miles
    ...

Done.
```

## Checking the current price floor

If searches return no results, run this snippet to see what Delta's lowest available award price actually is for the most recently fetched date:

```bash
python3 -c "
import json
data = json.load(open('debug_output/sample.json'))
miles = []
for s in data['data']['gqlSearchOffers']['gqlOffersSets']:
    for o in s.get('offers', []):
        for i in o.get('offerItems', []):
            for r in i.get('retailItems', []):
                for fi in (r.get('retailItemMetaData', {}).get('fareInformation') or []):
                    for fp in (fi.get('farePrice') or []):
                        m = fp.get('totalFarePrice', {}).get('milesEquivalentPrice', {}).get('mileCnt')
                        if m: miles.append(m)
print('Lowest available:', f'{min(miles):,} miles' if miles else 'none')
print('All tiers:', [f'{m:,}' for m in sorted(set(miles))])
"
```

Example output (PDX→AMS Aug 28, 2026):
```
Lowest available: 85,500 miles
All tiers: ['85,500', '105,300', '114,300', '127,800', '309,400', '428,900']
```

This tells you the realistic threshold to search at for that route and date.

## Configuration

Edit the constants at the top of `scraper.py` to change destinations or trip length:

| Constant | Default | Description |
|---|---|---|
| `EURO_HUBS` | `["AMS", "CDG", "MXP"]` | Destination airport codes |
| `HOME_BASE` | `"PDX"` | Origin airport |
| `SEATS` | `3` | Minimum seats required |
| `TRIP_DURATION` | `10` | Days between outbound and return |
| `DEFAULT_MAX_MILES` | `30_000` | Default mile ceiling (overridden at prompt) |

## Notes

- Session cookies from delta.com expire in approximately **30 minutes**. Re-copy the curl and update `delta_curl.txt` if you see `HTTP 444: session expired`.
- The `debug_output/` folder stores the raw JSON response from the last search for each hub/date. Useful for inspecting the data structure or troubleshooting.
- Do not commit `delta_curl.txt` — it contains your browser session cookies.

## License

MIT — see [LICENSE](LICENSE).
