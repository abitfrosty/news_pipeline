import os
import requests
import json
from dotenv import load_dotenv
from helper import get_current_timestamp

# Initialize the environment wrapper before setting global variables
load_dotenv()

BCS_API_REFRESH_KEY = os.getenv("BCS_API_REFRESH_KEY")
BCS_API_ACCESS_KEY = os.getenv("BCS_API_ACCESS_KEY")

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


if __name__ == "__main__":
    # 1. Getting the access token
    bcs_access_token = get_access_token(BCS_API_REFRESH_KEY)

    if not bcs_access_token:
        exit()
    
    # 2. Requesting Portfolio Data
    portfolio_response = get_portfolio_data(bcs_access_token)

    if not portfolio_response:
        exit()

    # 3. Save portfolio data
    save_portfolio_data(portfolio_response.json())

    # 4. Parse portfolio data
    parsed_portfolio = parse_portfolio_data(portfolio_response.json())

    # 5. Save clean portfolio data
    save_portfolio_data(parsed_portfolio, "_parsed")
      