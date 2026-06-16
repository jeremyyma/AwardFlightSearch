"""
Delta Multi-City Award Flight Scraper
Calls Delta's GraphQL offer API directly to find low-mile award availability
for multi-city itineraries across a range of dates.

USAGE
-----
1. Open Chrome and go to delta.com.
2. Run any multi-city award search (e.g. PDX→AMS, 3 passengers, Shop with Miles).
3. Open DevTools (Cmd+Option+I) → Network tab → filter by "rm-offer-gql".
4. Right-click that request → Copy → Copy as cURL (bash).
5. Save the copied text to delta_curl.txt in this folder.
6. Immediately run: python scraper.py
   (Session cookies expire in ~30 min — run right after copying.)

PROMPTS
-------
  Start/end date  — date range to search (outbound leg)
  Max miles       — mile ceiling per direction (default 30,000)

The scraper searches HOME_BASE ↔ each hub in EURO_HUBS for every date,
returning only itineraries where 3+ seats are available at or below the limit.
"""
import json
import os
import re
import sys
import time
import random
from datetime import datetime, timedelta
from pathlib import Path

try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    print("ERROR: curl_cffi not installed. Run: pip install curl-cffi")
    sys.exit(1)

# ── Constants ────────────────────────────────────────────────────────────────
EURO_HUBS = ["AMS", "CDG", "MXP"]
HOME_BASE = "PDX"
DEFAULT_MAX_MILES = 30_000
SEATS = 3
TRIP_DURATION = 10

DATE_FORMAT = "%m/%d/%Y"
START_DATE = datetime(2026, 8, 28)
END_DATE = datetime(2026, 9, 13)
DEBUG_DIR = Path(os.environ.get("SCRAPER_DEBUG_DIR", "debug_output"))
CURL_FILE = os.environ.get("DELTA_CURL_FILE", "delta_curl.txt")

DELAY_MIN = float(os.environ.get("DELAY_MIN", "1.5"))
DELAY_MAX = float(os.environ.get("DELAY_MAX", "3.5"))

OFFER_URL = "https://offer-api-prd.delta.com/prd/rm-offer-gql"

GQL_QUERY = """query ($offerSearchCriteria: OfferSearchCriteriaInput!) {
  gqlSearchOffers(offerSearchCriteria: $offerSearchCriteria) {
    gqlOffersSets {
      trips {
        tripId
        originAirportCode
        destinationAirportCode
        scheduledDepartureLocalTs
        stopCnt
      }
      offers {
        offerId
        soldOut
        additionalOfferProperties { fareType soldOut unavailableForSale }
        offerItems {
          retailItems {
            retailItemMetaData {
              fareInformation {
                availableSeatCnt
                farePrice {
                  totalFarePrice {
                    milesEquivalentPrice { mileCnt }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}"""


def parse_curl(curl_text: str) -> tuple:
    cookie_match = re.search(r"-b '([^']+)'", curl_text)
    if not cookie_match:
        cookie_match = re.search(r'--cookie "([^"]+)"', curl_text)
    cookies = cookie_match.group(1) if cookie_match else ""

    headers = {}
    for m in re.finditer(r"-H '([^']+)'", curl_text):
        parts = m.group(1).split(": ", 1)
        if len(parts) == 2:
            headers[parts[0].lower()] = parts[1]
    for m in re.finditer(r'-H "([^"]+)"', curl_text):
        parts = m.group(1).split(": ", 1)
        if len(parts) == 2:
            headers[parts[0].lower()] = parts[1]
    return cookies, headers


def load_session() -> tuple:
    curl_path = Path(CURL_FILE)
    if curl_path.exists():
        print(f"Reading session from {CURL_FILE} ...")
        curl_text = curl_path.read_text()
    else:
        print(f"File '{CURL_FILE}' not found.")
        print("Paste your cURL command, then press Enter twice:")
        lines = []
        while True:
            line = input()
            if line == "" and lines and lines[-1] == "":
                break
            lines.append(line)
        curl_text = "\n".join(lines)

    cookies, headers = parse_curl(curl_text)
    if not cookies:
        print("WARNING: No cookies parsed from the curl command.")
    return cookies, headers


def build_payload(hub: str, outbound_date: str, return_date: str) -> dict:
    out_dt = datetime.strptime(outbound_date, DATE_FORMAT).strftime("%Y-%m-%dT00:00:00")
    ret_dt = datetime.strptime(return_date, DATE_FORMAT).strftime("%Y-%m-%dT00:00:00")
    return {
        "variables": {
            "offerSearchCriteria": {
                "productGroups": [{"productCategoryCode": "FLIGHTS"}],
                "offersCriteria": {
                    "resultsPageNum": 1,
                    "resultsPerRequestNum": 30,
                    "preferences": {
                        "refundableOnly": False,
                        "showGlobalRegionalUpgradeCertificate": True,
                        "nonStopOnly": False,
                        "excludeBrandTypes": [],
                    },
                    "pricingCriteria": {"priceableIn": ["MILES"]},
                    "flightRequestCriteria": {
                        "currentTripIndexId": "0",
                        "sortableOptionId": None,
                        "selectedOfferId": "",
                        "searchOriginDestination": [
                            {
                                "departureLocalTs": out_dt,
                                "destinations": [{"airportCode": hub}],
                                "origins": [{"airportCode": HOME_BASE}],
                            },
                            {
                                "departureLocalTs": ret_dt,
                                "destinations": [{"airportCode": HOME_BASE}],
                                "origins": [{"airportCode": hub}],
                            },
                        ],
                        "sortByBrandId": "MAIN",
                        "additionalCriteriaMap": {"rollOutTag": "GBB"},
                    },
                },
                "customers": [
                    {"passengerTypeCode": "ADT", "passengerId": str(i)}
                    for i in range(1, SEATS + 1)
                ],
            }
        },
        "query": GQL_QUERY,
    }


def call_offer_api(payload: dict, cookies: str, base_headers: dict, tx_id: str) -> dict | None:
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "airline": "DL",
        "applicationid": "DC",
        "authorization": base_headers.get("authorization", "GUEST"),
        "channelid": "DCOM",
        "content-type": "application/json",
        "origin": "https://www.delta.com",
        "referer": "https://www.delta.com/",
        "transactionid": tx_id,
        "user-agent": base_headers.get(
            "user-agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        ),
        "x-app-route": "search",
        "x-app-type": "dcom-shop",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "Cookie": cookies,
    }
    try:
        resp = cffi_requests.post(
            OFFER_URL, headers=headers, json=payload, impersonate="chrome124", timeout=30
        )
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 444:
            print("    HTTP 444: session expired — copy a fresh curl from Chrome and restart.")
            sys.exit(1)
        print(f"    HTTP {resp.status_code}: {resp.text[:200]}")
        return None
    except Exception as exc:
        print(f"    Request error: {exc}")
        return None


def extract_results(data: dict, hub: str, outbound_date: str, return_date: str, max_miles: int = DEFAULT_MAX_MILES) -> bool:
    found = False
    try:
        offer_sets = data["data"]["gqlSearchOffers"]["gqlOffersSets"]
    except (KeyError, TypeError):
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        path = DEBUG_DIR / f"{hub.lower()}_{outbound_date.replace('/','')}_err.json"
        path.write_text(json.dumps(data, indent=2))
        print(f"    Unexpected response shape — saved {path}")
        return False

    for offer_set in offer_sets:
        for offer in offer_set.get("offers") or []:
            props = offer.get("additionalOfferProperties") or {}
            if offer.get("soldOut") or props.get("soldOut") or props.get("unavailableForSale"):
                continue
            fare_type = props.get("fareType", "")
            for item in offer.get("offerItems") or []:
                for retail in item.get("retailItems") or []:
                    # fareInformation is a list
                    fare_info_list = (
                        retail.get("retailItemMetaData", {}).get("fareInformation") or []
                    )
                    if isinstance(fare_info_list, dict):
                        fare_info_list = [fare_info_list]
                    for fare_info in fare_info_list:
                        seats_left = fare_info.get("availableSeatCnt") or 0
                        if seats_left < SEATS:
                            continue
                        # farePrice is also a list
                        fare_price_list = fare_info.get("farePrice") or []
                        if isinstance(fare_price_list, dict):
                            fare_price_list = [fare_price_list]
                        for fare_price in fare_price_list:
                            miles = (
                                fare_price.get("totalFarePrice", {})
                                .get("milesEquivalentPrice", {})
                                .get("mileCnt", 0)
                            )
                            if miles and miles <= max_miles:
                                print(
                                    f"  FOUND {outbound_date}/{return_date} | "
                                    f"{HOME_BASE}->{hub}->{HOME_BASE} | "
                                    f"{miles:,} miles | {fare_type} | {seats_left}+ seats"
                                )
                                found = True
    return found


def get_date_range() -> tuple:
    s = input("Start date (MM/DD/YYYY) [default 08/28/2026]: ").strip()
    e = input("End date   (MM/DD/YYYY) [default 09/13/2026]: ").strip()
    start = datetime.strptime(s, DATE_FORMAT) if s else START_DATE
    end = datetime.strptime(e, DATE_FORMAT) if e else END_DATE
    if start > end:
        raise ValueError("Start must be on or before end date")
    return start, end


def get_max_miles() -> int:
    raw = input(f"Max miles per direction [default {DEFAULT_MAX_MILES:,}]: ").strip()
    if not raw:
        return DEFAULT_MAX_MILES
    try:
        return int(raw.replace(",", ""))
    except ValueError:
        print(f"Invalid input, using default {DEFAULT_MAX_MILES:,}")
        return DEFAULT_MAX_MILES


def main() -> None:
    cookies, base_headers = load_session()
    mc = re.search(r"mc_cache_key=([^;]+)", cookies)
    base_tx = mc.group(1) if mc else "delta-scraper"

    start_date, end_date = get_date_range()
    max_miles = get_max_miles()
    total_days = (end_date - start_date).days + 1
    print(f"\n{total_days} days x {len(EURO_HUBS)} hubs = {total_days * len(EURO_HUBS)} searches")
    print(f"Looking for {SEATS} seats <= {max_miles:,} miles\n")

    current = start_date
    while current <= end_date:
        return_dt = current + timedelta(days=TRIP_DURATION)
        out_str = current.strftime(DATE_FORMAT)
        ret_str = return_dt.strftime(DATE_FORMAT)
        print(f"--- {out_str} out / {ret_str} back ---")

        for hub in EURO_HUBS:
            tx_id = f"{base_tx}_{int(time.time()*1000)}"
            payload = build_payload(hub, out_str, ret_str)
            data = call_offer_api(payload, cookies, base_headers, tx_id)
            if data:
                if not extract_results(data, hub, out_str, ret_str, max_miles):
                    print(f"    {HOME_BASE}->{hub}: no fares <= {max_miles:,} miles")
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        current += timedelta(days=1)

    print("\nDone.")


if __name__ == "__main__":
    main()
