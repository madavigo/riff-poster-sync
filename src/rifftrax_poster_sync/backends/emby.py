"""Emby media server backend."""

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from .base import MediaServer

_log = logging.getLogger(__name__)

# Emby accepts the API key as an Authorization header, keeping it out of
# server-side access logs (which log the full request URL by default).
_AUTH_HEADER = "Authorization"


def _sniff_mime(data: bytes) -> str:
    """Return the MIME type for image bytes by inspecting magic bytes.

    Falls back to image/jpeg (Emby's most-tolerated format) when the
    signature is unrecognised. Logs a warning so silent failures surface
    in CronJob logs.
    """
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"GIF":
        return "image/gif"
    # logging.warning fires on every occurrence; warnings.warn deduplicates
    # by call site so only the first unrecognised image in a batch would
    # surface — exactly the silent failure mode we're trying to avoid.
    _log.warning(
        "upload_poster: unrecognised image signature %r; "
        "defaulting to image/jpeg — Emby may reject the upload",
        data[:4],
    )
    return "image/jpeg"


class EmbyServer(MediaServer):
    def __init__(self, host, api_key):
        self.host = host.rstrip("/")
        self.api_key = api_key

    def _auth_value(self):
        return f"MediaBrowser Token={self.api_key}"

    def _get(self, path, params=None):
        url = f"{self.host}{path}"
        if params:
            # urllib.parse.urlencode handles the full encoding contract
            # (spaces, special chars, None values).  urllib.request.quote
            # does not exist and would AttributeError at runtime.
            url = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url)
        req.add_header(_AUTH_HEADER, self._auth_value())
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    def get_library_id(self, library_name):
        data = self._get("/Library/MediaFolders")
        for folder in data.get("Items", []):
            if folder.get("Name") == library_name:
                return folder["Id"]
        available = ", ".join(f["Name"] for f in data.get("Items", []))
        raise RuntimeError(f"Library '{library_name}' not found. Available: {available}")

    def get_user_id(self):
        users = self._get("/Users")
        if not users:
            raise RuntimeError("No users found in Emby")
        for user in users:
            if user.get("Policy", {}).get("IsAdministrator"):
                return user["Id"]
        return users[0]["Id"]

    def get_items(self, user_id, library_id):
        """Return all items from the library with image tag info."""
        data = self._get(
            f"/Users/{user_id}/Items",
            {
                "ParentId": library_id,
                "Recursive": "true",
                "IncludeItemTypes": "Movie",
                "Fields": "Name,ImageTags,BackdropImageTags",
            },
        )
        items = data.get("Items", [])
        total = data.get("TotalRecordCount")
        if total is not None and len(items) < total:
            raise RuntimeError(
                f"Emby returned only {len(items)} of {total} items — "
                "aborting to avoid incorrect cache pruning."
            )
        return items

    def get_items_missing_posters(self, user_id, library_id):
        """Return (all_items, missing_items) where missing lacks a Primary image."""
        items = self.get_items(user_id, library_id)
        missing = [i for i in items if "Primary" not in i.get("ImageTags", {})]
        return items, missing

    def update_title(self, item_id, title, user_id=None):
        fetch_path = f"/Users/{user_id}/Items/{item_id}" if user_id else f"/Items/{item_id}"
        item = self._get(fetch_path)
        item["Name"] = title
        url = f"{self.host}/Items/{item_id}"
        data = json.dumps(item).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header(_AUTH_HEADER, self._auth_value())
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status in (200, 204)
        except urllib.error.HTTPError as e:
            print(f"  Title update failed: HTTP {e.code} {e.reason}")
            return False

    def _upload_image(self, item_id, image_type, image_bytes):
        """Upload an image of the given Emby image type (Primary, Backdrop, etc.)."""
        url = f"{self.host}/Items/{item_id}/Images/{image_type}"
        encoded = base64.b64encode(image_bytes)
        mime = _sniff_mime(image_bytes)
        req = urllib.request.Request(url, data=encoded, method="POST")
        req.add_header(_AUTH_HEADER, self._auth_value())
        req.add_header("Content-Type", mime)
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status in (200, 204)
        except urllib.error.HTTPError as e:
            print(f"  Upload ({image_type}) failed: HTTP {e.code} {e.reason}")
            return False

    def upload_poster(self, item_id, image_bytes):
        return self._upload_image(item_id, "Primary", image_bytes)

    def upload_backdrop(self, item_id, image_bytes):
        return self._upload_image(item_id, "Backdrop", image_bytes)

    def delete_image(self, item_id, image_type):
        """Delete an image of the given type from an item."""
        url = f"{self.host}/Items/{item_id}/Images/{image_type}"
        req = urllib.request.Request(url, method="DELETE")
        req.add_header(_AUTH_HEADER, self._auth_value())
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status in (200, 204)
        except urllib.error.HTTPError as e:
            print(f"  Delete ({image_type}) failed: HTTP {e.code} {e.reason}")
            return False
