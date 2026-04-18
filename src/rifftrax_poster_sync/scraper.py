"""Poster image scraping from rifftrax.com pages."""

import re
import urllib.error
import urllib.request

RIFFTRAX_BASE = "https://www.rifftrax.com"

_GENERIC_IMAGE_FRAGMENTS = [
    "Logo-optimized", "FooterCouch", "RiffPlanet-social",
    "Live2017-header", "mcusercontent.com",
]

# Used by _extract_poster pass 2 to score CDN image candidates.
# PREFER: path segments that strongly indicate a product poster.
# REJECT: path segments that indicate decorative / layout images.
_POSTER_PREFER = re.compile(r"poster|product|cover", re.IGNORECASE)
_POSTER_REJECT = re.compile(r"background|banner|hero|header|logo|sprite", re.IGNORECASE)


def _is_useful_image(url):
    """Return False if the URL is a generic site logo/banner."""
    return not any(frag in url for frag in _GENERIC_IMAGE_FRAGMENTS)


def _fetch_page(slug):
    """Fetch a rifftrax.com product page and return the HTML, or None on failure."""
    url = f"{RIFFTRAX_BASE}/{slug}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"  Warning: HTTP {e.code} fetching {url}")
        return None
    except urllib.error.URLError as e:
        print(f"  Warning: URL error fetching {url}: {e.reason}")
        return None


def scrape_page(slug):
    """Fetch a rifftrax.com product page and return (poster_url, title).

    Either value may be None if not found.
    """
    page_html = _fetch_page(slug)
    if not page_html:
        return None, None

    poster_url = _extract_poster(page_html)
    title = _extract_title(page_html)
    return poster_url, title


def _extract_poster(page_html):
    """Extract the best poster image URL from page HTML."""
    # Pass 1: Drupal image-style path — highest confidence.
    # These URLs contain /styles/poster* which is the Drupal image style
    # reserved for product posters; almost never misidentified.
    m = re.search(
        r'src="(https://www\.rifftrax\.com/sites/default/files/styles/poster[^"]+)"',
        page_html,
    )
    if m and _is_useful_image(m.group(1)):
        return m.group(1)

    # Pass 2: All rifftrax CDN images, scored by path heuristic.
    # Using re.search (first match) here was the root cause of the poster
    # mismatch bug: on some pages the first matching URL is a background/hero
    # image that lives under the same sites/default/files/ path as real posters.
    # Instead, collect all candidates and prefer URLs with poster/product/cover
    # in the path, rejecting background/banner/hero/header/logo/sprite.
    candidates = re.findall(
        r'src="(https://www\.rifftrax\.com/sites/default/files/[^"]+\.(?:jpg|png))"',
        page_html,
    )
    preferred = [
        u for u in candidates
        if _POSTER_PREFER.search(u) and not _POSTER_REJECT.search(u)
    ]
    neutral = [
        u for u in candidates
        if not _POSTER_REJECT.search(u) and u not in preferred
    ]
    for url in (preferred or neutral):
        if _is_useful_image(url):
            return url

    # Pass 3: og:image meta tag — reliable on RiffTrax product pages but
    # placed last because it can point to a CDN-resized copy that loses quality.
    m = re.search(
        r'<meta[^>]+property="og:image(?::url)?"[^>]+content="([^"]+)"',
        page_html,
    )
    if m and _is_useful_image(m.group(1)):
        return m.group(1)

    return None


def _extract_title(page_html):
    """Extract the canonical product title from og:title meta tag."""
    import html as _html
    m = re.search(
        r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
        page_html,
    )
    if m:
        title = _html.unescape(m.group(1).strip())
        # Strip trailing site name e.g. " | RiffTrax"
        title = re.sub(r'\s*\|\s*RiffTrax\s*$', '', title).strip()
        return title if title else None
    return None


def scrape_poster_url(slug):
    """Fetch a rifftrax.com product page and extract the best poster image URL.

    .. deprecated::
        Use :func:`scrape_page` instead — it returns both poster and title in
        a single request and avoids a redundant HTTP fetch.
    """
    import warnings
    warnings.warn(
        "scrape_poster_url() is deprecated; use scrape_page() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    poster_url, _ = scrape_page(slug)
    return poster_url


def download_poster(poster_url):
    """Download a poster image and return the bytes, or None on failure."""
    try:
        with urllib.request.urlopen(poster_url) as resp:
            return resp.read()
    except Exception as e:
        print(f"  Warning: Could not download {poster_url}: {e}")
        return None
