from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable
from urllib.parse import urlparse, parse_qs
from firebase_admin import firestore

class AffiliateAttributionMiddleware(BaseHTTPMiddleware):
    """
    Middleware to capture ?ref=... and set a cookie for later use (e.g., at signup).
    Also records a click document in affiliate_clicks for tracking.
    """
    def __init__(self, app, cookie_name: str = "affiliate_ref", max_age_days: int = 90):
        super().__init__(app)
        self.cookie_name = cookie_name
        self.max_age = max_age_days * 24 * 3600

    async def dispatch(self, request: Request, call_next: Callable):
        # Extract ref from query if present
        ref = request.query_params.get('ref')
        response: Response = await call_next(request)
        if ref:
            try:
                # Store cookie for attribution on signup/checkout
                response.set_cookie(self.cookie_name, ref, max_age=self.max_age, httponly=False, samesite="Lax")
                # Record click document
                db = firestore.client()
                db.collection('affiliate_clicks').document().set({
                    'affiliateRef': ref,
                    'ip': request.client.host if request.client else None,
                    'userAgent': request.headers.get('user-agent'),
                    'createdAt': firestore.SERVER_TIMESTAMP,
                })
            except Exception:
                # Do not break the request on failure
                pass
        return response