import os
import sqlite3
import requests
import re
import random
import time
import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Initialize the environment wrapper before setting global variables
load_dotenv()

# Production Configuration Variables
DB_NAME = os.getenv("DB_NAME")
DB_SCHEMA_PATH = os.getenv("DB_SCHEMA_PATH")
CLSTR_API_KEY = os.getenv("CLSTR_API_KEY")
CLSTR_URL = os.getenv("CLSTR_URL")
SUMMARY_THRESHOLD = int(os.getenv("SUMMARY_THRESHOLD"))
SIGNIFICANCE_THRESHOLD = int(os.getenv("SIGNIFICANCE_THRESHOLD"))
BATCH_SIZE_SQL_WRITE = int(os.getenv("BATCH_SIZE_SQL_WRITE"))

class NewsIngestionPipeline:
    def __init__(self, db_path: str = DB_NAME):
        self.db_path = db_path
        # Compile your proven regular expressions once at initialization for maximum velocity
        self.header_pattern = re.compile(r"^[\s\w\[\]\·]+Last updated[\s\w\[\]\·]+ago\s+", re.IGNORECASE)
        self.footer_pattern = re.compile(
            r"\s[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z]{1,63}\b(?:[-a-zA-Z]*)+([\s\·]+)(This summary)?[\s\S]+", 
            re.IGNORECASE
        )
        self.footer_pattern2 = re.compile(r"(\s\w+\s\·\s)+(This summary)?[\s\S]+", re.IGNORECASE)
        self._init_db()

    def _get_connection(self):
        """Establishes connection and dynamically injects connection-scoped performance settings."""
        conn = sqlite3.connect(self.db_path)
        # WAL mode is database-scoped (persists in header), but synchronous MUST be set per session
        conn.execute("PRAGMA synchronous = NORMAL;")
        # Ensure WAL mode is active for concurrent script access
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_db(self):
        """Ensures directories exist and page_size optimizations are forced via vacuum if necessary."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # If database is fresh, execute initial schema setup
        if not os.path.exists(self.db_path) or os.path.getsize(self.db_path) == 0:
            conn = self._get_connection()
            # page_size must be declared BEFORE tables are created
            conn.execute("PRAGMA page_size = 4096;")
            
            # Read and execute your static structural template schema.sql
            with open(DB_SCHEMA_PATH, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
            conn.close()

    def _save_situation_to_sql(self, cursor, situation):
        """Saves optimized structural features. Bypasses the raw JSON dump entirely."""
        cursor.execute("""
            INSERT INTO clstr_situations (
                id, slug, title, summary_preview, category, significance_score, first_seen, last_updated, ingested_at, url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                slug=COALESCE(excluded.slug, clstr_situations.slug),
                title=COALESCE(excluded.title, clstr_situations.title),
                summary_preview=COALESCE(excluded.summary_preview, clstr_situations.summary_preview),
                category=COALESCE(excluded.category, clstr_situations.category),
                significance_score=COALESCE(excluded.significance_score, clstr_situations.significance_score),
                first_seen=COALESCE(excluded.first_seen, clstr_situations.first_seen),
                last_updated=COALESCE(excluded.last_updated, clstr_situations.last_updated),
                ingested_at=COALESCE(clstr_situations.ingested_at, excluded.ingested_at),
                url=COALESCE(excluded.url, clstr_situations.url)
        """, (
            situation.get("id"),
            situation.get("slug"),
            situation.get("title"),
            situation.get("summary_preview"),
            situation.get("category"),
            situation.get("significance_score"),
            situation.get("first_seen"),
            situation.get("last_updated"),
            self.get_current_timestamp(),
            situation.get("url")
        ))

    def _save_full_text(self, situation_id: str, raw_full_text: str):
        """
        Saves cleaned text into the time-series model.
        Captures historical processing metrics to prevent temporal look-ahead leakage.
        """
        cleaned_text = self.clean_payload(raw_full_text)
        if not cleaned_text:
            print(f"[Info] No valid text to save for situation ID {situation_id}. Skipping database update.")
            return
        current_time = self.get_current_timestamp()

        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # We explicitly update full_text and store the ingestion checkpoint
            cursor.execute("""
                UPDATE clstr_situations 
                SET full_text = ?, 
                    ingested_at = ?
                WHERE id = ?
            """, (cleaned_text, current_time, situation_id))
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            print(f"[-] Database transaction failure on ID {situation_id}: {e}")
        finally:
            conn.close()

    def get_current_timestamp(self):
        """Returns the current UTC timestamp in %Y-%m-%d %H:%M:%S format."""
        return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

    def update_clstr_request_url(self, params, endpoint):
        """Constructs the request URL with query parameters for clstr.news API."""
        if params.get("cursor"):
            return f"{CLSTR_URL}{endpoint}?cursor={params['cursor']}"
        query_string = "&".join(f"{key}={value}" for key, value in params.items())
        return f"{CLSTR_URL}{endpoint}?{query_string}"

    def scrape_full_text(self, url: str) -> str:
        """Tier 2: Connects directly to the source link to extract unredacted text for free."""
        if not url:
            return ""
        try:
            # Standard browser headers to prevent site blocks
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = requests.get(url, headers=headers, timeout=8)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Target the specific container holding the overview text
                main_container = soup.find('div', class_='mb-2')
                
                if main_container:
                    # Grab paragraph tags exclusively from inside this container
                    paragraphs = main_container.find_all('p')
                    full_article = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text()) > 30])
                    return full_article if len(full_article) > SUMMARY_THRESHOLD else ""
                    
        except Exception as e:
            print(f"[Scraper Skip] Failed to extract text from {url}: {e}")
        return ""

    def clean_payload(self, raw_text: str) -> str:
        """Applies your fine-tuned regular expressions step-by-step."""
        if not raw_text:
            return ""
        # 1. Strip Header
        step1 = self.header_pattern.sub("", raw_text)
        # 2. Strip Footer Matrix Block completely
        step2 = self.footer_pattern.sub("", step1)
        # 3. Strip additional footer content
        step3 = self.footer_pattern2.sub("", step2)
        return step3.strip()

    def execute_ingestion_cycle(self):
        print(f"[{self.get_current_timestamp()}] Ingestion Cycle Started.")
        headers = {"Authorization": f"Bearer {CLSTR_API_KEY}", "Content-Type": "application/json"}
        params = {"days": 7, "limit": 20, "sort": "recent"}
        endpoint = "situations"

        current_cursor = None
        total_processed = 0
        conn = self._get_connection()
        db_cursor = conn.cursor()
        
        while True:
            if current_cursor:
                params["cursor"] = current_cursor
                
            try:
                url = self.update_clstr_request_url(params, endpoint)
                response = requests.get(url, headers=headers, timeout=15)
                if response.status_code != 200:
                    print(f"[HTTP Error] Status {response.status_code}")
                    break
                    
                payload = response.json()
                situations_list = payload.get("data", [])
                
                if not situations_list:
                    break
                    
                for situation in situations_list:
                    self._save_situation_to_sql(db_cursor, situation)
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
        print(f"[{self.get_current_timestamp()}] Ingestion cycle concluded. Processed records: {total_processed}\n")

    def execute_scraping_cycle(self):
        """
        Saves cleaned text into the time-series model.
        Captures historical processing metrics to prevent temporal look-ahead leakage.
        """
        print(f"[{self.get_current_timestamp()}] Scraping cycle started.")
        
        total_processed = 0
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_situations_missing_text 
                ON clstr_situations(significance_score) 
                WHERE full_text IS NULL OR full_text = '';
            """)
            cursor.execute("""
                SELECT id, url FROM clstr_situations 
                WHERE full_text IS NULL OR full_text = '' 
                ORDER BY significance_score DESC 
                --LIMIT 10
            """)
            rows = cursor.fetchall()
            
            # 1. Separate Network Scraping from Database Transactions
            # We scrape everything first (or in chunks) so we don't hold DB locks during network lag
            scraped_payloads = []
            
            for row in rows:
                id, url = row[0], row[1]
                if not url:
                    continue
                    
                print(f" -> Scraping source asset: {url[:40]}...")
                full_text = self.scrape_full_text(url)
                cleaned_text = self.clean_payload(full_text)
                
                if cleaned_text:
                    scraped_payloads.append((cleaned_text, self.get_current_timestamp(), id))
                else:
                    print(f"[Info] No valid text extracted for ID {id}. Skipping this record.")
                    
                # Defensive courtesy delay happens safely outside of DB transactions
                time.sleep(random.uniform(0.2, 2) + random.uniform(0.2, 2) + 1)

            # 2. Batch Write to the Database
            # Now that we have the data, we open a single transaction and write in fast batches
            
            # Disable autocommit explicitly by starting a transaction
            cursor.execute("BEGIN TRANSACTION;")
            
            for index, payload in enumerate(scraped_payloads):
                try:
                    cursor.execute("""
                        UPDATE clstr_situations 
                        SET full_text = ?, 
                            ingested_at = ?
                        WHERE id = ?
                    """, payload)
                    
                    total_processed += 1
                    
                    # Commit every 10 items
                    if (index + 1) % BATCH_SIZE_SQL_WRITE == 0:
                        conn.commit()
                        cursor.execute("BEGIN TRANSACTION;") # Re-open for the next batch
                        
                except sqlite3.Error as e:
                    # If a specific update fails, rollback just this batch
                    conn.rollback()
                    print(f"[-] Batch failure around ID {payload[2]}: {e}")
                    # Re-open transaction to allow subsequent batches to try saving
                    cursor.execute("BEGIN TRANSACTION;") 
                    
            # Final commit for any remaining items left in the last partial batch
            conn.commit()

        except sqlite3.Error as e:
            print(f"[-] General Database error: {e}")
        finally:
            conn.close()
        print(f"[{self.get_current_timestamp()}] Scraping cycle concluded. Processed records: {total_processed}\n")
