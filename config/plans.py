# Backend plan configurations - Updated to match frontend and Paddle sandbox
PLANS = {
    'free': {
        'id': 'free',
        'name': 'Free',
        'credits': 10,
        'monthlyCredits': 10,
        'price': {
            'monthly': 0,
            'yearly': 0
        }
    },
    'student': {
        'id': 'student',
        'name': 'Student',
        'credits': 1000,
        'monthlyCredits': 1000,
        'yearlyCredits': 12000,  # 1000 × 12
        'price': {
            'monthly': 9,
            'yearly': 64.8  # 40% off: $9 × 12 × 0.6
        },
        'paddle_price_ids': {
            'monthly': 'pri_01k1ngfpxby3z96nq58f5b4rk6',
            'yearly': 'pri_01k1nh2zjgjpz0kh966rwwhm2g'
        }
    },
    'researcher': {
        'id': 'researcher',
        'name': 'Researcher',
        'credits': 2000,
        'monthlyCredits': 2000,
        'yearlyCredits': 24000,  # 2000 × 12
        'price': {
            'monthly': 19,
            'yearly': 136.8  # 40% off: $19 × 12 × 0.6
        },
        'paddle_price_ids': {
            'monthly': 'pri_01k1ngh1qkacvh917cgwy9rsrb',
            'yearly': 'pri_01k1nh4js7573cdkqmn1t5tk8r'
        }
    },
    'expert': {
        'id': 'expert',
        'name': 'Expert',
        'credits': 5000,
        'monthlyCredits': 5000,
        'yearlyCredits': 60000,  # 5000 × 12
        'price': {
            'monthly': 29,
            'yearly': 209
        },
        'paddle_price_ids': {
            'monthly': 'pri_01k1ngjaydkk1dhdzk52jkzt0y',
            'yearly': 'pri_01k1nhp6d7mw0dkyqsb4a1bbyg'
        }
    }
}

def get_plan(plan_id):
    """Get plan configuration by ID"""
    return PLANS.get(plan_id, PLANS['free'])

def is_valid_plan(plan_id):
    """Check if plan ID is valid"""
    return plan_id in PLANS