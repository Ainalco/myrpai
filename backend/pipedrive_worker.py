"""
Pipedrive CRM Sync Background Worker

Periodically syncs contacts with Pipedrive — links persons, imports deals,
detects stage changes, and logs activities on the contact timeline.

Uses smart interval logic:
  - Never-synced contacts: immediate
  - Active contacts (open deals / recent activity): every 15 min
  - Dormant contacts: every 6 hours

Usage:
    python pipedrive_worker.py
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

from database import SessionLocal
import models

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Configuration
POLL_INTERVAL_SECONDS = int(os.getenv("PIPEDRIVE_SYNC_INTERVAL", "300"))  # Default 5 minutes
BATCH_SIZE = 30  # Max contacts per user per cycle


async def pipedrive_worker_loop():
    """
    Main worker loop that syncs contacts with Pipedrive periodically.
    """
    logger.info("Pipedrive sync worker started")
    logger.info(f"Poll interval: {POLL_INTERVAL_SECONDS} seconds")
    logger.info(f"Batch size: {BATCH_SIZE} contacts per user per cycle")

    while True:
        try:
            logger.info(f"[{datetime.now(timezone.utc).isoformat()}] Starting Pipedrive sync cycle...")

            db = SessionLocal()

            try:
                # Find all users with an active Pipedrive API key
                api_keys = db.query(models.ApiKey).filter(
                    models.ApiKey.service_name == "pipedrive",
                    models.ApiKey.is_active == True,
                ).all()

                if not api_keys:
                    logger.debug("No users with Pipedrive API keys configured")
                else:
                    logger.info(f"Found {len(api_keys)} users with Pipedrive keys")

                    for api_key_record in api_keys:
                        user_id = api_key_record.user_id
                        try:
                            from pipedrive_sync import sync_all_contacts_pipedrive
                            result = await sync_all_contacts_pipedrive(db, user_id)

                            if result.get("success"):
                                synced = result.get("contactsSynced", 0)
                                if synced > 0:
                                    logger.info(
                                        f"User {user_id}: synced {synced} contacts, "
                                        f"{result.get('personsFound', 0)} persons found, "
                                        f"{result.get('dealsCreated', 0)} deals created, "
                                        f"{result.get('dealsUpdated', 0)} deals updated"
                                    )
                                else:
                                    logger.debug(f"User {user_id}: no contacts due for sync")
                            else:
                                logger.warning(f"User {user_id}: sync failed — {result.get('error')}")

                        except Exception as e:
                            logger.error(f"Error syncing user {user_id}: {str(e)}", exc_info=True)
                            continue

            except Exception as e:
                logger.error(f"Error during sync cycle: {str(e)}", exc_info=True)

            finally:
                db.close()

        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
            break

        except Exception as e:
            logger.error(f"Unexpected error in worker loop: {str(e)}", exc_info=True)

        logger.debug(f"Sleeping for {POLL_INTERVAL_SECONDS} seconds...")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    logger.info("Pipedrive sync worker stopped")


def main():
    """Entry point for the Pipedrive sync worker."""
    try:
        asyncio.run(pipedrive_worker_loop())
    except KeyboardInterrupt:
        logger.info("Pipedrive sync worker interrupted by user")


if __name__ == "__main__":
    main()
