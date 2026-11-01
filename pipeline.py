import os
from datetime import datetime
from data_ingestion import NewsIngestionPipeline


def execute_pipeline_cycle():
    pipeline = NewsIngestionPipeline()
    #pipeline.execute_ingestion_cycle()
    pipeline.execute_scraping_cycle()

if __name__ == "__main__":
    print(f"[{datetime.now()}] Starting News Pipeline...")
    execute_pipeline_cycle()
    print(f"[{datetime.now()}] News Pipeline Completed.")
