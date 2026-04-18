# rifftrax-poster-sync

Automatically sync poster art from [rifftrax.com](https://www.rifftrax.com) to your media server library.

If you've purchased RiffTrax videos and added them to Emby, Plex, or Jellyfin, you've probably noticed they show up without poster art. This tool fixes that by matching your library items to the RiffTrax catalog and uploading the official poster images.

## How it works

1. Builds a catalog index from the rifftrax.com sitemap (~1000 titles)
2. Lists items in your media server's RiffTrax library that are missing poster art
3. Matches each item to a catalog entry using direct slug matching, substring matching, and fuzzy matching
4. Scrapes the poster image from the matched rifftrax.com page
5. Uploads it to your media server via API

The catalog is cached locally and refreshed automatically every 30 days.

## Supported media servers

- **Emby** — fully supported
- Plex — planned
- Jellyfin — planned

## Install

```bash
pip install .
```

Or run directly:
```bash
python -m rifftrax_poster_sync sync \
  --host http://your-server:8096 \
  --api-key YOUR_API_KEY \
  --library RiffTrax
```

## Usage

### Sync posters

```bash
# Dry run first (no uploads, shows what would be done)
rifftrax-poster-sync sync \
  --host http://your-server:8096 \
  --api-key YOUR_API_KEY \
  --dry-run

# Run for real
rifftrax-poster-sync sync \
  --host http://your-server:8096 \
  --api-key YOUR_API_KEY
```

### Manage catalog

```bash
# Force refresh the catalog cache
rifftrax-poster-sync catalog --refresh --stats
```

### Docker

```bash
docker build -t rifftrax-poster-sync .

docker run --rm rifftrax-poster-sync sync \
  --host http://your-server:8096 \
  --api-key YOUR_API_KEY
```

### Run daily with cron

```bash
# Add to crontab (runs daily at 3am)
0 3 * * * rifftrax-poster-sync sync --host http://your-server:8096 --api-key YOUR_API_KEY
```

## How matching works

The tool uses a three-tier matching strategy:

1. **Direct match** (100% confidence) — generates candidate URL slugs from the item name and checks if they exist in the catalog
2. **Substring match** (90% confidence) — checks if a candidate slug is contained within a catalog slug (catches titles like `ladyhawke` matching `ladyhawke-with-cole-stratton-and-janet-varney`)
3. **Fuzzy match** (70%+ confidence) — uses sequence matching to find the closest catalog entry by word similarity

Items that don't match or whose pages have no poster image are logged and skipped.

The tool handles common filename conventions from RiffTrax downloads:
- Quality suffixes: `_HDhigh`, `_highTV`, `_HDmed`, etc.
- CamelCase filenames: `BattlefieldEarth_highTV` → `Battlefield Earth`
- Dot separators: `Road.House` → `Road House`
- RiffTrax Live prefixes, series prefixes, and more

## Safe to re-run

The tool only processes items that don't already have a primary poster image. Re-running it is safe and fast — items that already have art are skipped.

## Outstanding Issues
1. Some videos for example: (https://www.rifftrax.com/sherlock-holmes-the-pearl-of-death) see the poster art populated with the background art instead of the poster art from the rifftrax site.
