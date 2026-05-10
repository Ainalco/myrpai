#!/usr/bin/env python3
"""
Migration script to run Alembic migrations automatically
"""
import os
import sys
import time
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

def wait_for_db(database_url: str, max_retries: int = 30) -> bool:
    """Wait for database to be ready"""
    print("Waiting for database to be ready...")
    
    for i in range(max_retries):
        try:
            engine = create_engine(database_url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("Database is ready!")
            return True
        except OperationalError as e:
            print(f"Database not ready yet (attempt {i+1}/{max_retries}): {e}")
            time.sleep(2)
        except Exception as e:
            print(f"Unexpected error connecting to database: {e}")
            time.sleep(2)
    
    print("Failed to connect to database after all retries")
    return False

def run_migrations():
    """Run Alembic migrations"""
    # Get database URL from environment
    database_url = os.getenv(
        "DATABASE_URL", 
        "postgresql://workflow_user:workflow_pass@postgres:5432/workflow_platform"
    )
    
    # Wait for database to be ready
    if not wait_for_db(database_url):
        sys.exit(1)
    
    # Run migrations
    try:
        print("Running database migrations...")
        
        # Create Alembic config
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", database_url)
        
        # Run migrations
        command.upgrade(alembic_cfg, "head")
        print("Migrations completed successfully!")
        
    except Exception as e:
        print(f"Error running migrations: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migrations()