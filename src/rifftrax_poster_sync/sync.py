"""Orchestrator — ties catalog, matcher, scraper, and backend together."""

from .catalog import build_catalog
from .matcher import clean_name, match_to_catalog
from .scraper import download_poster, scrape_page
from .sync_cache import is_synced, load_sync_cache, mark_synced, save_sync_cache


def sync(server, library_name, dry_run=False, force_refresh=False, cache_dir=None):
    """Run the full poster sync pipeline.

    Returns a dict with counts: updated, title_updated, skipped, no_poster, no_match.
    """
    # Build or load catalog
    catalog = build_catalog(force_refresh=force_refresh, cache_dir=cache_dir)
    catalog_slugs = catalog["slugs"]
    print()

    # Load sync cache
    sync_cache = load_sync_cache(cache_dir)

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
    title_updated = 0
    skipped = 0
    no_poster = 0
    no_match = 0

    cache_dirty = False

    for item in all_items:
        name = item["Name"]
        item_id = item["Id"]
        has_poster = "Primary" in item.get("ImageTags", {})

        # Skip items already fully synced with the current title
        if has_poster and is_synced(item_id, name, sync_cache):
            skipped += 1
            continue

        # Match to catalog
        matched_slug, confidence, method = match_to_catalog(name, catalog_slugs)
        if not matched_slug:
            if not has_poster:
                print(f"[{name}]")
                print(f'  \u2717 No catalog match (cleaned: "{clean_name(name)}")')
                no_match += 1
            continue

        # Fetch page (poster + title)
        poster_url, page_title = scrape_page(matched_slug)

        needs_poster = not has_poster
        needs_title = page_title and page_title != name

        if not needs_poster and not needs_title:
            # Already in sync — update cache so we skip next time
            if not dry_run:
                mark_synced(item_id, name, matched_slug, sync_cache)
                cache_dirty = True
            skipped += 1
            continue

        conf_str = f"{confidence:.0%}" if confidence == 1.0 else f"{confidence:.1%}"
        print(f"[{name}]")
        print(f"  \u2192 Matched: /{matched_slug} ({method}, {conf_str})")

        final_title = page_title if needs_title else name

        # Update title if it differs
        if needs_title:
            if dry_run:
                print(f"  (dry run) Would rename: '{name}' → '{page_title}'")
                title_updated += 1
            elif server.update_title(item_id, page_title, user_id=user_id):
                print(f"  \u2713 Title: '{name}' → '{page_title}'")
                title_updated += 1

        # Upload poster if missing
        if needs_poster:
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
                continue

        # Mark fully synced
        if not dry_run:
            mark_synced(item_id, final_title, matched_slug, sync_cache)
            cache_dirty = True

    if cache_dirty:
        save_sync_cache(sync_cache, cache_dir)

    results = {
        "updated": updated,
        "title_updated": title_updated,
        "skipped": skipped,
        "no_poster": no_poster,
        "no_match": no_match,
    }

    print(f"\nDone.")
    print(f"  Posters uploaded: {updated}")
    print(f"  Titles updated:   {title_updated}")
    print(f"  Already synced:   {skipped}")
    print(f"  No poster on page:{no_poster}")
    print(f"  No catalog match: {no_match}")

    return results
