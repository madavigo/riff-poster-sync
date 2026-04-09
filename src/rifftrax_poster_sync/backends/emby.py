"""Emby media server backend."""

import base64
import json
import urllib.error
import urllib.request

from .base import MediaServer


class EmbyServer(MediaServer):
    def __init__(self, host, api_key):
        self.host = host.rstrip("/")
        self.api_key = api_key

    def _get(self, path, params=None):
        url = f"{self.host}{path}?api_key={self.api_key}"
        if params:
            for k, v in params.items():
                url += f"&{k}={urllib.request.quote(str(v))}"
        req = urllib.request.Request(url)
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

    def update_title(self, item_id, title):
        url = f"{self.host}/Items/{item_id}?api_key={self.api_key}"
        # Emby requires sending the full item object back; fetch it first
        item = self._get(f"/Items/{item_id}")
        item["Name"] = title
        data = json.dumps(item).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status in (200, 204)
        except urllib.error.HTTPError as e:
            print(f"  Title update failed: HTTP {e.code} {e.reason}")
            return False

    def upload_poster(self, item_id, image_bytes):
        url = f"{self.host}/Items/{item_id}/Images/Primary?api_key={self.api_key}"
        encoded = base64.b64encode(image_bytes)
        req = urllib.request.Request(url, data=encoded, method="POST")
        req.add_header("Content-Type", "image/jpeg")
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status in (200, 204)
        except urllib.error.HTTPError as e:
            print(f"  Upload failed: HTTP {e.code} {e.reason}")
            return False
