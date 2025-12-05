"""Utility helper functions"""

import re
import json
import logging

logger = logging.getLogger(__name__)


def extract_json(text: str) -> str:
    """
    Extract JSON from response text, handling markdown code blocks.

    Args:
        text: Response text that may contain JSON

    Returns:
        Extracted JSON string
    """
    # Try to find JSON in code blocks first
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block:
        return code_block.group(1)

    # Fall back to finding raw JSON
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        return json_match.group(0)

    return text


def sanitize_log(data: dict, sensitive_keys: list = None) -> dict:
    """
    Sanitize data for logging by removing sensitive information.

    Args:
        data: Dictionary to sanitize
        sensitive_keys: List of keys to redact (default: api_key, password, token, secret)

    Returns:
        Sanitized copy of the dictionary
    """
    if sensitive_keys is None:
        sensitive_keys = ['api_key', 'apikey', 'password', 'token', 'secret', 'authorization']

    sanitized = {}
    for key, value in data.items():
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            sanitized[key] = '[REDACTED]'
        elif isinstance(value, dict):
            sanitized[key] = sanitize_log(value, sensitive_keys)
        else:
            sanitized[key] = value

    return sanitized


def safe_json_loads(text: str, default=None):
    """
    Safely parse JSON, returning default on failure.

    Args:
        text: JSON string to parse
        default: Default value if parsing fails

    Returns:
        Parsed JSON or default value
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


def truncate(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length.

    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to append if truncated

    Returns:
        Truncated text
    """
    if not text or len(text) <= max_length:
        return text or ""
    return text[:max_length - len(suffix)] + suffix


def normalize_rating(rating: str) -> str:
    """
    Normalize rating string to standard format.

    Args:
        rating: Rating string to normalize

    Returns:
        Normalized rating (uppercase, trimmed)
    """
    if not rating:
        return "UNKNOWN"

    rating = rating.strip().upper()

    # Common normalizations
    normalizations = {
        'NR': 'UNKNOWN',
        'NOT RATED': 'UNKNOWN',
        'UNRATED': 'UNKNOWN',
        'TV-Y7-FV': 'TV-Y7',
        'TV-14-DV': 'TV-14',
        'TV-14-LV': 'TV-14',
        'TV-MA-LV': 'TV-MA',
        'TV-MA-S': 'TV-MA',
    }

    return normalizations.get(rating, rating)
