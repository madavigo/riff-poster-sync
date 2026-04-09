"""Poster image scraping from rifftrax.com pages."""

import re
import urllib.error
import urllib.request

RIFFTRAX_BASE = "https://www.rifftrax.com"

_GENERIC_IMAGE_FRAGMENTS = [
    "Logo-optimized", "FooterCouch", "RiffPlanet-social",
    "Live2017-header", "mcusercontent.com",
]


def _is_useful_image(url):
    """Return False if the URL is a generic site logo/banner."""
    return not any(frag in url for frag in _GENERIC_IMAGE_FRAGMENTS)


def scrape_poster_url(slug):
    """Fetch a rifftrax.com product page and extract the best poster image URL.

    Tries in order:
      1. Styled poster image (styles/poster CDN path)
      2. Any rifftrax CDN image
      3. og:image meta tag
    Returns URL string or None.
    """
    url = f"{RIFFTRAX_BASE}/{slug}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp:
            page_html = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"  Warning: HTTP {e.code} fetching {url}")
        return None
    except urllib.error.URLError as e:
        print(f"  Warning: URL error fetching {url}: {e.reason}")
        return None

    # 1. Styled poster image
    m = re.search(
        r'src="(https://www\.rifftrax\.com/sites/default/files/styles/poster[^"]+)"',
        page_html,
    )
    if m and _is_useful_image(m.group(1)):
        return m.group(1)

    # 2. Any rifftrax CDN image
    m = re.search(
        r'src="(https://www\.rifftrax\.com/sites/default/files/[^"]+\.(?:jpg|png))"',
        page_html,
    )
    if m and _is_useful_image(m.group(1)):
        return m.group(1)

    # 3. og:image meta tag
    m = re.search(
        r'<meta[^>]+property="og:image(?::url)?"[^>]+content="([^"]+)"',
        page_html,
    )
    if m and _is_useful_image(m.group(1)):
        return m.group(1)

    return None


def download_poster(poster_url):
    """Download a poster image and return the bytes, or None on failure."""
    try:
        with urllib.request.urlopen(poster_url) as resp:
            return resp.read()
    except Exception as e:
        print(f"  Warning: Could not download {poster_url}: {e}")
        return None
