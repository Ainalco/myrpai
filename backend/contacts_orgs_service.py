from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
import threading
import logging

import models
from database import SessionLocal

logger = logging.getLogger(__name__)


def trigger_org_dnc_cascade(org_id: int):
    """Async trigger"""
    thread = threading.Thread(target=run_dnc_cascade, args=(org_id,))
    thread.start()

    return f"job-{org_id}-{int(datetime.now().timestamp())}"


def run_dnc_cascade(org_id: int):
    db: Session = SessionLocal()

    try:
        org = db.query(models.ContactOrganization).filter(
            models.ContactOrganization.id == org_id
        ).first()

        if not org:
            return

        # --- PG LOCK ---
        try:
            db.execute(text(f"SELECT pg_advisory_xact_lock({org_id})"))
        except Exception:
            pass

        contacts = db.query(models.Contact).filter(
            models.Contact.contact_organization_id == org_id,
            models.Contact.deleted_at.is_(None),
        ).all()

        contact_ids = [c.id for c in contacts]

        # --- SET DNC ---
        db.query(models.Contact).filter(
            models.Contact.id.in_(contact_ids)
        ).update({"status": "do_not_contact"}, synchronize_session=False)

        # --- CANCEL EMAILS ---
        emails = db.query(models.EmailQueue).filter(
            models.EmailQueue.contact_id.in_(contact_ids),
            models.EmailQueue.status == "pending",
        ).all()

        for email in emails:
            email.status = "cancelled"
            email.metadata = {
                **(email.metadata or {}),
                "reason": "org_dnc"
            }

        # --- LOG ---
        for cid in contact_ids:
            db.add(models.ContactActivity(
                contact_id=cid,
                user_id=org.dnc_set_by,
                activity_type="org_dnc_applied",
                title="Organization marked as Do Not Contact",
                occurred_at=datetime.now(timezone.utc),
            ))

        org.dnc_propagation_status = "completed"

        db.commit()

    except Exception as e:
        logger.error(f"DNC cascade failed: {e}")
        org.dnc_propagation_status = "failed"
        db.commit()

    finally:
        db.close()
