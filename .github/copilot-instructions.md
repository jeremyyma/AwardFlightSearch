# Delta Award Flight Scraper

Scans Delta's live award inventory for multi-city itineraries across a date range,
reporting itineraries where 3+ seats are available at or below a mile ceiling.

## Architecture

The scraper calls Delta's internal GraphQL endpoint (`offer-api-prd.delta.com/prd/rm-offer-gql`)
directly using session cookies copied from a real Chrome browser session. `curl_cffi` is used
to impersonate Chrome's TLS fingerprint so Akamai accepts the request.

No proxy service, no Playwright, no account login required.

## Key constants (scraper.py)

- `EURO_HUBS` — destination airports to check
- `HOME_BASE` — origin airport (PDX)
- `SEATS` — minimum seats required (3)
- `TRIP_DURATION` — days between outbound and return (10)
- `DEFAULT_MAX_MILES` — default mile ceiling shown at prompt (30,000)

## Session cookie refresh workflow

1. Open Chrome → delta.com → run one multi-city award search (3 pax, Shop with Miles).
2. DevTools → Network → filter `rm-offer-gql` → right-click → Copy as cURL (bash).
3. Save to `delta_curl.txt` in the project root.
4. Run `python scraper.py` immediately (cookies expire in ~30 min).

## User prompts

1. Start date (MM/DD/YYYY)
2. End date (MM/DD/YYYY)
3. Max miles per direction (integer, default 30,000)

## Response parsing

`fareInformation` and `farePrice` are both arrays in the GraphQL response.
The parser iterates both and filters by `availableSeatCnt >= SEATS` and `mileCnt <= max_miles`.
