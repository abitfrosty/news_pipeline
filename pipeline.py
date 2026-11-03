import os
import datetime
from data_ingestion import NewsIngestionPipeline
from helper import get_current_timestamp

def execute_pipeline_cycle():
    pipeline = NewsIngestionPipeline()
    pipeline.execute_ingestion_cycle()
    pipeline.execute_scraping_cycle()

if __name__ == "__main__":
    print(f"[{get_current_timestamp()}] Starting News Pipeline...")
    execute_pipeline_cycle()
    print(f"[{get_current_timestamp()}] News Pipeline Completed.")
