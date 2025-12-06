"""REST API for admin panel and integrations"""

from gatekeeper.api.requests import requests_bp
from gatekeeper.api.users import users_bp
from gatekeeper.api.approvals import approvals_bp
from gatekeeper.api.stats import stats_bp

__all__ = ['requests_bp', 'users_bp', 'approvals_bp', 'stats_bp']
