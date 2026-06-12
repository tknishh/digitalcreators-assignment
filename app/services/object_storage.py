import logging
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class StorageError(Exception):
    pass


class StorageObjectNotFoundError(StorageError):
    pass


class ObjectStorage(ABC):
    @abstractmethod
    def upload(self, local_path: Path, key: str, content_type: str = "application/octet-stream") -> str:
        raise NotImplementedError

    @abstractmethod
    def download(self, key: str, local_path: Path) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def exists(self, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_public_url(self, key: str) -> str | None:
        raise NotImplementedError


class LocalObjectStorage(ObjectStorage):
    def __init__(self) -> None:
        self.root = settings.local_storage_dir
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        return self.root / key

    def upload(self, local_path: Path, key: str, content_type: str = "application/octet-stream") -> str:
        dest = self._path_for(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest)
        return key

    def exists(self, key: str) -> bool:
        path = self._path_for(key)
        return path.is_file() and path.stat().st_size > 0

    def download(self, key: str, local_path: Path) -> None:
        src = self._path_for(key)
        if not self.exists(key):
            raise StorageObjectNotFoundError(f"Object not found in storage: {key}")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, local_path)

    def delete(self, key: str) -> None:
        path = self._path_for(key)
        if path.exists():
            path.unlink()

    def get_public_url(self, key: str) -> str | None:
        return None


class FirebaseObjectStorage(ObjectStorage):
    def __init__(self) -> None:
        import firebase_admin
        from firebase_admin import credentials, storage

        cred_path = Path(settings.firebase_credentials_path)
        if not settings.firebase_credentials_path or not cred_path.exists():
            raise FileNotFoundError(
                f"Firebase credentials file not found: {settings.firebase_credentials_path}"
            )
        if cred_path.is_dir():
            raise FileNotFoundError(
                f"Firebase credentials path is a directory, not a JSON file: {cred_path}"
            )

        bucket = settings.firebase_storage_bucket.removeprefix("gs://")

        if not firebase_admin._apps:
            cred = credentials.Certificate(str(cred_path))
            firebase_admin.initialize_app(cred, {"storageBucket": bucket})

        self._bucket = storage.bucket()

    def upload(self, local_path: Path, key: str, content_type: str = "application/octet-stream") -> str:
        blob = self._bucket.blob(key)
        blob.upload_from_filename(str(local_path), content_type=content_type)
        return key

    def exists(self, key: str) -> bool:
        return self._bucket.blob(key).exists()

    def download(self, key: str, local_path: Path) -> None:
        blob = self._bucket.blob(key)
        if not blob.exists():
            raise StorageObjectNotFoundError(f"Object not found in storage: {key}")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(local_path))

    def delete(self, key: str) -> None:
        blob = self._bucket.blob(key)
        if blob.exists():
            blob.delete()

    def get_public_url(self, key: str) -> str | None:
        blob = self._bucket.blob(key)
        if not blob.exists():
            return None
        return blob.public_url


_storage: ObjectStorage | None = None
_active_storage_backend: str = "uninitialized"


def get_active_storage_backend() -> str:
    if _storage is None:
        get_object_storage()
    return _active_storage_backend


def get_object_storage() -> ObjectStorage:
    global _storage, _active_storage_backend
    if _storage is None:
        if settings.storage_backend == "firebase":
            try:
                _storage = FirebaseObjectStorage()
                _active_storage_backend = "firebase"
                logger.info(
                    "Using Firebase Storage bucket: %s",
                    settings.firebase_storage_bucket.removeprefix("gs://"),
                )
            except Exception as exc:
                _storage = LocalObjectStorage()
                _active_storage_backend = "local"
                logger.warning(
                    "Firebase init failed (%s). Falling back to local storage at %s",
                    exc,
                    settings.local_storage_dir,
                )
        else:
            _storage = LocalObjectStorage()
            _active_storage_backend = "local"
            logger.info("Using local object storage at %s", settings.local_storage_dir)
    return _storage
