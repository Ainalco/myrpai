# Pipedrive Background Sync Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a background worker that continuously syncs Pipedrive persons and deals into the contact system, with manual sync endpoints for on-demand use.

**Architecture:** Standalone `pipedrive_worker.py` runs every 5 minutes, uses smart interval logic to decide which contacts need syncing, calls existing `pipedrive_service.py` functions for Pipedrive API access, upserts `ContactDeal` records and logs activities. Same sync function is exposed via `POST /contacts/{id}/sync-crm` for manual triggers.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, httpx (async), Alembic

**Spec:** `docs/superpowers/specs/2026-03-31-pipedrive-sync-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/alembic/versions/028_add_crm_synced_at.py` | CREATE | Migration: add `crm_synced_at` column to contacts |
| `backend/models.py` | MODIFY (line ~355) | Add `crm_synced_at` column to Contact model |
| `backend/pipedrive_sync.py` | CREATE | Shared sync logic: sync single contact, smart interval query, deal upsert |
| `backend/pipedrive_worker.py` | CREATE | Standalone background worker process |
| `backend/contacts.py` | MODIFY | Add 2 manual sync endpoints |

---

## Task 1: Migration 028 — Add `crm_synced_at` to contacts

**Files:**
- Create: `backend/alembic/versions/028_add_crm_synced_at.py`
- Modify: `backend/models.py`

- [ ] **Step 1: Write migration 028**

Create `backend/alembic/versions/028_add_crm_synced_at.py`:

```python
"""Add crm_synced_at to contacts for tracking Pipedrive sync freshness

Revision ID: 028_add_crm_synced_at
Revises: 027_add_contact_system
"""
from alembic import op
import sqlalchemy as sa

revision = "028_add_crm_synced_at"
down_revision = "027_add_contact_system"


def upgrade():
    op.add_column("contacts", sa.Column("crm_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_contacts_crm_synced_at", "contacts", ["crm_synced_at"])


def downgrade():
    op.drop_index("ix_contacts_crm_synced_at", "contacts")
    op.drop_column("contacts", "crm_synced_at")
```

- [ ] **Step 2: Add column to Contact model**

In `backend/models.py`, in the Contact class, add after the `deleted_at` line (currently line 355):

```python
    crm_synced_at = Column(DateTime(timezone=True))
```

- [ ] **Step 3: Verify models load**

```bash
cd /home/tauhid/code/aibot2/backend
python -c "import models; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/028_add_crm_synced_at.py backend/models.py
git commit -m "feat: add migration 028 — crm_synced_at on contacts for Pipedrive sync tracking"
```

---

## Task 2: Pipedrive Sync Service

**Files:**
- Create: `backend/pipedrive_sync.py`

- [ ] **Step 1: Create pipedrive_sync.py**

```python
"""
Pipedrive CRM sync for the contact system.
Syncs persons and deals from Pipedrive into contact_deals and updates contact/org metadata.

Used by:
  - pipedrive_worker.py (background sync every 5 min)
  - contacts.py (manual POST /contacts/{id}/sync-crm endpoint)
"""
import httpx
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import or_, and_, func
from datetime import datetime, timedelta
import logging

import models
from contacts_service import log_activity, update_contact_stats

logger = logging.getLogger(__name__)

PIPEDRIVE_API_BASE = "https://api.pipedrive.com/v1"

# Smart interval thresholds
INTERVAL_ACTIVE = timedelta(minutes=15)   # Contacts with open deals or recent activity
INTERVAL_DORMANT = timedelta(hours=6)     # Everything else
ACTIVE_WINDOW = timedelta(hours=48)       # "Recently active" = activity within 48h


async def _get_api_key(db: Session, user_id: int) -> Optional[str]:
    """Get user's Pipedrive API key from encrypted storage."""
    from pipedrive_service import get_pipedrive_api_key
    return await get_pipedrive_api_key(db, user_id)


async def _fetch_person_deals(api_key: str, person_id: int) -> List[dict]:
    """Fetch ALL deals for a Pipedrive person (paginated)."""
    all_deals = []
    start = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            response = await client.get(
                f"{PIPEDRIVE_API_BASE}/persons/{person_id}/deals",
                params={
                    "api_token": api_key,
                    "status": "all_not_deleted",
                    "start": start,
                    "limit": 100,
                },
            )
            response.raise_for_status()
            data = response.json()

            items = data.get("data") or []
            all_deals.extend(items)

            pagination = data.get("additional_data", {}).get("pagination", {})
            if pagination.get("more_items_in_collection"):
                start = pagination.get("next_start", start + 100)
            else:
                break

    return all_deals


async def _get_stage_map(db: Session, user_id: int) -> Dict[str, str]:
    """Get Pipedrive stage_id → stage_name mapping (cached 24h in pipedrive_service)."""
    from pipedrive_service import get_deal_stages
    result = await get_deal_stages(db, user_id)
    if result.get("success"):
        return result.get("stages", {})
    return {}


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse Pipedrive date string (YYYY-MM-DD) into datetime."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _upsert_deal(
    db: Session,
    user_id: int,
    contact: models.Contact,
    deal_data: dict,
    stage_map: Dict[str, str],
) -> Dict[str, str]:
    """
    Create or update a single ContactDeal from Pipedrive deal data.
    Returns {"action": "created"/"updated"/"unchanged", "title": str, "old_stage": str|None, "new_stage": str|None}
    """
    external_deal_id = str(deal_data.get("id"))
    title = deal_data.get("title", "Untitled Deal")
    status = deal_data.get("status", "open")  # open, won, lost
    stage_id = str(deal_data.get("stage_id", ""))
    stage_name = stage_map.get(stage_id, f"Stage {stage_id}")
    value = deal_data.get("value")
    if value is not None:
        try:
            value = float(value)
        except (ValueError, TypeError):
            value = None
    currency = deal_data.get("currency", "USD")
    expected_close = _parse_date(deal_data.get("expected_close_date"))

    # Lookup existing deal
    existing = db.query(models.ContactDeal).filter(
        models.ContactDeal.contact_id == contact.id,
        models.ContactDeal.external_deal_id == external_deal_id,
        models.ContactDeal.crm_provider == "pipedrive",
    ).first()

    if existing:
        old_stage = existing.stage_name
        old_status = existing.status
        changed = False

        if existing.title != title:
            existing.title = title
            changed = True
        if existing.status != status:
            existing.status = status
            changed = True
        if existing.stage_name != stage_name:
            existing.stage_name = stage_name
            changed = True
        if existing.value != value:
            existing.value = value
            changed = True
        if existing.currency != currency:
            existing.currency = currency
            changed = True
        if existing.expected_close_date != expected_close:
            existing.expected_close_date = expected_close
            changed = True

        if changed:
            db.flush()

            action = "updated"
            # Determine what kind of change to log
            if old_stage != stage_name and old_stage and stage_name:
                return {"action": action, "title": title, "change": "stage", "old_stage": old_stage, "new_stage": stage_name}
            elif old_status != status:
                return {"action": action, "title": title, "change": "status", "old_status": old_status, "new_status": status}
            else:
                return {"action": action, "title": title, "change": "fields"}
        else:
            return {"action": "unchanged", "title": title}

    else:
        # Create new ContactDeal
        new_deal = models.ContactDeal(
            contact_id=contact.id,
            user_id=user_id,
            contact_organization_id=contact.contact_organization_id,
            external_deal_id=external_deal_id,
            crm_provider="pipedrive",
            title=title,
            status=status,
            stage_name=stage_name,
            value=value,
            expected_close_date=expected_close,
            currency=currency,
        )
        db.add(new_deal)
        db.flush()
        return {"action": "created", "title": title, "new_stage": stage_name, "deal_id": new_deal.id}


async def sync_contact_pipedrive(
    db: Session,
    user_id: int,
    contact_id: int,
) -> Dict[str, Any]:
    """
    Sync a single contact with Pipedrive.
    1. Find Pipedrive person by email(s)
    2. Link external_person_id
    3. Link Pipedrive org to ContactOrganization
    4. Fetch all deals → upsert ContactDeal rows
    5. Log activities for new/changed deals
    6. Update stats
    7. Set crm_synced_at

    Returns sync result dict.
    """
    # Load contact with emails
    contact = db.query(models.Contact).options(
        selectinload(models.Contact.contact_emails),
    ).filter(
        models.Contact.id == contact_id,
        models.Contact.user_id == user_id,
        models.Contact.deleted_at.is_(None),
    ).first()

    if not contact:
        return {"success": False, "error": "Contact not found"}

    # Get Pipedrive API key
    api_key = await _get_api_key(db, user_id)
    if not api_key:
        return {"success": False, "error": "Pipedrive API key not configured"}

    now = datetime.utcnow()
    result = {
        "success": True,
        "personFound": False,
        "externalPersonId": None,
        "dealsTotal": 0,
        "dealsCreated": 0,
        "dealsUpdated": 0,
        "orgLinked": False,
        "orgName": None,
    }

    # --- Step 1: Find Pipedrive person by email(s) ---
    from pipedrive_service import find_person_by_email

    emails = [ce.email for ce in (contact.contact_emails or [])]
    if not emails:
        emails = [contact.email]

    person = None
    person_id = None
    for email in emails:
        search_result = await find_person_by_email(db, user_id, email)
        if search_result.get("found"):
            person = search_result.get("person", {})
            person_id = search_result.get("person_id")
            break

    if not person or not person_id:
        # Person not found — set crm_synced_at so we don't re-check every 5 min
        contact.crm_synced_at = now
        db.commit()
        result["personFound"] = False
        return result

    result["personFound"] = True
    result["externalPersonId"] = str(person_id)

    # --- Step 2: Link person ---
    contact.external_person_id = str(person_id)
    contact.crm_provider = "pipedrive"

    # --- Step 3: Link Pipedrive org ---
    pipedrive_org = person.get("organization") or {}
    pipedrive_org_id = pipedrive_org.get("id") if isinstance(pipedrive_org, dict) else None
    pipedrive_org_name = pipedrive_org.get("name") if isinstance(pipedrive_org, dict) else None

    if pipedrive_org_id and contact.contact_organization_id:
        org = db.query(models.ContactOrganization).filter(
            models.ContactOrganization.id == contact.contact_organization_id,
        ).first()
        if org:
            org.external_org_id = str(pipedrive_org_id)
            org.crm_provider = "pipedrive"
            if pipedrive_org_name and org.name != pipedrive_org_name:
                org.name = pipedrive_org_name
            result["orgLinked"] = True
            result["orgName"] = org.name

    # --- Step 4: Fetch all deals for person ---
    try:
        pipedrive_deals = await _fetch_person_deals(api_key, person_id)
    except Exception as e:
        logger.error(f"Failed to fetch deals for person {person_id}: {e}")
        contact.crm_synced_at = now
        db.commit()
        result["error"] = f"Failed to fetch deals: {str(e)}"
        return result

    # --- Step 5: Get stage mapping ---
    stage_map = await _get_stage_map(db, user_id)

    # --- Step 6: Upsert deals ---
    for deal_data in pipedrive_deals:
        try:
            upsert_result = _upsert_deal(db, user_id, contact, deal_data, stage_map)
            action = upsert_result.get("action")
            title = upsert_result.get("title", "")

            if action == "created":
                result["dealsCreated"] += 1
                log_activity(
                    db=db,
                    user_id=user_id,
                    contact_id=contact_id,
                    activity_type="deal_stage_change",
                    direction="internal",
                    source_type="crm_sync",
                    source_id=f"pipedrive_deal_{deal_data.get('id')}_created",
                    deal_id=upsert_result.get("deal_id"),
                    summary=f"New deal synced: {title} at {upsert_result.get('new_stage', 'Unknown')}",
                    title=f"New deal: {title}",
                )
            elif action == "updated":
                result["dealsUpdated"] += 1
                change = upsert_result.get("change")
                if change == "stage":
                    log_activity(
                        db=db,
                        user_id=user_id,
                        contact_id=contact_id,
                        activity_type="deal_stage_change",
                        direction="internal",
                        source_type="crm_sync",
                        source_id=f"pipedrive_deal_{deal_data.get('id')}_stage_{upsert_result.get('new_stage')}",
                        summary=f"{title}: {upsert_result.get('old_stage')} → {upsert_result.get('new_stage')}",
                        title=f"Stage change: {title}",
                    )
                elif change == "status":
                    log_activity(
                        db=db,
                        user_id=user_id,
                        contact_id=contact_id,
                        activity_type="deal_status_change",
                        direction="internal",
                        source_type="crm_sync",
                        source_id=f"pipedrive_deal_{deal_data.get('id')}_status_{upsert_result.get('new_status')}",
                        summary=f"{title}: {upsert_result.get('old_status')} → {upsert_result.get('new_status')}",
                        title=f"Deal {upsert_result.get('new_status')}: {title}",
                    )
        except Exception as e:
            logger.error(f"Failed to upsert deal {deal_data.get('id')}: {e}")
            continue

    result["dealsTotal"] = len(pipedrive_deals)

    # --- Step 7: Recompute stats + set synced_at ---
    update_contact_stats(db, contact_id)
    contact.crm_synced_at = now
    db.commit()

    logger.info("Pipedrive sync complete", extra={
        "user_id": user_id, "contact_id": contact_id,
        "person_id": person_id, "deals_total": len(pipedrive_deals),
        "deals_created": result["dealsCreated"], "deals_updated": result["dealsUpdated"],
    })

    return result


def get_contacts_due_for_sync(db: Session, user_id: int, limit: int = 30) -> List[models.Contact]:
    """
    Query contacts that are due for Pipedrive sync based on smart interval logic.
    Priority: never synced > active+overdue > dormant+overdue.
    Returns up to `limit` contacts.
    """
    now = datetime.utcnow()
    active_cutoff = now - ACTIVE_WINDOW        # 48h ago
    active_interval = now - INTERVAL_ACTIVE     # 15 min ago
    dormant_interval = now - INTERVAL_DORMANT   # 6h ago

    # Base filter: user's non-deleted contacts
    base = and_(
        models.Contact.user_id == user_id,
        models.Contact.deleted_at.is_(None),
    )

    # Priority 1: Never synced (crm_synced_at IS NULL)
    never_synced = db.query(models.Contact).filter(
        base,
        models.Contact.crm_synced_at.is_(None),
    ).order_by(models.Contact.id).limit(limit).all()

    remaining = limit - len(never_synced)
    if remaining <= 0:
        return never_synced

    # Get IDs of contacts with open deals (for "active" classification)
    contacts_with_open_deals = db.query(models.ContactDeal.contact_id).filter(
        models.ContactDeal.user_id == user_id,
        models.ContactDeal.status == "open",
        models.ContactDeal.deleted_at.is_(None),
    ).distinct().subquery()

    # Priority 2: Active contacts (open deals OR recent activity) overdue for sync
    active_overdue = db.query(models.Contact).filter(
        base,
        models.Contact.crm_synced_at.isnot(None),
        models.Contact.crm_synced_at < active_interval,
        or_(
            models.Contact.id.in_(db.query(contacts_with_open_deals)),
            and_(
                models.Contact.last_activity_at.isnot(None),
                models.Contact.last_activity_at > active_cutoff,
            ),
        ),
    ).order_by(models.Contact.crm_synced_at).limit(remaining).all()

    remaining -= len(active_overdue)
    if remaining <= 0:
        return never_synced + active_overdue

    # Priority 3: Dormant contacts overdue for sync
    already_fetched_ids = [c.id for c in never_synced + active_overdue]
    dormant_overdue = db.query(models.Contact).filter(
        base,
        models.Contact.crm_synced_at.isnot(None),
        models.Contact.crm_synced_at < dormant_interval,
        ~models.Contact.id.in_(already_fetched_ids) if already_fetched_ids else True,
    ).order_by(models.Contact.crm_synced_at).limit(remaining).all()

    return never_synced + active_overdue + dormant_overdue


async def sync_all_contacts_pipedrive(
    db: Session,
    user_id: int,
) -> Dict[str, Any]:
    """
    Sync all contacts due for sync for a given user.
    Called by the background worker and the bulk manual endpoint.
    """
    import asyncio

    api_key = await _get_api_key(db, user_id)
    if not api_key:
        return {"success": False, "error": "Pipedrive API key not configured"}

    contacts = get_contacts_due_for_sync(db, user_id, limit=30)

    totals = {
        "success": True,
        "contactsSynced": 0,
        "personsFound": 0,
        "dealsCreated": 0,
        "dealsUpdated": 0,
        "errors": 0,
    }

    for contact in contacts:
        try:
            result = await sync_contact_pipedrive(db, user_id, contact.id)
            totals["contactsSynced"] += 1
            if result.get("personFound"):
                totals["personsFound"] += 1
            totals["dealsCreated"] += result.get("dealsCreated", 0)
            totals["dealsUpdated"] += result.get("dealsUpdated", 0)
        except Exception as e:
            logger.error(f"Sync failed for contact {contact.id}: {e}")
            totals["errors"] += 1
            continue

        # Rate limit: 100ms between contacts
        await asyncio.sleep(0.1)

    logger.info("Bulk Pipedrive sync complete", extra={
        "user_id": user_id,
        "contacts_synced": totals["contactsSynced"],
        "persons_found": totals["personsFound"],
        "deals_created": totals["dealsCreated"],
    })

    return totals
```

- [ ] **Step 2: Verify syntax**

```bash
cd /home/tauhid/code/aibot2/backend
python -c "import ast; ast.parse(open('pipedrive_sync.py').read()); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/pipedrive_sync.py
git commit -m "feat: add Pipedrive sync service — person linking, deal upsert, smart intervals"
```

---

## Task 3: Pipedrive Background Worker

**Files:**
- Create: `backend/pipedrive_worker.py`

- [ ] **Step 1: Create pipedrive_worker.py**

```python
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
from datetime import datetime

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
            logger.info(f"[{datetime.utcnow().isoformat()}] Starting Pipedrive sync cycle...")

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
```

- [ ] **Step 2: Verify syntax**

```bash
cd /home/tauhid/code/aibot2/backend
python -c "import ast; ast.parse(open('pipedrive_worker.py').read()); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/pipedrive_worker.py
git commit -m "feat: add Pipedrive background sync worker — smart intervals, per-user batch sync"
```

---

## Task 4: Manual Sync Endpoints

**Files:**
- Modify: `backend/contacts.py`

- [ ] **Step 1: Add sync endpoints to contacts.py**

In `backend/contacts.py`, add these two endpoints. They must go AFTER the `/export` endpoint and BEFORE the `/{contact_id}` detail endpoint (to avoid route capture, following the established pattern).

Find the line `@router.get("/{contact_id}", response_model=ContactDetailResponse)` and insert BEFORE it:

```python
@router.post("/sync-crm")
async def sync_all_contacts_crm(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Trigger Pipedrive sync for all contacts due for sync."""
    from pipedrive_sync import sync_all_contacts_pipedrive
    result = await sync_all_contacts_pipedrive(db, current_user.id)
    return result
```

Then also add AFTER the `POST /{contact_id}/merge` endpoint (at the end of the file, with other `/{contact_id}/...` routes):

```python
@router.post("/{contact_id}/sync-crm")
async def sync_contact_crm(
    contact_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Trigger Pipedrive sync for a single contact."""
    from pipedrive_sync import sync_contact_pipedrive
    result = await sync_contact_pipedrive(db, current_user.id, contact_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Sync failed"))
    return result
```

- [ ] **Step 2: Verify routes**

```bash
cd /home/tauhid/code/aibot2/backend
python -c "import ast; ast.parse(open('contacts.py').read()); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/contacts.py
git commit -m "feat: add manual Pipedrive sync endpoints — POST /contacts/sync-crm and /contacts/{id}/sync-crm"
```

---

## Task 5: Validation

- [ ] **Step 1: Verify all files load**

```bash
cd /home/tauhid/code/aibot2/backend
python -c "
import ast
for f in ['pipedrive_sync.py', 'pipedrive_worker.py', 'contacts.py', 'models.py']:
    ast.parse(open(f).read())
    print(f'{f}: OK')
print('All files valid')
"
```

- [ ] **Step 2: Verify endpoint routes**

```bash
cd /home/tauhid/code/aibot2/backend
python -c "
from contacts import router
for r in router.routes:
    methods = ', '.join(r.methods) if hasattr(r, 'methods') else 'N/A'
    print(f'{methods:10s} {r.path}')
" 2>/dev/null || echo "Import requires running services — verify via AST parse above"
```

Expected endpoints include:
- `POST /sync-crm` (bulk)
- `POST /{contact_id}/sync-crm` (single)

- [ ] **Step 3: Final commit if any remaining changes**

```bash
git status
# If clean: done. If not:
git add -A && git commit -m "feat: Pipedrive background sync pipeline — complete implementation"
```
