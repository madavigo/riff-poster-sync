"""Cache for tracking which items have been fully synced (poster + backdrop + title)."""

import json
import pathlib
import time

DEFAULT_CACHE_DIR = pathlib.Path.home() / ".rifftrax-poster-sync"
CACHE_FILE_NAME = "synced_items.json"


def load_sync_cache(cache_dir=None):
    """Load the synced items cache from disk. Returns a dict keyed by item_id."""
    cache_file = (cache_dir or DEFAULT_CACHE_DIR) / CACHE_FILE_NAME
    if not cache_file.exists():
        return {}
    try:
        return json.loads(cache_file.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_sync_cache(cache, cache_dir=None):
    """Persist the synced items cache to disk."""
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / CACHE_FILE_NAME
    cache_file.write_text(json.dumps(cache, indent=2))


def is_synced(item_id, current_name, cache):
    """Return True if this item is fully synced: title matches and backdrop has been set."""
    entry = cache.get(str(item_id))
    if not entry:
        return False
    if entry.get("synced_title") != current_name:
        return False
    return bool(entry.get("backdrop_synced"))


def mark_synced(item_id, synced_title, slug, cache, backdrop_synced=False):
    """Record that an item has been fully synced."""
    cache[str(item_id)] = {
        "synced_title": synced_title,
        "slug": slug,
        "synced_at": time.time(),
        "backdrop_synced": backdrop_synced,
    }
