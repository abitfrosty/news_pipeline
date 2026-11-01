import os
import re
import sqlite3
from dotenv import load_dotenv

from data_ingestion import NewsIngestionPipeline

load_dotenv()

DB_NAME = os.getenv("DB_NAME")

def clean_clstr_payload(raw_text: str) -> str:
    if not raw_text:
        return ""

    # 1. Clear leading spaces and target the header directly
    clean_text = raw_text.strip()
    
    # Extract everything after the 'Last updated...' line down to the footer
    # Using an explicit multi-line negative lookahead to capture the actual body
    header_pattern = r"^[\s\w\[\]\·]+Last updated[\s\w\[\]\·]+ago\s+"
    clean_text = re.sub(header_pattern, "", clean_text, flags=re.DOTALL | re.IGNORECASE)
    
    # 2. Hardened footer removal
    # Matches the first occurrence of multiple website domains separated by dots/spaces
    footer_pattern = r"\s[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z]{1,63}\b(?:[-a-zA-Z]*)+([\s\·]+)(This summary)?[\s\S]+"
    clean_text = re.sub(footer_pattern, "", clean_text, flags=re.DOTALL)

    return clean_text

def trim_full_text():
    data_ingestion = NewsIngestionPipeline()
    conn = data_ingestion._get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, full_text FROM clstr_situations WHERE NOT full_text='' AND full_text IS NOT NULL;")
        rows = cursor.fetchall()
        for row in rows:
            print(f"Trimming full_text for id: {row[0]}")
            full_text = row[1]
            trimmed_text = data_ingestion.clean_payload(full_text)
            cursor.execute("UPDATE clstr_situations SET full_text=? WHERE id=?", (trimmed_text, row[0]))
        conn.commit()
    except sqlite3.Error as e:
        print(f"[-] Database error: {e}")
    finally:
        conn.close()
    

if __name__ == "__main__":
    print("Starting full text trimming...")
    trim_full_text()
    print("Full text trimming completed.")
