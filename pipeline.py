import os
import sqlite3
import requests
import json
import time
from datetime import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from random import random
import re

# Initialize the environment wrapper before setting global variables
load_dotenv()

# Production Configuration Variables
DB_NAME = os.getenv("DB_NAME")
DB_SCHEMA_PATH = os.getenv("DB_SCHEMA_PATH")
CLSTR_API_KEY = os.getenv("CLSTR_API_KEY")
CLSTR_URL = "https://api.clstr.news/v1/"
SUMMARY_THRESHOLD = 220  # Minimum character count to trigger full-text scraping
SIGNIFICANCE_THRESHOLD = 7  # Minimum significance score to consider for scraping

def init_database():
    """Builds a robust, time-series storage schema for clstr.news profiles."""
    with open(DB_SCHEMA_PATH, "r") as f:
        schema = f.read()
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.executescript(schema)
    conn.close()
    
    """Initializes a highly optimized database structure with minimal disk footprint."""
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Enable Write-Ahead Logging to prevent disk fragmentation
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = NORMAL;")
    
    # Clean structural table designed for machine learning features
    cursor.execute(""""""
        CREATE TABLE IF NOT EXISTS clstr_situations (
            id TEXT PRIMARY KEY,
            slug TEXT,
            title TEXT NOT NULL,
            summary_preview TEXT,    -- Stays as fallback
            full_text TEXT,          -- Bypasses the $29 paywall for free
            category TEXT,
            significance_score INTEGER,
            first_seen TIMESTAMP,
            last_updated TIMESTAMP,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            url TEXT            
        )
    """""")
    conn.commit()
    conn.close()
    """

def clean_clstr_payload(raw_text: str) -> str:
    if not raw_text:
        return ""
    
    # 1. Remove metadata header up to the last update timestamp
    # Matches '[SITUATION]' through to the end of the line containing 'Last updated...'
    clean_text = re.sub(r'^\[SITUATION\].*?Last updated[^\n]+\n?', '', raw_text, flags=re.DOTALL)
    
    # 2. Strip trailing domain tracking signatures and update counts
    # Looks for the characteristic sequence of multiple domain extensions separated by middle dots
    clean_text = re.sub(r'\b\w+\.[a-z]{2,3}(?:\s+·\s+\w+\.[a-z]{2,3})*.*This summary has been updated.*$', '', clean_text, flags=re.DOTALL)
    
    return clean_text.strip()

def scrape_full_text(url):
    """Tier 2: Connects directly to the source link to extract unredacted text for free."""
    if not url:
        return None
    try:
        # Standard browser headers to prevent site blocks
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Smart extraction: Grabs text inside paragraph tags, excluding ads
            paragraphs = soup.find_all('p')
            full_article = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text()) > 30])
            full_article = clean_clstr_payload(full_article)
            return full_article if len(full_article) > SUMMARY_THRESHOLD else None
    except Exception as e:
        print(f"[Scraper Skip] Failed to extract text from {url}: {e}")
    return None

def save_situation_to_sql(cursor, situation):
    """Saves optimized structural features. Bypasses the raw JSON dump entirely."""
    situation_id = situation.get("id")
    url = situation.get("url")
    
    # Check if the situation already exists in our local vault
    cursor.execute("SELECT full_text FROM clstr_situations WHERE id = ?", (situation_id,))
    row = cursor.fetchone()
    
    full_text = None
    if row:
        full_text = row[0]
    
    # If it's a new entry or missing full text, execute the Tier-2 scraper
    if not full_text and len(situation.get("summary_preview", "")) >= SUMMARY_THRESHOLD-1 and situation.get("significance_score", 0) >= SIGNIFICANCE_THRESHOLD:
        print(f" -> Scraping source asset: {situation.get('title')[:40]}...")
        full_text = scrape_full_text(url)
        time.sleep(random()*2 + random()*2 + 1)  # Defensive courtesy delay to avoid hitting sites too fast
        
    cursor.execute("""
        INSERT INTO clstr_situations (
            id, slug, title, summary_preview, full_text, category, significance_score, first_seen, last_updated, ingested_at, url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            full_text=COALESCE(excluded.full_text, clstr_situations.full_text),
            last_updated=excluded.last_updated
    """, (
        situation_id,
        situation.get("slug"),
        situation.get("title"),
        situation.get("summary_preview"),
        full_text,
        situation.get("category"),
        situation.get("significance_score"),
        situation.get("first_seen"),
        situation.get("last_updated"),
        datetime.isoformat(datetime.now()),
        url
    ))

def update_clstr_request_url(params, endpoint):
    """Constructs the request URL with query parameters for clstr.news API."""
    if params.get("cursor"):
        return f"{CLSTR_URL}{endpoint}?cursor={params['cursor']}"
    query_string = "&".join(f"{key}={value}" for key, value in params.items())
    return f"{CLSTR_URL}{endpoint}?{query_string}"

def execute_pipeline_cycle():
    print(f"[{datetime.now()}] Ingestion & Scraping Cycle Started.")
    headers = {"Authorization": f"Bearer {CLSTR_API_KEY}", "Content-Type": "application/json"}
    params = {"days": 1, "limit": 1, "sort": "recent"}
    endpoint = "situations"

    current_cursor = None
    total_processed = 0
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA journal_mode = WAL;")
    db_cursor = conn.cursor()
    
    while True:
        if current_cursor:
            params["cursor"] = current_cursor
            
        try:
            url = update_clstr_request_url(params, endpoint)
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                print(f"[HTTP Error] Status {response.status_code}")
                break
                
            payload = response.json()
            situations_list = payload.get("data", [])
            
            if not situations_list:
                break
                
            for situation in situations_list:
                save_situation_to_sql(db_cursor, situation)
                total_processed += 1
                
            conn.commit()
            
            current_cursor = payload.get("next_cursor")
            if not current_cursor:
                break
                
            time.sleep(1)
        except Exception as error:
            print(f"[Error] Pipeline failure: {error}")
            break
            
    conn.close()
    print(f"[{datetime.now()}] Cycle Concluded. Processed records: {total_processed}\n")

if __name__ == "__main__":
    init_database()
    execute_pipeline_cycle()
