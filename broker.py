import os
import requests
import json
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from helper import get_current_timestamp

# Initialize the environment wrapper before setting global variables
load_dotenv()

BCS_API_REFRESH_KEY = os.getenv("BCS_API_REFRESH_KEY")
BCS_API_ACCESS_KEY = os.getenv("BCS_API_ACCESS_KEY")

BCS_API_REFRESH_KEYS = {
    "Broker": os.getenv("BCS_API_REFRESH_KEY6998"),
    "IIS1": os.getenv("BCS_API_REFRESH_KEY7352"),
    "IIS2": os.getenv("BCS_API_REFRESH_KEY9373"),
    "IIS3": os.getenv("BCS_API_REFRESH_KEY9563")
}

def get_portfolio_data(access_token):
    # Getting portfolio data
    portfolio_url = "https://be.broker.ru/trade-api-bff-portfolio/api/v1/portfolio"

    portfolio_headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }

    # Keep payload empty but execute the request
    portfolio_response = requests.get(portfolio_url, headers=portfolio_headers)

    print("\nPortfolio Response Status:", portfolio_response.status_code)
    print("Portfolio Response Data:")
    print(portfolio_response.text[:1000])

    if portfolio_response.status_code != 200:
        return None

    return portfolio_response


def get_access_token(refresh_token):
    # Getting access token with provided refresh token
    # 1. Configuration
    # IMPORTANT: Change to "trade-api-read" if your token is Read-Only
    CLIENT_ID = "trade-api-write" 

    # 2. Getting the Access Token
    auth_url = "https://be.broker.ru/trade-api-keycloak/realms/tradeapi/protocol/openid-connect/token"

    auth_payload = {
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }

    auth_headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }

    auth_response = requests.post(auth_url, headers=auth_headers, data=auth_payload)

    # 3. Verify Auth request succeeded
    if auth_response.status_code != 200:
        print(f"Auth failed: {auth_response.status_code} - {auth_response.text}")
        return None
    
    # 4. Crucial step: Extract the actual token string from the JSON response
    tokens_json = auth_response.json()
    bcs_access_token = tokens_json.get("access_token")

    # 5. Return the access token
    if bcs_access_token:
        print("Access Token successfully generated.")
        return bcs_access_token

    return None


def parse_portfolio_data(portfolio_data):
    # Example Usage:
    # parsed_data = load_and_parse_stored_portfolio("portfolio_2026-11-04_12-54-14.json")
    # print(parsed_data["LKOH"])  # Instantly check your LUKOIL position
    # 1. Read the structured JSON file back into Python
    #with open(filename, "r", encoding="utf-8") as f:
    #    portfolio_data = json.load(f)
    
    # 2. Process the data (filtering out T0/T1 duplicates, using T2)
    unique_portfolio = {}
    for item in portfolio_data:
        if item.get("term") != "T2":
            continue
            
        ticker = item.get("ticker")
        unique_portfolio[ticker] = {
            "name": item.get("displayName"),
            "ticker": item.get("ticker"),
            "type": item.get("instrumentType") or item.get("type"),
            "quantity": item.get("quantity"),
            "value_rub": item.get("currentValueRub"),
            "pl_rub": item.get("unrealizedPL"),
            "pl_percent": item.get("unrealizedPercentPL")
        }
        
    return unique_portfolio


def save_portfolio_data(portfolio_data, prefix=""):
    # 1. Standardize your filename (no colons for Windows)
    safe_timestamp = get_current_timestamp().replace(":", "-").replace(" ", "_")
    report_filename = f"portfolio_{safe_timestamp}{prefix}.json"

    # 2. Save it as a properly formatted JSON file
    with open(report_filename, "w", encoding="utf-8") as f:
        json.dump(portfolio_data, f, ensure_ascii=False, indent=4)
        
    print(f"Portfolio successfully saved to {report_filename}")


def fetch_bcs_trades_chunked(refresh_token, start_str="2026-02-01", end_str="2026-11-13", chunk_days=7):
    bcs_access_token = get_access_token(refresh_token)
    if not bcs_access_token:
        print("Failed to obtain access token.")
        return

    url = "https://be.broker.ru/trade-api-bff-trade-details/api/v1/trades/search"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {bcs_access_token}",
    }

    start_dt = datetime.strptime(start_str, "%Y-%m-%d")
    end_dt = datetime.strptime(end_str, "%Y-%m-%d")
    
    all_records = []
    seen_trade_nums = set()
    page_size = 100

    current_start = start_dt
    while current_start <= end_dt:
        current_end = min(current_start + timedelta(days=chunk_days - 1), end_dt)
        
        s_iso = current_start.strftime("%Y-%m-%dT00:00:00.000Z")
        e_iso = current_end.strftime("%Y-%m-%dT23:59:59.000Z")
        
        offset = 0
        while True:
            payload = json.dumps({
                "size": page_size,
                "offset": offset,
                "startDateTime": s_iso,
                "endDateTime": e_iso,
            })

            response = requests.post(url, headers=headers, data=payload)
            if response.status_code == 429:
                time.sleep(5)
                continue
            if response.status_code == 204 or not response.text.strip():
                # Empty response body means no trades in this window/page
                break
            if response.status_code != 200:
                print(f"Error {response.status_code} for {s_iso[:10]}..{e_iso[:10]}: {response.text}")
                break

            try:
                data = response.json()
            except ValueError:
                print(f"Non-JSON response for {s_iso[:10]}..{e_iso[:10]}: {repr(response.text[:200])}")
                break

            records = data.get("records", [])
            if not records:
                break

            new_count = 0
            for rec in records:
                t_num = rec.get("tradeNum")
                if t_num not in seen_trade_nums:
                    seen_trade_nums.add(t_num)
                    all_records.append(rec)
                    new_count += 1

            total_records = data.get("totalRecords", 0)
            if new_count == 0 or len(records) < page_size or (offset + len(records)) >= total_records:
                break

            offset += page_size
            time.sleep(0.5)

        print(f"Window {s_iso[:10]} -> {e_iso[:10]}: total unique trades = {len(all_records)}")
        current_start = current_end + timedelta(days=1)
        time.sleep(0.5)

    final_payload = {"records": all_records, "totalRecords": len(all_records)}
    save_portfolio_data(final_payload, "_trades")
    print(f"Done! Saved {len(all_records)} total unique trades.")
    return final_payload


def trades_pipeline(refresh_token):
    # 1. Getting trades
    parsed_trades = fetch_bcs_trades_chunked(refresh_token, start_str="2026-10-01", end_str="2026-11-13", chunk_days=7)

    # 2. Clean trades
    cleaned_trades = clean_trade_records(parsed_trades)

    # 3. Save trades
    save_portfolio_data(cleaned_trades, "_trades_cleaned")


def clean_trade_records(raw_data):
    """
    Cleans raw BCS trade JSON data, keeping only core fields for trade analysis.
    Accepts either a file path (str) or a parsed JSON dict/list.
    """
    # Example usage:
    # cleaned_trades = clean_trade_records(final_payload)
    # Or directly from a saved JSON file:
    # cleaned_trades = clean_trade_records("path/to/your_trades.json")
    if isinstance(raw_data, str):
        with open(raw_data, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

    records = raw_data.get("records", []) if isinstance(raw_data, dict) else raw_data
    side_map = {"1": "buy", "2": "sell"}
    
    cleaned = []
    for rec in records:
        raw_side = str(rec.get("side", ""))
        cleaned.append({
            "ticker": rec.get("ticker"),
            "price": rec.get("price"),
            "date": rec.get("tradeDateTime"),
            "quantity": rec.get("tradeQuantity"),
            "lots": rec.get("tradeQuantityLots"),
            "side": side_map.get(raw_side, raw_side),
        })

    # Sort chronologically from oldest to newest
    cleaned.sort(key=lambda x: x["date"] or "")
    return cleaned


def portfolio_pipeline(refresh_token, portfolio_name=""):
    # 1. Getting the access token
    bcs_access_token = get_access_token(refresh_token)

    if not bcs_access_token:
        return
    
    # 2. Requesting Portfolio Data
    portfolio_response = get_portfolio_data(bcs_access_token)

    if not portfolio_response:
        return

    # 3. Save portfolio data
    save_portfolio_data(portfolio_response.json())

    # 4. Parse portfolio data
    parsed_portfolio = parse_portfolio_data(portfolio_response.json())

    # 5. Save clean portfolio data
    save_portfolio_data(parsed_portfolio, f"_{portfolio_name}_parsed")


if __name__ == "__main__":

    exit()
        
    trades_pipeline(BCS_API_REFRESH_KEY)
    
    for portfolio, key in BCS_API_REFRESH_KEYS.items():
        portfolio_pipeline(key, portfolio)
        time.sleep(1)