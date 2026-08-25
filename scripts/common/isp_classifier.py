"""
ISP name normalization — maps raw ip2region ISP strings to groups:
telecom / unicom / mobile / other
"""

from .constants import ISP_KEYWORDS


def classify_isp(isp_name: str) -> str:
    """Normalize an ISP name to one of: telecom, unicom, mobile, other."""
    if not isp_name:
        return 'other'

    lower = isp_name.lower().strip()

    for group, keywords in ISP_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return group

    return 'other'
