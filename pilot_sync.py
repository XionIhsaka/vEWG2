import requests
import json
import os
import time
from datetime import datetime
from typing import Optional

# Configuration - Environment variables set in GitHub Secrets
CLIENT_ID = os.environ.get("VAMSYS_CLIENT_ID")
CLIENT_SECRET = os.environ.get("VAMSYS_CLIENT_SECRET")

TOKEN_URL = "https://vamsys.io/oauth/token"
INITIAL_URL = "https://vamsys.io/api/v3/operations/pilots?page%5Bsize%5D=100"
OUTPUT_FILE = "pilot_activity.json"

def get_access_token() -> Optional[str]:
    """Fetches the OAuth2 token from vAMSYS using Client Credentials."""
    if not CLIENT_ID or not CLIENT_SECRET:
        print("Error: Missing VAMSYS_CLIENT_ID or VAMSYS_CLIENT_SECRET.")
        return None

    try:
        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "scope": "*",
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception as e:
        print(f"Authentication failed: {e}")
        return None

def get_next_url(res_json: dict) -> Optional[str]:
    """
    Robustly finds the 'next' page URL across different API formats.
    Handles dictionary links, list links, and metadata objects.
    """
    links = res_json.get("links")
    
    # Case 1: 'links' is a dictionary {"next": "https://..."}
    if isinstance(links, dict):
        return links.get("next")

    # Case 2: 'links' is a list of objects [{"label": "Next", "url": "..."}]
    if isinstance(links, list):
        for item in links:
            if not isinstance(item, dict):
                continue
            
            label = str(item.get("label", "")).strip().lower()
            rel = str(item.get("rel", "")).strip().lower()
            url = item.get("url")

            # Check for common 'next' indicators including HTML entities like &raquo;
            if url and (label == "next" or rel == "next" or "next" in label or "raquo" in label):
                return url

    # Case 3: 'meta' object fallback
    meta = res_json.get("meta")
    if isinstance(meta, dict):
        return meta.get("next_page_url")

    return None

def generate_pilot_json():
    """Main execution: authenticates, paginates through pilots, and saves JSON."""
    token = get_access_token()
    if not token:
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    all_pilots = []
    seen_ids = set()
    page_count = 0
    url = INITIAL_URL

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting sync...")

    while url:
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            res_json = response.json()
        except Exception as e:
            print(f"Request failed on page {page_count + 1}: {e}")
            break

        data = res_json.get("data", [])
        if not data:
            print("No more data returned from API.")
            break

        added_this_page = 0
        for p in data:
            if not isinstance(p, dict):
                continue

            # Capture the pilot identifier (e.g., DLH123)
            pilot_id = p.get("callsign") or p.get("username")
            
            if pilot_id and pilot_id not in seen_ids:
                seen_ids.add(pilot_id)
                all_pilots.append({"pilot_id": pilot_id})
                added_this_page += 1

        page_count += 1
        print(f"Page {page_count}: Processed {len(data)} items. Total unique: {len(all_pilots)}")

        # Find the next page URL
        url = get_next_url(res_json)
        
        # Safety stop to prevent infinite loops (vAMSYS active roster is usually < 100 pages)
        if not url or page_count >= 150:
            break
        
        # Brief sleep to respect API rate limits
        time.sleep(0.1)

    # Prepare data in the LH-Virtual style with a human-readable timestamp
    output_data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(all_pilots),
        "pilots": all_pilots
    }

    # Write to file
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4, ensure_ascii=False)
        print(f"\nSUCCESS: {len(all_pilots)} pilots saved to {OUTPUT_FILE}")
    except OSError as e:
        print(f"Error saving file: {e}")

if __name__ == "__main__":
    generate_pilot_json()
