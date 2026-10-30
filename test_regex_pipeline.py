import sqlite3
import re
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("DB_NAME")
# --- YOUR PIECE-BY-PIECE REGEX PATTERNS ---
HEADER_PAT = r"^[\s\w\[\]\·]+Last updated[\s\w\[\]\·]+ago\s+"
FOOTER_PAT = r"\s[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z]{1,63}\b(?:[-a-zA-Z]*)+([\s\·]+)(This summary)?[\s\S]+"

def clean_payload(raw_text: str) -> str:
    if not raw_text:
        return ""
    
    # Apply your header fix
    step1 = re.sub(HEADER_PAT, "", raw_text, flags=re.IGNORECASE)
    
    # Apply your footer fix
    step2 = re.sub(FOOTER_PAT, "", step1, flags=re.IGNORECASE)
    
    return step2.strip()

def run_pipeline_test(db_path: str, limit: int = 100):
    if not os.path.exists(db_path):
        print(f"[-] Database not found at: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Select sample rows where full_text is present to validate transformations
    cursor.execute("""
        SELECT id, title, full_text 
        FROM clstr_situations 
        WHERE full_text IS NOT NULL AND full_text != ''
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("[!] No records with full_text found to test.")
        return

    print(f"[*] Processing {len(rows)} samples for pattern validation...")
    
    # Generate an isolated HTML QA report for side-by-side verification
    report_filename = f"regex_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    
    with open(report_filename, "w", encoding="utf-8") as f:
        f.write("""
        <html>
        <head>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 40px; background: #f8f9fa; color: #333; }
                .card { background: white; padding: 25px; margin-bottom: 30px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
                h2 { color: #0066cc; margin-top: 0; font-size: 1.2rem; border-bottom: 2px solid #eee; padding-bottom: 8px;}
                .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
                pre { background: #f1f3f5; padding: 15px; border-radius: 5px; white-space: pre-wrap; word-break: break-all; font-size: 0.85rem; max-height: 300px; overflow-y: auto; border: 1px solid #e9ecef; }
                .cleaned pre { background: #ebfbee; border: 1px solid #c3fae8; }
                .meta { font-size: 0.8rem; color: #666; margin-bottom: 10px; }
            </style>
        </head>
        <body>
            <h1>clstr.news Regex Pipeline Validation Report</h1>
            <p>Review side-by-side transformations to confirm header/footer stripping did not slice core body text.</p>
        """)
        
        failures = 0
        for doc_id, title, raw in rows:
            cleaned = clean_payload(raw)
            
            # Diagnostic flag: checking if the cleaner stripped too much or left metadata behind
            anomaly_detected = False
            if "[SITUATION]" in cleaned or len(cleaned) < 50:
                anomaly_detected = True
                failures += 1
                
            f.write(f"""
            <div class="card" style="{ 'border-left: 5px solid #ff6b6b;' if anomaly_detected else 'border-left: 5px solid #2f9e44;' }">
                <h2>{title} <span style="font-size:0.8rem; color:#888;">(ID: {doc_id})</span></h2>
                { '<b style="color:#e03131;">[!] Potential Anomaly Detected</b>' if anomaly_detected else '' }
                <div class="grid">
                    <div>
                        <div class="meta">Raw Scraped Text Layer:</div>
                        <pre>{raw}</pre>
                    </div>
                    <div class="cleaned">
                        <div class="meta">Transformed Text (Ready for Tokenizer/DB):</div>
                        <pre>{cleaned}</pre>
                    </div>
                </div>
            </div>
            """)
            
        f.write("</body></html>")
    
    print(f"[+] Validation report built successfully: {report_filename}")
    print(f"[*] Total Anomalies / Empty yields caught: {failures} out of {len(rows)} samples.")

if __name__ == "__main__":
    # Point this to your real local development database path
    DB_FILE = DB_NAME
    run_pipeline_test(DB_FILE, limit=100)