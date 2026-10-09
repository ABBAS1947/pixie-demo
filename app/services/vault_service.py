"""PostgreSQL is canonical. No runtime plaintext Markdown mirrors.

Legacy paths remain metadata until the explicit storage migration removes them.
Readable Markdown is produced by the authorized privacy export only.
"""
from pathlib import Path
from app.core.config import settings

def vault_path_for(user, title):
    return None

async def write_note_file(user, title, content):
    return None

def overwrite_note_file(user, vault_path, content):
    return None

def delete_note_file(vault_path):
    if not vault_path:
        return
    root = Path(settings.vault_root).resolve()
    path = root / vault_path
    if path.is_symlink() or not path.resolve().is_relative_to(root / "users"):
        raise ValueError("Invalid legacy note path")
    path.unlink(missing_ok=True)
