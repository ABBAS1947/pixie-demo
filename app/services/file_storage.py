"""Opaque, contained ciphertext objects in the dedicated Pixie vault."""
import uuid
from pathlib import Path
from app.core.config import settings
from app.services.content_crypto import MAX_BYTES, atomic_private_write, owner_id, seal, unseal

class FileStorage:
    STORAGE_ROOT = Path(settings.FILE_STORAGE_ROOT)

    @classmethod
    def initialize(cls):
        (cls.STORAGE_ROOT / "users").mkdir(parents=True, exist_ok=True, mode=0o700)

    @classmethod
    def get_user_folder(cls, user_id):
        folder = cls.STORAGE_ROOT / "users" / owner_id(user_id)
        if folder.is_symlink() or not folder.resolve().is_relative_to(cls.STORAGE_ROOT.resolve() / "users"):
            raise ValueError("Invalid user storage path")
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        return folder

    @classmethod
    def save_file(cls, user_id, filename, content, *, resource_id):
        if len(content) > MAX_BYTES:
            raise ValueError("File exceeds the 50 MiB limit")
        owner = owner_id(user_id)
        resource = owner_id(resource_id)
        relative = f"users/{owner}/{resource}.pixie"
        data = seal(content, domain="private", owner=owner, resource=resource, field="upload").encode() if settings.content_encryption_mode == "required" else content
        atomic_private_write(cls.get_file_path(relative), data)
        return relative

    @classmethod
    def get_file_path(cls, storage_path, *, user_id=None, resource_id=None):
        path = cls.STORAGE_ROOT / storage_path
        root = cls.STORAGE_ROOT.resolve()
        if path.is_symlink() or not path.resolve().is_relative_to(root / "users"):
            raise ValueError("Invalid storage path")
        parts = Path(storage_path).parts
        if user_id is not None and (len(parts) < 3 or parts[0] != "users" or parts[1] != owner_id(user_id)):
            raise ValueError("Object does not belong to the expected learner")
        if resource_id is not None and settings.content_encryption_mode == "required":
            if len(parts) != 3 or path.name != f"{owner_id(resource_id)}.pixie":
                raise ValueError("Object does not match the expected resource")
        return path

    @classmethod
    def get_file_content(cls, storage_path, *, user_id=None, resource_id=None):
        if settings.content_encryption_mode == "required" and (user_id is None or resource_id is None):
            raise ValueError("Verified owner and resource are required")
        path = cls.get_file_path(storage_path, user_id=user_id, resource_id=resource_id)
        if path.stat().st_size > 100 * 1024 * 1024:
            raise ValueError("Stored object exceeds limit")
        data = path.read_bytes()
        if settings.content_encryption_mode != "required":
            return data
        parts = Path(storage_path).parts
        if len(parts) != 3 or parts[0] != "users" or path.suffix != ".pixie":
            raise ValueError("Encrypted storage migration is required")
        return unseal(data.decode("ascii"), domain="private", owner=owner_id(user_id),
                      resource=owner_id(resource_id), field="upload")

    @classmethod
    def delete_file(cls, storage_path, *, user_id=None, resource_id=None):
        path = cls.get_file_path(storage_path, user_id=user_id, resource_id=resource_id)
        existed = path.exists()
        path.unlink(missing_ok=True)
        return existed

    @classmethod
    def get_file_size(cls, storage_path):
        path = cls.get_file_path(storage_path)
        return path.stat().st_size if path.exists() else 0

    @classmethod
    def file_exists(cls, storage_path):
        return cls.get_file_path(storage_path).exists()

    @classmethod
    def save_processed_note(cls, user_id, note_id, content):
        raise RuntimeError("PostgreSQL is canonical; runtime Markdown mirrors are disabled")
