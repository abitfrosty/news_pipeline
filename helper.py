import os
import re
import sqlite3
from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("DB_NAME")

def clean_clstr_payload(raw_text: str) -> str:
    if not raw_text:
        return ""

    # 1. Clear leading spaces and target the header directly
    clean_text = raw_text.strip()
    
    # Extract everything after the 'Last updated...' line down to the footer
    # Using an explicit multi-line negative lookahead to capture the actual body
    #header_pattern = r"^\[SITUATION\].*?Last updated[^\n]*\n"
    header_pattern = r"^[\s\w\[\]\·]+Last updated[\s\w\[\]\·]+ago\s+"
    clean_text = re.sub(header_pattern, "", clean_text, flags=re.DOTALL | re.IGNORECASE)
    
    # 2. Hardened footer removal
    # Matches the first occurrence of multiple website domains separated by dots/spaces
    #footer_pattern = r"\n\s*\b\w+\.[a-z]{2,6}(?:\s+·\s+[\w.-]+\.[a-z]{2,6})+.*$"
    footer_pattern = r"\s[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z]{1,63}\b(?:[-a-zA-Z]*)+([\s\·]+)(This summary)?[\s\S]+"
    clean_text = re.sub(footer_pattern, "", clean_text, flags=re.DOTALL)

    return clean_text
    # 1. Remove metadata header up to the last update timestamp
    # Matches '[SITUATION]' through to the end of the line containing 'Last updated...'
    clean_text = re.sub(r'^\[SITUATION\].*?Last updated[^\n]+\n?', '', raw_text, flags=re.DOTALL)
    
    # 2. Strip trailing domain tracking signatures and update counts
    # Looks for the characteristic sequence of multiple domain extensions separated by middle dots
    clean_text = re.sub(r'\b\w+\.[a-z]{2,3}(?:\s+·\s+\w+\.[a-z]{2,3})*.*This summary has been updated.*$', '', clean_text, flags=re.DOTALL)
    
    return clean_text.strip()

def trim_full_text():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA journal_mode = WAL;")
    cursor = conn.cursor()
    cursor.execute("SELECT full_text FROM clstr_situations WHERE id = ?", ("0128ee1f-5a15-46af-9ed0-695d01c3db22",))
    row = cursor.fetchone()
    
    full_text = None
    if row:
        full_text = row[0]

    print(full_text)
    print("======")
    print(clean_clstr_payload(full_text))


if __name__ == "__main__":
    print("Starting full text trimming...")
    trim_full_text()
