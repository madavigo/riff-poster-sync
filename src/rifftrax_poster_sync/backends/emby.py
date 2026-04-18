"""Emby media server backend."""

import base64
import json
import urllib.error
import urllib.request

from .base import MediaServer

# Emby accepts the API key as an Authorization header, keeping it out of
# server-side access logs (which log the full request URL by default).
_AUTH_HEADER = "Authorization"


class EmbyServer(MediaServer):
    def __init__(self, host, api_key):
        self.host = host.rstrip("/")
        self.api_key = api_key

    def _auth_value(self):
        return f"MediaBrowser Token={self.api_key}"

    def _get(self, path, params=None):
        url = f"{self.host}{path}"
        if params:
            query = "&".join(
                f"{k}={urllib.request.quote(str(v))}" for k, v in params.items()
            )
            url = f"{url}?{query}"
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

    def get_items_missing_posters(self, user_id, library_id):
        data = self._get(
            f"/Users/{user_id}/Items",
            {
                "ParentId": library_id,
                "Recursive": "true",
                "IncludeItemTypes": "Movie",
                "Fields": "Name,ImageTags",
            },
        )
        items = data.get("Items", [])
        missing = [i for i in items if "Primary" not in i.get("ImageTags", {})]
        return items, missing

    def update_title(self, item_id, title, user_id=None):
        # Fetch full item via user-scoped endpoint
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

    def upload_poster(self, item_id, image_bytes):
        url = f"{self.host}/Items/{item_id}/Images/Primary"
        encoded = base64.b64encode(image_bytes)
        # Sniff magic bytes rather than trusting the URL extension — a CDN
        # can serve JPEG under a .png path and vice versa.
        mime = "image/png" if image_bytes[:4] == b"\x89PNG" else "image/jpeg"
        req = urllib.request.Request(url, data=encoded, method="POST")
        req.add_header(_AUTH_HEADER, self._auth_value())
        req.add_header("Content-Type", mime)
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status in (200, 204)
        except urllib.error.HTTPError as e:
            print(f"  Upload failed: HTTP {e.code} {e.reason}")
            return False
