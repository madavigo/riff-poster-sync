"""Abstract base class for media server backends."""

from abc import ABC, abstractmethod


class MediaServer(ABC):
    """Interface that each media server backend must implement."""

    @abstractmethod
    def get_library_id(self, library_name):
        """Return the internal ID for a library by name."""

    @abstractmethod
    def get_user_id(self):
        """Return a user ID to use for API calls."""

    @abstractmethod
    def get_items_missing_posters(self, user_id, library_id):
        """Return (all_items, items_missing_posters).

        Each item is a dict with at least 'Id' and 'Name' keys.
        """

    @abstractmethod
    def update_title(self, item_id, title, user_id=None):
        """Update the display title for an item. Returns True on success."""

    @abstractmethod
    def upload_poster(self, item_id, image_bytes):
        """Upload poster image bytes for an item. Returns True on success."""
