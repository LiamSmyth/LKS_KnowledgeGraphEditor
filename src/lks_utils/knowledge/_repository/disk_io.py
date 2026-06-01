"""Disk persistence helpers for Repository."""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from lks_utils.knowledge.links.link_instance import LinkInstance
from lks_utils.knowledge.links.link_type import LinkType
from lks_utils.knowledge.models.node import Node

if TYPE_CHECKING:
    from lks_utils.knowledge.repository import Repository


def save_repository(*, repository: Repository, directory: str | Path) -> None:
    root = Path(directory)
    repository._repo_root = root  # noqa: SLF001
    nodes_dir = root / "nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)

    desired_paths = repository._build_storage_paths(root)  # noqa: SLF001
    existing_json_files = set(nodes_dir.rglob(
        "*.json")) if nodes_dir.exists() else set()

    for node in repository.list_nodes():
        _atomic_write(
            str(desired_paths[str(node.id)]),
            pretty_json(node.model_dump()),
        )

    for stale_path in existing_json_files - set(desired_paths.values()):
        stale_path.unlink(missing_ok=True)

    prune_empty_directories(nodes_dir)

    link_types_dir = root / "link_types"
    link_type_paths = repository._build_link_type_storage_paths(root)  # noqa: SLF001
    existing_lt_files = set(link_types_dir.rglob(
        "*.json")) if link_types_dir.exists() else set()
    for lt in repository.list_link_types():
        _atomic_write(str(link_type_paths[lt.id]),
                      pretty_json(lt.model_dump()))
    desired_lt_files = set(link_type_paths.values())
    for stale in existing_lt_files - desired_lt_files:
        stale.unlink(missing_ok=True)
    prune_empty_directories(link_types_dir)

    links_dir = root / "links"
    link_paths = repository._build_link_storage_paths(root)  # noqa: SLF001
    existing_lk_files = set(links_dir.rglob(
        "*.json")) if links_dir.exists() else set()
    for lk in repository.list_links():
        _atomic_write(str(link_paths[lk.id]), pretty_json(lk.model_dump()))
    desired_lk_files = set(link_paths.values())
    for stale in existing_lk_files - desired_lk_files:
        stale.unlink(missing_ok=True)
    prune_empty_directories(links_dir)

    _atomic_write(
        str(root / "index.json"),
        pretty_json(repository._build_index(root=root, desired_paths=desired_paths)),  # noqa: SLF001
    )


def save_new_links(*, repository: Repository, directory: str | Path, new_link_ids: set[str]) -> None:
    root = Path(directory)
    repository._repo_root = root  # noqa: SLF001

    if new_link_ids:
        (root / "links").mkdir(parents=True, exist_ok=True)
        for lk_id in new_link_ids:
            lk_path = repository._compute_link_path(lk_id, root)  # noqa: SLF001
            if lk_path is not None:
                lk_path.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write(str(lk_path), pretty_json(repository._links[lk_id].model_dump()))  # noqa: SLF001

    repository._sync_index()  # noqa: SLF001


def save_new_link_types(*, repository: Repository, directory: str | Path, new_link_type_ids: set[str]) -> None:
    root = Path(directory)
    repository._repo_root = root  # noqa: SLF001

    if new_link_type_ids:
        (root / "link_types").mkdir(parents=True, exist_ok=True)
        lt_paths = repository._build_link_type_storage_paths(root)  # noqa: SLF001
        for lt_id in new_link_type_ids:
            lt_path = lt_paths.get(lt_id)
            if lt_path is not None:
                lt_path.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write(str(lt_path), pretty_json(repository._link_types[lt_id].model_dump()))  # noqa: SLF001

    repository._sync_index()  # noqa: SLF001


def save_touched(
    *,
    repository: Repository,
    directory: str | Path,
    touched_node_ids: set[str],
    touched_link_type_ids: set[str],
    touched_link_ids: set[str],
    old_repo: Repository,
) -> None:
    root = Path(directory)
    repository._repo_root = root  # noqa: SLF001

    new_node_paths = repository._build_storage_paths(root)  # noqa: SLF001
    old_node_paths = old_repo._build_storage_paths(root)  # noqa: SLF001

    if touched_node_ids:
        (root / "nodes").mkdir(parents=True, exist_ok=True)
        for node_id in touched_node_ids:
            new_path = new_node_paths.get(node_id)
            old_path = old_node_paths.get(node_id)
            if new_path is not None:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write(str(new_path), pretty_json(repository._nodes[node_id].model_dump()))  # noqa: SLF001
            if old_path is not None and old_path != new_path:
                old_path.unlink(missing_ok=True)
        prune_empty_directories(root / "nodes")

    if touched_link_type_ids:
        new_lt_paths = repository._build_link_type_storage_paths(root)  # noqa: SLF001
        old_lt_paths = old_repo._build_link_type_storage_paths(root)  # noqa: SLF001
        for lt_id in touched_link_type_ids:
            new_path = new_lt_paths.get(lt_id)
            old_path = old_lt_paths.get(lt_id)
            if new_path is not None:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write(str(new_path), pretty_json(repository._link_types[lt_id].model_dump()))  # noqa: SLF001
            if old_path is not None and old_path != new_path:
                old_path.unlink(missing_ok=True)
        lt_dir = root / "link_types"
        if lt_dir.exists():
            prune_empty_directories(lt_dir)

    if touched_link_ids:
        new_lk_paths = repository._build_link_storage_paths(root)  # noqa: SLF001
        old_lk_paths = old_repo._build_link_storage_paths(root)  # noqa: SLF001
        for lk_id in touched_link_ids:
            new_path = new_lk_paths.get(lk_id)
            old_path = old_lk_paths.get(lk_id)
            if new_path is not None:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write(str(new_path), pretty_json(repository._links[lk_id].model_dump()))  # noqa: SLF001
            _remove_stale_link_files(
                root=root,
                link_id=lk_id,
                keep_path=new_path,
                preferred_old_path=old_path,
            )
        lk_dir = root / "links"
        if lk_dir.exists():
            prune_empty_directories(lk_dir)

    repository._sync_index()  # noqa: SLF001


def load_repository(
    *,
    repository_cls: type[Repository],
    directory: str | Path,
    source_repo_id: str | None = None,
    use_index: bool = True,
) -> Repository:
    root = Path(directory)
    nodes_dir = root / "nodes"

    index_data = load_index_data(root) if use_index else None
    inferred_repo_id = load_index_repo_id(root) or "default"
    repo = repository_cls(source_repo_id=source_repo_id or inferred_repo_id)
    repo._repo_root = root  # noqa: SLF001

    for node_file in iter_node_files(root=root, nodes_dir=nodes_dir, index_data=index_data):
        if not node_file.exists():
            continue
        payload = json.loads(node_file.read_text(encoding="utf-8"))
        node = Node.model_validate(payload)
        if not node.source_repo_id:
            node = node.model_copy(
                update={"source_repo_id": repo.source_repo_id})
        repo.upsert(node)

    link_types_dir = root / "link_types"
    if link_types_dir.exists():
        for lt_file in sorted(link_types_dir.rglob("*.json")):
            try:
                lt = LinkType.model_validate(json.loads(
                    lt_file.read_text(encoding="utf-8")))
                repo.upsert_link_type(lt)
            except Exception:
                pass

    links_dir = root / "links"
    if links_dir.exists():
        for lk_file in sorted(links_dir.rglob("*.json")):
            try:
                lk = LinkInstance.model_validate(
                    json.loads(lk_file.read_text(encoding="utf-8")))
                repo.upsert_link(lk)
            except Exception:
                pass

    index_path = root / "index.json"
    if not index_path.exists():
        desired_paths = repo._build_storage_paths(root)  # noqa: SLF001
        _atomic_write(str(index_path), pretty_json(repo._build_index(root=root, desired_paths=desired_paths)))  # noqa: SLF001

    try:
        repo._sync_index()  # noqa: SLF001
    except PermissionError:
        # Concurrent external writers (e.g. live reload + MCP mutations) can
        # momentarily lock index.json on Windows; loading should remain read-safe.
        pass
    return repo


def load_index_data(root: Path) -> dict[str, object] | None:
    index_path = root / "index.json"
    if not index_path.exists():
        return None
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def iter_node_files(*, root: Path, nodes_dir: Path, index_data: dict[str, object] | None) -> list[Path]:
    indexed_files = indexed_node_files(root=root, index_data=index_data)
    if indexed_files:
        return indexed_files
    if not nodes_dir.exists():
        return []
    return sorted(nodes_dir.rglob("*.json"))


def indexed_node_files(*, root: Path, index_data: dict[str, object] | None) -> list[Path]:
    if not isinstance(index_data, dict):
        return []
    raw_nodes = index_data.get("nodes")
    if not isinstance(raw_nodes, dict):
        return []
    node_files: list[Path] = []
    for entry in raw_nodes.values():
        if not isinstance(entry, dict):
            continue
        raw_path = entry.get("path")
        if isinstance(raw_path, str) and raw_path:
            node_files.append(root / Path(raw_path))
    return sorted(node_files)


def prune_empty_directories(root: Path) -> None:
    if not root.exists():
        return
    directories = sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        try:
            next(directory.iterdir())
        except StopIteration:
            directory.rmdir()
        except OSError:
            continue


def load_index_repo_id(root: Path) -> str | None:
    data = load_index_data(root)
    if not isinstance(data, dict):
        return None
    value = data.get("source_repo_id")
    return str(value) if value else None


def _remove_stale_link_files(
    *,
    root: Path,
    link_id: str,
    keep_path: Path | None,
    preferred_old_path: Path | None,
) -> None:
    """Delete stale files for one link id while keeping the current target path.

    ``preferred_old_path`` may drift from the actual on-disk file location when
    a link's source/target/link-type has already gone missing. In that case,
    also scan by id suffix under ``links/`` to ensure stale files are removed.
    """
    candidates: set[Path] = set()
    if preferred_old_path is not None:
        candidates.add(preferred_old_path)

    links_dir = root / "links"
    if links_dir.exists():
        candidates.update(links_dir.rglob(f"*_{link_id}.json"))

    keep_marker = keep_path.as_posix() if keep_path is not None else None
    for candidate in candidates:
        if keep_marker is not None and candidate.as_posix() == keep_marker:
            continue
        candidate.unlink(missing_ok=True)


def pretty_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def _atomic_write(path: str, content: str) -> None:
    """Route writes through repository module symbol for patch-based tests."""
    from lks_utils.knowledge import repository as repository_module  # noqa: PLC0415

    repository_module.atomic_write(path, content)
