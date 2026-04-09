"""Orchestrator — ties catalog, matcher, scraper, and backend together."""

from .catalog import build_catalog
from .matcher import clean_name, match_to_catalog
from .scraper import download_poster, scrape_poster_url


def sync(server, library_name, dry_run=False, force_refresh=False, cache_dir=None):
    """Run the full poster sync pipeline.

    Returns a dict with counts: updated, no_poster, no_match, already_have.
    """
    # Build or load catalog
    catalog = build_catalog(force_refresh=force_refresh, cache_dir=cache_dir)
    catalog_slugs = catalog["slugs"]
    print()

    # Connect to media server
    print(f"Connecting to {server.__class__.__name__} ...")
    library_id = server.get_library_id(library_name)
    print(f"Found library '{library_name}' (id={library_id})")

    user_id = server.get_user_id()
    print(f"Using user id={user_id}\n")

    all_items, missing = server.get_items_missing_posters(user_id, library_id)
    already_have = len(all_items) - len(missing)

    print(f"Total items: {len(all_items)}")
    print(f"  Already have poster: {already_have}")
    print(f"  Missing poster:      {len(missing)}\n")

    updated = 0
    no_poster = 0
    no_match = 0

    for item in missing:
        name = item["Name"]
        item_id = item["Id"]
        print(f"[{name}]")

        # Match to catalog
        matched_slug, confidence, method = match_to_catalog(name, catalog_slugs)
        if not matched_slug:
            print(f'  \u2717 No catalog match (cleaned: "{clean_name(name)}")')
            no_match += 1
            continue

        conf_str = f"{confidence:.0%}" if confidence == 1.0 else f"{confidence:.1%}"
        print(f"  \u2192 Matched: /{matched_slug} ({method}, {conf_str})")

        # Fetch poster
        poster_url = scrape_poster_url(matched_slug)
        if not poster_url:
            print("  \u2717 No poster image on page")
            no_poster += 1
            continue

        image_bytes = download_poster(poster_url)
        if not image_bytes:
            no_poster += 1
            continue

        print(f"  \u2713 Poster: {poster_url}")

        if dry_run:
            print(f"  (dry run) Would upload {len(image_bytes)} bytes")
            updated += 1
            continue

        if server.upload_poster(item_id, image_bytes):
            print("  \u2713 Uploaded")
            updated += 1
        else:
            no_poster += 1

    results = {
        "updated": updated,
        "no_poster": no_poster,
        "no_match": no_match,
        "already_have": already_have,
    }

    print(f"\nDone.")
    print(f"  Updated:          {updated}")
    print(f"  No poster on page:{no_poster}")
    print(f"  No catalog match: {no_match}")
    print(f"  Already had art:  {already_have}")

    return results
