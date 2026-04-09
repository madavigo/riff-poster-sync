"""Command-line interface for rifftrax-poster-sync."""

import argparse
import pathlib
import sys

from . import __version__
from .backends.emby import EmbyServer
from .catalog import build_catalog
from .sync import sync


def main():
    parser = argparse.ArgumentParser(
        prog="rifftrax-poster-sync",
        description="Sync poster art from rifftrax.com to your media server.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command")

    # --- sync ---
    sync_p = sub.add_parser("sync", help="Sync poster art to your media server")
    sync_p.add_argument("--server", choices=["emby"], default="emby",
                        help="Media server type (default: emby)")
    sync_p.add_argument("--host", required=True, help="Server URL (e.g. http://10.10.67.170:9096)")
    sync_p.add_argument("--api-key", required=True, help="Server API key")
    sync_p.add_argument("--library", default="RiffTrax", help="Library name (default: RiffTrax)")
    sync_p.add_argument("--dry-run", action="store_true", help="Show what would be done without uploading")
    sync_p.add_argument("--refresh-catalog", action="store_true", help="Force refresh the RiffTrax catalog cache")
    sync_p.add_argument("--cache-dir", default=None, help="Override cache directory path")

    # --- catalog ---
    cat_p = sub.add_parser("catalog", help="Manage the RiffTrax catalog cache")
    cat_p.add_argument("--refresh", action="store_true", help="Force refresh from sitemap")
    cat_p.add_argument("--stats", action="store_true", help="Show catalog statistics")

    args = parser.parse_args()

    if args.command == "sync":
        if args.server == "emby":
            server = EmbyServer(args.host, args.api_key)
        cache_dir = pathlib.Path(args.cache_dir) if args.cache_dir else None
        sync(
            server=server,
            library_name=args.library,
            dry_run=args.dry_run,
            force_refresh=args.refresh_catalog,
            cache_dir=cache_dir,
        )

    elif args.command == "catalog":
        catalog = build_catalog(force_refresh=args.refresh)
        if args.stats:
            print(f"\nCatalog entries: {len(catalog['slugs'])}")

    else:
        parser.print_help()
        sys.exit(1)
