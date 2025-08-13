from fastapi import APIRouter, Request, HTTPException
from firebase_admin import firestore
from typing import Optional
from datetime import datetime

from affiliate_service import AffiliateService

router = APIRouter(prefix="/affiliate", tags=["affiliate"])

affiliate_service: Optional[AffiliateService] = None

def init(db_client):
    global affiliate_service
    affiliate_service = AffiliateService(db_client)

@router.get("/click")
async def track_click(request: Request, ref: str):
    if not affiliate_service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    ip = request.client.host if request.client else None
    user_agent = request.headers.get('user-agent')
    affiliate_service.record_click(ref, ip, user_agent)
    return {"ok": True}

@router.post("/reserve-username")
async def reserve_username(body: dict):
    if not affiliate_service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    desired = body.get('desired')
    uid = body.get('uid')
    if not desired or not uid:
        raise HTTPException(status_code=400, detail="desired and uid are required")
    try:
        slug = affiliate_service.reserve_username(desired, uid)
        return {"ok": True, "slug": slug}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/stats")
async def get_stats(uid: Optional[str] = None, username: Optional[str] = None, days: int = 90):
    """
    Aggregate clicks, payments, revenue, and commission for an affiliate.
    Identify the affiliate by uid or username. Default window is last 90 days; set days<=0 for all-time.
    """
    if not affiliate_service:
        raise HTTPException(status_code=500, detail="Service not initialized")

    db = affiliate_service.db
    if not db:
        raise HTTPException(status_code=500, detail="Database not available")

    # Resolve affiliate doc
    aff_doc = None
    aff_uid = None
    if uid:
        doc_ref = db.collection('affiliates').document(uid)
        snap = doc_ref.get()
        if not snap.exists:
            raise HTTPException(status_code=404, detail="Affiliate not found")
        aff_doc = snap
        aff_uid = uid
    elif username:
        query = db.collection('affiliates').where('affiliateUsername', '==', username).limit(1)
        docs = list(query.stream())
        if not docs:
            raise HTTPException(status_code=404, detail="Affiliate not found")
        aff_doc = docs[0]
        aff_uid = aff_doc.id
    else:
        raise HTTPException(status_code=400, detail="Provide uid or username")

    aff_data = aff_doc.to_dict() or {}
    aff_username = aff_data.get('affiliateUsername')
    if not aff_username:
        raise HTTPException(status_code=400, detail="Affiliate username missing on profile")

    # Time window
    from datetime import datetime, timedelta
    threshold = None
    if days and days > 0:
        threshold = datetime.utcnow() - timedelta(days=days)

    # Payments aggregation
    payments_q = db.collection('payments')\
        .where('affiliateRef', '==', aff_username)\
        .where('status', '==', 'paid')
    if threshold:
        payments_q = payments_q.where('createdAt', '>=', threshold)

    total_revenue = 0.0
    payments_count = 0
    currency = aff_data.get('totals', {}).get('currency') or 'USD'
    referred_user_ids = set()

    for d in payments_q.stream():
        data = d.to_dict() or {}
        amt = data.get('amount')
        try:
            total_revenue += float(amt or 0)
        except Exception:
            pass
        payments_count += 1
        if data.get('currency'):
            currency = data.get('currency')
        uid_ref = data.get('userId')
        if uid_ref:
            referred_user_ids.add(uid_ref)

    referrals_count = len(referred_user_ids)
    commission = total_revenue * 0.30

    # Clicks aggregation
    clicks_q = db.collection('affiliate_clicks').where('affiliateRef', '==', aff_username)
    if threshold:
        clicks_q = clicks_q.where('createdAt', '>=', threshold)

    clicks_count = sum(1 for _ in clicks_q.stream())
    conversion_rate = (referrals_count / clicks_count) if clicks_count > 0 else 0.0

    return {
        'affiliate': {
            'uid': aff_uid,
            'username': aff_username,
            'email': aff_data.get('email'),
            'name': aff_data.get('name'),
        },
        'windowDays': days,
        'totals': {
            'revenue': total_revenue,
            'commission': commission,
            'currency': (currency or 'USD').upper(),
            'paymentsCount': payments_count,
            'referralsCount': referrals_count,
            'clicksCount': clicks_count,
            'conversionRate': conversion_rate,
        },
        'lastUpdated': datetime.utcnow().isoformat() + 'Z',
    }