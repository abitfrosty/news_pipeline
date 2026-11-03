import os
import requests
from dotenv import load_dotenv


# Initialize the environment wrapper before setting global variables
load_dotenv()

BCS_API_KEY = os.getenv("BCS_API_KEY")
BCS_API_ACCESS_KEY = os.getenv("BCS_API_ACCESS_KEY")

def connect():

    # Getting portfolio data
    url = "https://be.broker.ru/trade-api-bff-portfolio/api/v1/portfolio"

    payload = {}

    headers = {
    'Accept': 'application/json',
    'Authorization': f'Bearer {BCS_API_ACCESS_KEY}'
    }

    response = requests.request("GET", url, headers=headers, data=payload)

    print(response.text)


def get_access_key():
    # Getting access key
    url = "https://be.broker.ru/trade-api-keycloak/realms/tradeapi/protocol/openid-connect/token"

    payload = {
    "client_id": "trade-api-write",
    "refresh_token": BCS_API_KEY,
    "grant_type": "refresh_token"
    }

    headers = {
    'Content-Type': 'application/x-www-form-urlencoded',
    'Accept': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    print(response.text)
    print(response.access_token)


if __name__ == "__main__":
    # 1. Configuration
    # BCS_API_KEY = "YOUR_ACTUAL_REFRESH_TOKEN_HERE"

    # IMPORTANT: Change to "trade-api-read" if your token is Read-Only
    CLIENT_ID = "trade-api-write" 

    # 2. Getting the Access Token
    auth_url = "https://be.broker.ru/trade-api-keycloak/realms/tradeapi/protocol/openid-connect/token"

    auth_payload = {
        "client_id": CLIENT_ID,
        "refresh_token": BCS_API_KEY,
        "grant_type": "refresh_token"
    }

    auth_headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }

    auth_response = requests.post(auth_url, headers=auth_headers, data=auth_payload)

    # Verify Auth request succeeded
    if auth_response.status_code != 200:
        print(f"Auth failed: {auth_response.status_code} - {auth_response.text}")
        exit()

    # Crucial step: Extract the actual token string from the JSON response
    tokens_json = auth_response.json()
    bcs_access_token = tokens_json.get("access_token")

    print("Access Token successfully generated.")

    # 3. Requesting Portfolio Data
    portfolio_url = "https://be.broker.ru/trade-api-bff-portfolio/api/v1/portfolio"

    portfolio_headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {bcs_access_token}'
    }

    # Keep payload empty but execute the request
    portfolio_response = requests.get(portfolio_url, headers=portfolio_headers)

    print("\nPortfolio Response Status:", portfolio_response.status_code)
    print("Portfolio Response Data:")
    print(portfolio_response.text)