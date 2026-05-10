"""One-time backfill: embed existing Text Gen outputs + transcripts + sent emails.

Iterates all completed Executions and EmailQueue rows, calling store_text_gen_output,
store_transcript_chunks, and store_generated_email. The UNIQUE(source_type, source_id,
chunk_index) constraint makes this safe to re-run — existing embeddings are updated
rather than duplicated.

Usage:
    python backfill_rag_embeddings.py                 # full backfill
    python backfill_rag_embeddings.py --dry-run       # count rows without embedding
    python backfill_rag_embeddings.py --limit 100     # backfill a subset
    python backfill_rag_embeddings.py --skip-emails   # text gen + transcript only

Expected cost: under $1 for typical existing data (text-embedding-3-small is
$0.02 per 1M tokens).
"""
import argparse
import asyncio
import logging
import sys
import time
from typing import List, Optional, Tuple

from sqlalchemy import String, cast, func, literal, or_

from database import SessionLocal
import models
from rag_service import (
    embeddings_available,
    store_text_gen_output,
    store_transcript_chunks,
    store_generated_email,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROGRESS_EVERY = 100
DEFAULT_FAIL_THRESHOLD_PCT = 10.0


def _text_gen_candidates(db, limit: Optional[int]) -> List[Tuple[int, bool, bool]]:
    """Return (execution_id, need_text_gen, need_transcript) for executions that
    still need at least one embedding.

    Filtering is done in SQL via NOT EXISTS correlated subqueries so we never
    materialise the full set of already-embedded source_ids in Python. Postgres
    uses the UNIQUE(source_type, source_id, chunk_index) index on
    content_embeddings to evaluate each subquery as an index lookup. Note that
    ``limit`` applies to rows that still need work — a value of 100 yields 100
    candidate executions rather than "first 100 by id, most of which may be
    already done".
    """
    eid_source_id = func.concat(
        cast(literal("execution:"), String), cast(models.Execution.id, String)
    )
    tid_source_id = func.concat(
        cast(literal("transcript:"), String), cast(models.Execution.id, String)
    )
    tg_missing = ~(
        db.query(models.ContentEmbedding.id)
        .filter(models.ContentEmbedding.source_type == "text_gen_output")
        .filter(models.ContentEmbedding.source_id == eid_source_id)
        .exists()
    )
    tr_missing = ~(
        db.query(models.ContentEmbedding.id)
        .filter(models.ContentEmbedding.source_type == "transcript_chunk")
        .filter(models.ContentEmbedding.source_id == tid_source_id)
        .exists()
    )
    q = (
        db.query(
            models.Execution.id,
            tg_missing.label("need_text_gen"),
            tr_missing.label("need_transcript"),
        )
        .filter(models.Execution.status == "completed")
        .filter(or_(tg_missing, tr_missing))
        .order_by(models.Execution.id)
    )
    if limit:
        q = q.limit(limit)
    return [(row.id, bool(row.need_text_gen), bool(row.need_transcript)) for row in q.all()]


def _email_candidates(db, limit: Optional[int]) -> List[int]:
    """Return EmailQueue ids that do not yet have a generated_email embedding.

    Uses a SQL NOT EXISTS so the "already embedded" filter happens at the
    index, not by loading every distinct source_id into memory. ``limit``
    applies to rows that still need work."""
    email_source_id = func.concat(
        cast(literal("email:"), String), cast(models.EmailQueue.id, String)
    )
    email_missing = ~(
        db.query(models.ContentEmbedding.id)
        .filter(models.ContentEmbedding.source_type == "generated_email")
        .filter(models.ContentEmbedding.source_id == email_source_id)
        .exists()
    )
    q = (
        db.query(models.EmailQueue.id)
        .filter(models.EmailQueue.status.in_(["sent", "pending"]))
        .filter(email_missing)
        .order_by(models.EmailQueue.id)
    )
    if limit:
        q = q.limit(limit)
    return [row[0] for row in q.all()]


def _log_progress(label: str, processed: int, ok: int, fail: int, skipped: int, start: float) -> None:
    elapsed = max(time.monotonic() - start, 1e-9)
    rate = processed / elapsed
    logger.info(
        f"{label} progress: processed={processed} ok={ok} failed={fail} "
        f"skipped={skipped} elapsed={elapsed:.1f}s rows_per_sec={rate:.1f}"
    )


async def _resolve_tenant(
    db, workflow_id: Optional[int]
) -> tuple[Optional[int], Optional[int]]:
    """Return (account_id, owner_user_id) for a workflow.

    Both are needed by the backfill: account_id scopes the embedding row,
    owner_user_id scopes the Contact lookup so we don't match a contact
    belonging to another tenant that happens to share the same email.
    """
    if not workflow_id:
        return None, None
    wf = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
    if not wf or not wf.owner_id:
        return None, None
    owner = db.query(models.User).filter(models.User.id == wf.owner_id).first()
    if not owner or not owner.org_id:
        return None, wf.owner_id
    acct = db.query(models.Account).filter(models.Account.org_id == owner.org_id).first()
    return (acct.id if acct else None), wf.owner_id


async def _resolve_contact_and_org(
    db,
    participants,
    user_id: Optional[int],
) -> tuple[Optional[int], Optional[int]]:
    """Find a contact whose email matches a participant, scoped to user_id.

    Contact.email is not unique across tenants; resolving globally would match
    another account's contact row and attach their contact_id/org_id to the
    embedding, violating multi-tenant isolation. When user_id is None we
    cannot safely resolve — return None.
    """
    if not participants or not user_id:
        return None, None
    for p in participants:
        email = p.get("email") if isinstance(p, dict) else None
        if email:
            contact = db.query(models.Contact).filter(
                models.Contact.email == email,
                models.Contact.user_id == user_id,
            ).first()
            if contact:
                return contact.id, contact.contact_organization_id
    return None, None


async def backfill_text_gen(limit: Optional[int], dry_run: bool) -> tuple[int, int, int]:
    ok, fail, skipped = 0, 0, 0
    processed = 0
    start = time.monotonic()

    # Phase 1: collect target IDs + per-row "need text_gen / transcript" flags
    # under a dedicated session, then close it. Previously this loaded every
    # already-embedded source_id into a Python set; now the NOT EXISTS lives
    # in SQL so memory no longer scales with the embedding table.
    # We intentionally do NOT iterate Execution rows with yield_per and commit
    # inside the loop — psycopg2 invalidates the server-side cursor when a
    # commit lands mid-stream, and a single row's failure would poison the
    # whole session so every subsequent row fails with InvalidRequestError.
    id_session = SessionLocal()
    try:
        candidates = _text_gen_candidates(id_session, limit)
    finally:
        id_session.close()

    logger.info(f"Text gen: {len(candidates)} executions need at least one embedding")

    # Phase 2: process each row on its own short-lived session so a single
    # embedding failure only rolls back that row and can't leak into the next.
    for ex_id, need_text_gen, need_transcript in candidates:
        processed += 1

        if not need_text_gen and not need_transcript:
            # Shouldn't happen — the candidate query filters to rows needing
            # work — but keep the branch so a future query change is safe.
            skipped += 1
        elif dry_run:
            ok += 1
        else:
            db = SessionLocal()
            try:
                ex = db.query(models.Execution).filter(models.Execution.id == ex_id).first()
                if ex is None:
                    # Row disappeared between phase 1 and phase 2 (unlikely
                    # but possible during a long backfill); treat as skipped.
                    skipped += 1
                else:
                    account_id, owner_user_id = await _resolve_tenant(db, ex.workflow_id)
                    if not account_id:
                        logger.debug(f"Skipped execution {ex.id}: no account_id")
                        fail += 1
                    else:
                        results = ex.results or {}
                        extracted = results.get("extracted_information") or {}
                        transcript = (ex.input_data or {}).get("transcript") or results.get("transcript") or ""
                        participants = (ex.input_data or {}).get("participants") or results.get("participants") or []

                        contact_id, org_id = await _resolve_contact_and_org(
                            db, participants, owner_user_id
                        )

                        if need_text_gen and extracted:
                            await store_text_gen_output(
                                db=db,
                                account_id=account_id,
                                execution_id=ex.id,
                                extracted_information=extracted,
                                contact_id=contact_id,
                                org_id=org_id,
                                meeting_date=(ex.input_data or {}).get("meeting_date"),
                            )
                        if need_transcript and transcript:
                            await store_transcript_chunks(
                                db=db,
                                account_id=account_id,
                                execution_id=ex.id,
                                transcript=transcript,
                                contact_id=contact_id,
                                org_id=org_id,
                                meeting_date=(ex.input_data or {}).get("meeting_date"),
                            )
                        ok += 1
            except Exception as e:
                logger.error(f"Failed execution {ex_id}: {e}")
                fail += 1
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                db.close()

        if processed % PROGRESS_EVERY == 0:
            _log_progress("Text gen", processed, ok, fail, skipped, start)

    _log_progress("Text gen final", processed, ok, fail, skipped, start)
    return ok, fail, skipped


async def backfill_emails(limit: Optional[int], dry_run: bool) -> tuple[int, int, int]:
    ok, fail, skipped = 0, 0, 0
    processed = 0
    start = time.monotonic()

    # Phase 1: SQL-filtered candidate list — only emails that still need an
    # embedding come back. See backfill_text_gen for the rationale on not
    # mixing yield_per with commits.
    id_session = SessionLocal()
    try:
        email_ids = _email_candidates(id_session, limit)
    finally:
        id_session.close()

    logger.info(f"Emails: {len(email_ids)} rows need embedding")

    # Phase 2: one session per row; a single row's failure cannot poison the
    # next row's transaction.
    for eq_id in email_ids:
        processed += 1
        if dry_run:
            ok += 1
        else:
            db = SessionLocal()
            try:
                eq = db.query(models.EmailQueue).filter(models.EmailQueue.id == eq_id).first()
                if eq is None:
                    skipped += 1
                else:
                    account_id, _ = await _resolve_tenant(db, eq.workflow_id)
                    if not account_id:
                        logger.debug(f"Skipped email {eq.id}: no account_id")
                        fail += 1
                    else:
                        # Contact lookup is by primary key (eq.contact_id), not
                        # by email, so no cross-tenant scoping needed here —
                        # the PK FK already proves ownership.
                        org_id = None
                        if eq.contact_id:
                            c = db.query(models.Contact).filter(models.Contact.id == eq.contact_id).first()
                            if c:
                                org_id = c.contact_organization_id

                        await store_generated_email(
                            account_id=account_id,
                            email_queue_id=eq.id,
                            subject=eq.subject,
                            body=eq.body,
                            contact_id=eq.contact_id,
                            org_id=org_id,
                            sequence_run_id=eq.sequence_run_id,
                            workflow_id=eq.workflow_id,
                        )
                        ok += 1
            except Exception as e:
                logger.error(f"Failed email {eq_id}: {e}")
                fail += 1
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                db.close()

        if processed % PROGRESS_EVERY == 0:
            _log_progress("Emails", processed, ok, fail, skipped, start)

    _log_progress("Emails final", processed, ok, fail, skipped, start)
    return ok, fail, skipped


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Count rows without actually embedding")
    parser.add_argument("--limit", type=int, help="Limit the number of rows processed (per category)")
    parser.add_argument("--skip-emails", action="store_true", help="Only backfill text gen + transcripts")
    parser.add_argument("--skip-text-gen", action="store_true", help="Only backfill emails")
    parser.add_argument(
        "--fail-threshold-pct",
        type=float,
        default=DEFAULT_FAIL_THRESHOLD_PCT,
        help="Exit non-zero only if failure rate (fail / (ok + fail)) exceeds this percent (default 10)",
    )
    args = parser.parse_args()

    if not embeddings_available() and not args.dry_run:
        logger.error(
            "OPENAI_API_KEY is not configured. Set it in docker/.env (or your "
            "environment) and restart the backend before running the backfill. "
            "Use --dry-run to count rows without embedding."
        )
        sys.exit(2)

    total_ok, total_fail, total_skipped = 0, 0, 0

    if not args.skip_text_gen:
        ok, fail, skipped = await backfill_text_gen(args.limit, args.dry_run)
        logger.info(f"Text gen: ok={ok} fail={fail} skipped={skipped}")
        total_ok += ok
        total_fail += fail
        total_skipped += skipped

    if not args.skip_emails:
        ok, fail, skipped = await backfill_emails(args.limit, args.dry_run)
        logger.info(f"Emails: ok={ok} fail={fail} skipped={skipped}")
        total_ok += ok
        total_fail += fail
        total_skipped += skipped

    attempted = total_ok + total_fail
    fail_pct = (total_fail / attempted * 100.0) if attempted else 0.0
    logger.info(
        f"Backfill complete: {total_ok} embedded, {total_fail} failed, "
        f"{total_skipped} skipped (fail_rate={fail_pct:.1f}%)"
    )
    sys.exit(0 if fail_pct <= args.fail_threshold_pct else 1)


if __name__ == "__main__":
    asyncio.run(main())
