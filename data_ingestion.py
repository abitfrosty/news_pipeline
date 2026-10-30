import sqlite3
import re
import os
from datetime import datetime
from dotenv import load_dotenv

# Initialize the environment wrapper before setting global variables
load_dotenv()

# Production Configuration Variables
DB_NAME = os.getenv("DB_NAME")
DB_SCHEMA_PATH = os.getenv("DB_SCHEMA_PATH")

class NewsIngestionPipeline:
    def __init__(self, db_path: str = DB_NAME):
        self.db_path = db_path
        # Compile your proven regular expressions once at initialization for maximum velocity
        self.header_pattern = re.compile(r"^[\s\w\[\]\·]+Last updated[\s\w\[\]\·]+ago\s+", re.IGNORECASE)
        self.footer_pattern = re.compile(
            r"\s[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z]{1,63}\b(?:[-a-zA-Z]*)+([\s\·]+)(This summary)?[\s\S]+", 
            re.IGNORECASE
        )
        self._init_db()

    def _get_connection(self):
        """Establishes connection and dynamically injects connection-scoped performance settings."""
        conn = sqlite3.connect(self.db_path)
        # WAL mode is database-scoped (persists in header), but synchronous MUST be set per session
        conn.execute("PRAGMA synchronous = NORMAL;")
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

    def clean_payload(self, raw_text: str) -> str:
        """Applies your fine-tuned regular expressions step-by-step."""
        if not raw_text:
            return ""
        # 1. Strip Header
        step1 = self.header_pattern.sub("", raw_text)
        # 2. Strip Footer Matrix Block completely
        step2 = self.footer_pattern.sub("", step1)
        return step2.strip()

    def save_full_text(self, situation_id: str, raw_full_text: str):
        """
        Saves cleaned text into the time-series model.
        Captures historical processing metrics to prevent temporal look-ahead leakage.
        """
        cleaned_text = self.clean_payload(raw_full_text)
        current_time = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

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
