"""
Email Queue Background Worker

This worker periodically checks for pending emails in the queue
and sends them via SMTP when their scheduled time arrives.

Usage:
    python email_worker.py
"""

import asyncio
import logging
import sys
from datetime import datetime

from database import SessionLocal
from email_service import process_email_queue

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
POLL_INTERVAL_SECONDS = 60  # Check every 60 seconds
PROCESS_BATCH_SIZE = 50     # Process up to 50 emails per batch


async def email_worker_loop():
    """
    Main worker loop that processes the email queue periodically.
    """
    logger.info("Email worker started")
    logger.info(f"Poll interval: {POLL_INTERVAL_SECONDS} seconds")
    logger.info(f"Batch size: {PROCESS_BATCH_SIZE} emails")

    while True:
        try:
            logger.info(f"[{datetime.utcnow().isoformat()}] Checking email queue...")

            # Create a new database session for each cycle
            db = SessionLocal()

            try:
                # Process the email queue
                result = await process_email_queue(db)

                if result.get("success"):
                    stats = result.get("stats", {})
                    if stats.get("processed", 0) > 0:
                        logger.info(
                            f"Processed {stats['processed']} emails: "
                            f"{stats['sent']} sent, {stats['failed']} failed"
                        )

                        # Log any errors
                        for error in stats.get("errors", []):
                            logger.error(f"Email {error['email_id']}: {error['error']}")
                    else:
                        logger.debug("No emails to process")
                else:
                    logger.error(f"Email queue processing failed: {result.get('error')}")

            except Exception as e:
                logger.error(f"Error during email processing: {str(e)}", exc_info=True)

            finally:
                # Always close the database session
                db.close()

        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
            break

        except Exception as e:
            logger.error(f"Unexpected error in worker loop: {str(e)}", exc_info=True)

        # Wait before next poll
        logger.debug(f"Sleeping for {POLL_INTERVAL_SECONDS} seconds...")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    logger.info("Email worker stopped")


def main():
    """
    Entry point for the email worker.
    """
    try:
        # Run the async worker loop
        asyncio.run(email_worker_loop())
    except KeyboardInterrupt:
        logger.info("Email worker interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error in email worker: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
