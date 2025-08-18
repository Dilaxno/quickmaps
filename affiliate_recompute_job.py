import asyncio
import logging
import os
from typing import Optional

from firebase_admin import firestore

# Global task handle so we can stop on shutdown
_TASK: Optional[asyncio.Task] = None


def _compute_totals_for_affiliate(db: firestore.Client, aff_doc: firestore.DocumentSnapshot, commission_rate: float = 0.35):
    """
    Recompute totals and referralsCount for a single affiliate from payments collection.
    Writes results back to affiliates/{uid} in a single update.
    """
    data = aff_doc.to_dict() or {}
    username = data.get('affiliateUsername')
    if not username:
        return

    payments_q = db.collection('payments') \
                  .where('affiliateRef', '==', username) \
                  .where('status', '==', 'paid')

    total_revenue = 0.0
    currency = (data.get('totals', {}) or {}).get('currency') or 'USD'
    unique_users = set()

    for d in payments_q.stream():
        p = d.to_dict() or {}
        amt = p.get('amount') or 0
        try:
            total_revenue += float(amt)
        except Exception:
            pass
        cur = p.get('currency')
        if cur:
            currency = cur
        uid = p.get('userId')
        if uid:
            unique_users.add(uid)

    referrals_count = len(unique_users)
    commission = total_revenue * commission_rate

    aff_doc.reference.update({
        'totals': {
            'revenue': total_revenue,
            'commission': commission,
            'currency': (currency or 'USD').upper(),
        },
        'referralsCount': referrals_count,
        'totalsLastRecomputedAt': firestore.SERVER_TIMESTAMP,
        'totalsSource': 'payments_full_recompute'
    })


def _recompute_all_sync(db: firestore.Client, logger: logging.Logger, commission_rate: float = 0.35):
    """Synchronous full recompute across all affiliates."""
    affiliates = db.collection('affiliates').stream()
    count = 0
    for aff_doc in affiliates:
        try:
            _compute_totals_for_affiliate(db, aff_doc, commission_rate)
            count += 1
        except Exception as e:
            logger.error(f"Affiliate totals recompute failed for {aff_doc.id}: {e}")
    logger.info(f"Affiliate totals recompute completed for {count} affiliates")


def _recompute_single_sync(db: firestore.Client, logger: logging.Logger, uid: Optional[str] = None, username: Optional[str] = None, commission_rate: float = 0.35) -> str:
    """Recompute for a single affiliate identified by uid or username. Returns affiliate uid."""
    aff_doc = None
    if uid:
        ref = db.collection('affiliates').document(uid)
        snap = ref.get()
        if not snap.exists:
            raise ValueError("Affiliate not found")
        aff_doc = snap
        uid_res = uid
    elif username:
        q = db.collection('affiliates').where('affiliateUsername', '==', username).limit(1)
        docs = list(q.stream())
        if not docs:
            raise ValueError("Affiliate not found")
        aff_doc = docs[0]
        uid_res = aff_doc.id
    else:
        raise ValueError("Provide uid or username")

    _compute_totals_for_affiliate(db, aff_doc, commission_rate)
    return uid_res


async def trigger_recompute_all(logger: logging.Logger, db: firestore.Client, commission_rate: float = 0.35):
    """Public async API to trigger one-off recompute for all affiliates."""
    await asyncio.to_thread(_recompute_all_sync, db, logger, commission_rate)


async def trigger_recompute_single(logger: logging.Logger, db: firestore.Client, uid: Optional[str] = None, username: Optional[str] = None, commission_rate: float = 0.35) -> str:
    """Public async API to recompute a single affiliate by uid or username."""
    return await asyncio.to_thread(_recompute_single_sync, db, logger, uid, username, commission_rate)


async def _loop(logger: logging.Logger, db: firestore.Client, interval_seconds: int, commission_rate: float = 0.35):
    logger.info(f"Affiliate totals scheduler running every {interval_seconds}s")
    while True:
        try:
            await trigger_recompute_all(logger, db, commission_rate)
        except Exception as e:
            logger.error(f"Affiliate totals periodic recompute error: {e}")
        await asyncio.sleep(interval_seconds)


def start_affiliate_recompute_scheduler(logger: logging.Logger, db: firestore.Client, interval_seconds: int = 6 * 60 * 60):
    """Start the periodic recompute scheduler. Safe to call multiple times; only one task runs."""
    global _TASK
    if _TASK and not _TASK.done():
        return _TASK
    loop = asyncio.get_running_loop()
    _TASK = loop.create_task(_loop(logger, db, interval_seconds))
    return _TASK


def stop_affiliate_recompute_scheduler(logger: logging.Logger):
    """Stop the periodic recompute scheduler if running."""
    global _TASK
    if _TASK and not _TASK.done():
        _TASK.cancel()
        logger.info("Affiliate totals scheduler stopped")
        _TASK = None