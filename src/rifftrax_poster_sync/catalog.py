"""RiffTrax catalog — sitemap scraper and local cache."""

import json
import pathlib
import time
import urllib.request
import xml.etree.ElementTree as ET

RIFFTRAX_BASE = "https://www.rifftrax.com"
SITEMAP_URL = f"{RIFFTRAX_BASE}/sitemap.xml"
DEFAULT_CACHE_DIR = pathlib.Path.home() / ".rifftrax-poster-sync"
CATALOG_MAX_AGE_DAYS = 30

# Sitemap paths that are not product pages
_SKIP_PREFIXES = [
    "catalog", "collection", "staff", "article", "iriffs", "search",
    "genre", "riffer", "about", "app", "support", "community",
    "mst3k", "offers", "unriffed", "friends", "howto", "game",
    "music", "node", "user", "admin", "cart", "checkout",
]


def fetch_sitemap_slugs():
    """Fetch rifftrax.com sitemap and return a list of product page slugs."""
    print("Fetching sitemap from rifftrax.com ...")
    req = urllib.request.Request(SITEMAP_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        data = resp.read()

    root = ET.fromstring(data)
    ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [loc.text for loc in root.findall(".//ns:loc", ns)]

    base = f"{RIFFTRAX_BASE}/"
    slugs = []
    for url in urls:
        if not url.startswith(base):
            continue
        path = url[len(base):]
        if not path:
            continue
        if "/" in path and not path.startswith("live/"):
            continue
        if any(path == p or path.startswith(p + "/") or path.startswith(p + "?")
               for p in _SKIP_PREFIXES):
            continue
        slugs.append(path)

    print(f"  Found {len(slugs)} product slugs in sitemap")
    return slugs


def load_catalog(cache_dir=None):
    """Load the cached catalog from disk, or return None if stale/missing."""
    cache_file = (cache_dir or DEFAULT_CACHE_DIR) / "catalog.json"
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text())
        age_days = (time.time() - data.get("built_at", 0)) / 86400
        if age_days > CATALOG_MAX_AGE_DAYS:
            print(f"Catalog cache is {age_days:.0f} days old, refreshing ...")
            return None
        return data
    except (json.JSONDecodeError, KeyError):
        return None


def save_catalog(catalog, cache_dir=None):
    """Save catalog to disk."""
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "catalog.json"
    cache_file.write_text(json.dumps(catalog, indent=2))


def build_catalog(force_refresh=False, cache_dir=None):
    """Build or load the catalog index."""
    if not force_refresh:
        cached = load_catalog(cache_dir)
        if cached:
            print(f"Using cached catalog ({len(cached['slugs'])} slugs)")
            return cached

    slugs = fetch_sitemap_slugs()
    catalog = {
        "built_at": time.time(),
        "slugs": {s: s for s in slugs},
    }
    save_catalog(catalog, cache_dir)
    print(f"Catalog built and cached ({len(slugs)} slugs)")
    return catalog
