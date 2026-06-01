"""Index/cache sync helpers for Repository."""
from __future__ import annotations

from pathlib import Path
import time


def sync_index(*, repository: object) -> None:
    """Rebuild index.json from current repository state."""
    root = repository._require_repo_root()  # noqa: SLF001
    desired_paths = repository._build_storage_paths(root)  # noqa: SLF001
    index_path = root / "index.json"
    content = repository._pretty_json(  # noqa: SLF001
        repository._build_index(root=root, desired_paths=desired_paths)  # noqa: SLF001
    )
    if index_path.exists():
        try:
            current = index_path.read_text(encoding="utf-8")
            if current == content:
                return
        except Exception:
            pass
    _atomic_write(str(index_path), content)


def require_repo_root(*, repository: object) -> Path:
    """Return the configured repository root or raise a guidance error."""
    root = repository._repo_root  # noqa: SLF001
    if root is None:
        raise ValueError(
            "Repository root is not set. Call Repository.save(path) or "
            "Repository.load(path) before graph-view persistence operations."
        )
    return root


def _atomic_write(path: str, content: str) -> None:
    """Route writes through repository module symbol for patch-based tests."""
    from lks_utils.knowledge import repository as repository_module  # noqa: PLC0415

    last_error: PermissionError | None = None
    for delay in (0.01, 0.03, 0.06):
        try:
            repository_module.atomic_write(path, content)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(delay)
    if last_error is not None:
        raise last_error
