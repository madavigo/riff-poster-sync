"""Orchestrator — ties catalog, matcher, scraper, and backend together."""

from .catalog import build_catalog
from .matcher import clean_name, match_to_catalog
from .scraper import download_image, scrape_page
from .sync_cache import is_synced, load_sync_cache, mark_synced, save_sync_cache


def sync(server, library_name, dry_run=False, force_refresh=False, cache_dir=None):
    """Run the full poster sync pipeline.

    Returns a dict with counts: updated, backdrop_updated, title_updated, skipped,
    no_poster, no_match.
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

    all_items = server.get_items(user_id, library_id)
    missing = [i for i in all_items if "Primary" not in i.get("ImageTags", {})]
    already_have = len(all_items) - len(missing)

    print(f"Total items: {len(all_items)}")
    print(f"  Already have poster: {already_have}")
    print(f"  Missing poster:      {len(missing)}\n")

    updated = 0
    backdrop_updated = 0
    title_updated = 0
    skipped = 0
    no_poster = 0
    no_match = 0

    cache_dirty = False

    for item in all_items:
        name = item["Name"]
        item_id = item["Id"]
        has_poster = "Primary" in item.get("ImageTags", {})
        has_backdrop = bool(item.get("BackdropImageTags", []))

        # Skip items already fully synced (poster + backdrop + title)
        if has_poster and has_backdrop and is_synced(item_id, name, sync_cache):
            skipped += 1
            continue

        # Match to catalog — exact and substring only first
        matched_slug, confidence, method = match_to_catalog(name, catalog_slugs, fuzzy=False)

        # Before fuzzy matching, try candidate slugs directly on rifftrax.com.
        # This catches items not yet in the sitemap (e.g. content uploaded outside
        # the normal workflow) before a fuzzy catalog match can grab the wrong title.
        if not matched_slug:
            from .matcher import candidate_slugs as _candidate_slugs
            from .scraper import _fetch_page
            for candidate in _candidate_slugs(name):
                if "/" in candidate:
                    continue
                page = _fetch_page(candidate)
                if page:
                    matched_slug = candidate
                    confidence = 1.0
                    method = "direct-fetch"
                    break

        # Last resort: fuzzy catalog match
        if not matched_slug:
            matched_slug, confidence, method = match_to_catalog(name, catalog_slugs, fuzzy=True)

        if not matched_slug:
            if not has_poster:
                print(f"[{name}]")
                print(f'  ✗ No catalog match (cleaned: "{clean_name(name)}")')
                no_match += 1
            continue

        # Fetch page (poster + background + title)
        poster_url, background_url, page_title = scrape_page(matched_slug)

        needs_poster = not has_poster
        needs_backdrop = not has_backdrop and background_url is not None
        needs_title = page_title and page_title != name

        if not needs_poster and not needs_backdrop and not needs_title:
            # Already in sync — update cache so we skip next time
            if not dry_run:
                mark_synced(item_id, name, matched_slug, sync_cache, backdrop_synced=True)
                cache_dirty = True
            skipped += 1
            continue

        conf_str = f"{confidence:.0%}" if confidence == 1.0 else f"{confidence:.1%}"
        print(f"[{name}]")
        print(f"  → Matched: /{matched_slug} ({method}, {conf_str})")

        final_title = page_title if needs_title else name

        # Update title if it differs
        if needs_title:
            if dry_run:
                print(f"  (dry run) Would rename: '{name}' → '{page_title}'")
                title_updated += 1
            elif server.update_title(item_id, page_title, user_id=user_id):
                print(f"  ✓ Title: '{name}' → '{page_title}'")
                title_updated += 1

        # Upload poster if missing
        if needs_poster:
            if not poster_url:
                print("  ✗ No poster image on page")
                no_poster += 1
                continue

            image_bytes = download_image(poster_url)
            if not image_bytes:
                no_poster += 1
                continue

            print(f"  ✓ Poster: {poster_url}")

            if dry_run:
                print(f"  (dry run) Would upload poster {len(image_bytes)} bytes")
                updated += 1
            elif server.upload_poster(item_id, image_bytes):
                print("  ✓ Poster uploaded")
                updated += 1
            else:
                no_poster += 1
                continue

        # Upload backdrop if missing
        backdrop_ok = has_backdrop  # already had one
        if needs_backdrop:
            image_bytes = download_image(background_url)
            if image_bytes:
                print(f"  ✓ Backdrop: {background_url}")
                if dry_run:
                    print(f"  (dry run) Would upload backdrop {len(image_bytes)} bytes")
                    backdrop_updated += 1
                    backdrop_ok = True
                elif server.upload_backdrop(item_id, image_bytes):
                    print("  ✓ Backdrop uploaded")
                    backdrop_updated += 1
                    backdrop_ok = True
                else:
                    print("  ✗ Backdrop upload failed")
            else:
                print("  ✗ Could not download backdrop image")

        # Mark fully synced
        if not dry_run:
            mark_synced(item_id, final_title, matched_slug, sync_cache, backdrop_synced=backdrop_ok)
            cache_dirty = True

    # Prune cache entries for items that no longer exist in the library.
    # Without this, a deleted item's entry lingers — if Emby reuses the same
    # item_id when the video is re-added AND auto-assigns a poster (e.g. from
    # TMDB) before the next sync run, the stale cache entry would cause the
    # RiffTrax poster to be silently skipped.
    seen_ids = {str(item["Id"]) for item in all_items}
    orphaned = [k for k in sync_cache if k not in seen_ids]
    if orphaned:
        n = len(orphaned)
        label = "entry" if n == 1 else "entries"
        print(f"  {'Would prune' if dry_run else 'Pruned'} {n} stale cache {label}: {orphaned}")
        if not dry_run:
            for k in orphaned:
                del sync_cache[k]
            cache_dirty = True

    if cache_dirty:
        save_sync_cache(sync_cache, cache_dir)

    results = {
        "updated": updated,
        "backdrop_updated": backdrop_updated,
        "title_updated": title_updated,
        "skipped": skipped,
        "no_poster": no_poster,
        "no_match": no_match,
    }

    print(f"\nDone.")
    print(f"  Posters uploaded:   {updated}")
    print(f"  Backdrops uploaded: {backdrop_updated}")
    print(f"  Titles updated:     {title_updated}")
    print(f"  Already synced:     {skipped}")
    print(f"  No poster on page:  {no_poster}")
    print(f"  No catalog match:   {no_match}")

    return results
