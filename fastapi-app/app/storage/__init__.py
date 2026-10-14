from functools import lru_cache

from app.storage.base import StorageBackend
from app.storage.local import LocalStorage


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    return LocalStorage()
