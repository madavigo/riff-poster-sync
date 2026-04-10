"""Name cleaning, slug generation, and catalog matching."""

import difflib
import html
import re

FUZZY_THRESHOLD = 0.70

# Only strip quality suffixes preceded by underscore to avoid stripping real
# title words like "Spy High" or "Split Second"
_FILENAME_SUFFIXES = re.compile(
    r"_(HDhigh|HDmed|HDlow|HDLow|highTV|lowTV|high|low|HD|SD)$", re.IGNORECASE
)


def clean_name(name):
    """Normalize an item name for matching.

    Strips download-quality suffixes, decodes HTML entities, splits CamelCase
    filenames into words, normalizes dots and dashes.
    """
    name = html.unescape(name)
    name = _FILENAME_SUFFIXES.sub("", name)
    name = name.replace(".", " ")

    # CamelCase splitting only for names with no spaces (raw filenames)
    if " " not in name:
        name = name.replace("-", " ")
        if re.search(r"[a-z][A-Z]", name):
            name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
            name = re.sub(r"([A-Za-z])(\d)", r"\1 \2", name)
            name = re.sub(r"(\d)([A-Za-z])", r"\1 \2", name)
            # Re-join ordinal suffixes split above: "20 th" → "20th"
            name = re.sub(r"(\d) (st|nd|rd|th)(\b|[^a-z])", r"\1\2\3", name)
        # Single uppercase letters glued to next word: IAmMy → I Am My
        name = re.sub(r"(?<![A-Z])([A-Z])([A-Z][a-z])", r"\1 \2", name)
        # Lowercase prepositions glued from CamelCase: ReturnofSwampThing
        name = re.sub(r"([a-z])(of|and|the|from)([A-Z])", r"\1 \2 \3", name)
        name = re.sub(r"([a-z])(of|from)(?=\s|$)", r"\1 \2", name)

    # Decode percent-encoded characters
    name = re.sub(r"%([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), name)
    return name.strip()


def _base_slug(text):
    """Convert text to a hyphenated lowercase URL slug."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def _slug_to_words(slug):
    """Convert a slug to normalized words for fuzzy comparison."""
    return slug.replace("-", " ").replace("/", " ").strip()


def candidate_slugs(name):
    """Generate candidate slugs from an item name for direct catalog lookup."""
    slugs = []
    seen = set()

    def _add(s):
        if s and s not in seen:
            seen.add(s)
            slugs.append(s)

    # RiffTrax Live titles
    live_match = re.match(r"rifftrax\s*live[!:.\-_\s]*(.+)", name, re.IGNORECASE)
    if live_match:
        movie = clean_name(live_match.group(1))
        slug = _base_slug(movie)
        _add(f"live/{slug}")
        _add(f"rifftrax-live-{slug}")
        _add(slug)
        return slugs

    # "RiffTrax: Title" / "RiffTrax Goes to ..."
    rt_prefix = re.match(r"riff\s*trax[:\s]+(.+)", name, re.IGNORECASE)
    if rt_prefix:
        movie = clean_name(rt_prefix.group(1))
        slug = _base_slug(movie)
        _add(slug)
        _add(f"rifftrax-{slug}")
        _add(_base_slug(clean_name(name)))
        return slugs

    # "RiffTrax Sports: ..."
    sports_match = re.match(r"riff\s*trax\s*sports[:\-_\s]+(.+)", name, re.IGNORECASE)
    if sports_match:
        movie = clean_name(sports_match.group(1))
        slug = _base_slug(movie)
        _add(slug)
        _add(f"the-{slug}")
        return slugs

    # "The Mads are Back: ..."
    mads_match = re.match(r"the mads (?:are back[:\s]+)?(.+)", name, re.IGNORECASE)
    if mads_match:
        movie = clean_name(mads_match.group(1))
        slug = _base_slug(movie)
        _add(slug)
        _add(f"the-{slug}")
        _add(_base_slug(clean_name(name)))
        return slugs

    # "Mary Higgins Clark ..." prefix
    mhc_match = re.match(r"mary\s*higgins\s*clark[:\-_\s]+(.+)", name, re.IGNORECASE)
    if mhc_match:
        movie = clean_name(mhc_match.group(1))
        slug = _base_slug(movie)
        _add(slug)
        _add(f"a-{slug}" if not slug.startswith("a-") else slug)
        return slugs

    # Standard title
    cleaned = clean_name(name)
    base = _base_slug(cleaned)
    _add(base)

    # Numbers glued to words: "hobgoblins2" → "hobgoblins-2"
    fixed_nums = re.sub(r"([a-z])(\d)", r"\1-\2", base)
    _add(fixed_nums)

    # Roman numerals at boundary: "-iibrothers" → "-ii-brothers"
    fixed_roman = re.sub(
        r"(?:^|-)(iii|ii|iv)([a-hj-z])",
        lambda m: m.group(0).replace(m.group(1) + m.group(2),
                                     m.group(1) + "-" + m.group(2)),
        base
    )
    _add(fixed_roman)

    if not base.startswith("the-"):
        _add(f"the-{base}")
        _add(f"the-{fixed_nums}")

    # No hyphens variant: "ironheart"
    _add(base.replace("-", ""))

    # Drop "and": "sherlock-holmes-and-the-spider-woman" → "sherlock-holmes-the-spider-woman"
    if "-and-" in base:
        _add(base.replace("-and-", "-"))

    # US/UK spelling
    if "theater" in base:
        _add(base.replace("theater", "theatre"))
    if "theatre" in base:
        _add(base.replace("theatre", "theater"))

    # Numerals → words
    for digit, word in [("2", "two"), ("3", "three"), ("4", "four"),
                        ("5", "five"), ("10", "ten")]:
        if f"-{digit}-" in base or base.endswith(f"-{digit}"):
            variant = base.replace(f"-{digit}-", f"-{word}-").replace(
                f"-{digit}", f"-{word}")
            _add(variant)

    return slugs


def match_to_catalog(name, catalog_slugs):
    """Match an item name to a catalog slug.

    Returns (matched_slug, confidence, method) or (None, 0, None).
    """
    candidates = candidate_slugs(name)

    # 1. Direct match
    for slug in candidates:
        if slug in catalog_slugs:
            return slug, 1.0, "direct"

    # 2. Substring match
    for slug in candidates:
        if len(slug) < 4 or "/" in slug:
            continue
        for cat_slug in catalog_slugs:
            if slug in cat_slug or cat_slug.startswith(slug + "-"):
                return cat_slug, 0.9, "substring"

    # 3. Fuzzy match
    cleaned = clean_name(name)
    base = _base_slug(cleaned)
    cleaned_words = _slug_to_words(base)
    best_slug = None
    best_score = 0.0

    for cat_slug in catalog_slugs:
        cat_words = _slug_to_words(cat_slug)
        score = difflib.SequenceMatcher(None, cleaned_words, cat_words).ratio()
        if score > best_score:
            best_score = score
            best_slug = cat_slug

    if best_score >= FUZZY_THRESHOLD:
        return best_slug, best_score, "fuzzy"

    return None, 0.0, None
