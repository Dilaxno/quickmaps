import logging
from typing import Optional, Dict, Any
from datetime import datetime

from firebase_admin import firestore

logger = logging.getLogger(__name__)

class AffiliateService:
    def __init__(self, db_client: firestore.Client):
        self.db = db_client

    def reserve_username(self, desired: str, affiliate_uid: str) -> str:
        """
        Reserve a unique affiliate username using a Firestore transaction.
        Returns the reserved username (may apply a numeric suffix if taken).
        """
        desired = (desired or '').strip().lower()
        if not desired:
            raise ValueError("desired username required")

        usernames = self.db.collection('affiliate_usernames')
        base_slug = desired
        chosen = base_slug

        @firestore.transactional
        def txn(transaction: firestore.Transaction):
            nonlocal chosen
            for attempt in range(0, 50):  # limit attempts
                slug = base_slug if attempt == 0 else f"{base_slug}{attempt+1}"
                doc_ref = usernames.document(slug)
                snapshot = doc_ref.get(transaction=transaction)
                if snapshot.exists:
                    data = snapshot.to_dict() or {}
                    if data.get('uid') == affiliate_uid:
                        chosen = slug
                        return
                    # otherwise try next suffix
                    continue
                transaction.set(doc_ref, {
                    'uid': affiliate_uid,
                    'reservedAt': datetime.utcnow(),
                })
                chosen = slug
                return
            raise ValueError("could not reserve unique username")

        transaction = self.db.transaction()
        txn(transaction)
        return chosen

    def record_click(self, affiliate_ref: str, ip: str, user_agent: str) -> None:
        """Create affiliate_clicks doc for tracking."""
        ref = self.db.collection('affiliate_clicks').document()
        ref.set({
            'affiliateRef': affiliate_ref,
            'ip': ip,
            'userAgent': user_agent[:500] if user_agent else None,
            'createdAt': datetime.utcnow(),
        })

    def record_payment(self, payment_id: str, user_id: str, amount_cents: int, currency: str, affiliate_ref: Optional[str], plan_id: Optional[str], interval: Optional[str]) -> None:
        """
        Create payments/{paymentId} and update affiliate totals/referrals when affiliate_ref exists.
        """
        payment_doc = self.db.collection('payments').document(payment_id)
        payment_doc.set({
            'userId': user_id,
            'amount': amount_cents,
            'currency': (currency or 'USD').upper(),
            'affiliateRef': affiliate_ref,
            'status': 'paid',
            'createdAt': firestore.SERVER_TIMESTAMP,
            'planId': plan_id,
            'interval': interval,
        }, merge=True)

        if affiliate_ref:
            # find affiliate by username
            affiliates = self.db.collection('affiliates')
            q = affiliates.where('affiliateUsername', '==', affiliate_ref).limit(1)
            docs = list(q.stream())
            if not docs:
                logger.warning(f"Affiliate '{affiliate_ref}' not found; skipping totals update")
                return
            aff_doc = docs[0]
            aff_ref = aff_doc.reference

            @firestore.transactional
            def update_affiliate(transaction: firestore.Transaction):
                snapshot = transaction.get(aff_ref)
                data = snapshot.to_dict() or {}
                totals = data.get('totals') or {}
                revenue = float(totals.get('revenue', 0)) + float(amount_cents)
                commission = revenue * 0.30
                currency_u = (totals.get('currency') or currency or 'USD').upper()

                # referralsCount increment if first payment from this user
                # check if this affiliate already has a payment from this user
                prev = self.db.collection('payments').where('userId', '==', user_id).where('affiliateRef', '==', affiliate_ref).limit(1)
                prev_docs = list(prev.stream())
                inc_referrals = 1 if len(prev_docs) == 0 else 0

                update_data = {
                    'totals': {
                        'revenue': revenue,
                        'commission': commission,
                        'currency': currency_u,
                    }
                }
                if inc_referrals:
                    update_data['referralsCount'] = firestore.Increment(1)
                transaction.update(aff_ref, update_data)

            txn = self.db.transaction()
            update_affiliate(txn)