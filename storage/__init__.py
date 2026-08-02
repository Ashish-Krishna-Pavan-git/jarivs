"""Storage package compatibility exports."""

from .persistence import (
    load_digests,
    load_last_n_hours,
    load_today_digests,
    save_article,
    save_daily_report,
    save_digest,
    save_items,
)

__all__ = [
    "load_digests",
    "load_last_n_hours",
    "load_today_digests",
    "save_article",
    "save_daily_report",
    "save_digest",
    "save_items",
]
