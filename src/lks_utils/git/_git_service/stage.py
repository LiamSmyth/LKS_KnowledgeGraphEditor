"""Staging and commit helpers for KnowledgeGitService."""
from __future__ import annotations

from pathlib import Path

import pygit2


def default_signature(repo: pygit2.Repository | None) -> pygit2.Signature:
    """Build commit signature from repository config with safe fallbacks."""
    if repo is None:
        return pygit2.Signature("lks", "lks@example.com")
    config = repo.config
    try:
        name = str(config["user.name"])
    except (KeyError, TypeError):
        name = "lks"
    try:
        email = str(config["user.email"])
    except (KeyError, TypeError):
        email = "lks@example.com"
    return pygit2.Signature(name, email)


def stage_paths(repo: pygit2.Repository | None, rel_paths: list[str]) -> None:
    """Stage selected repository-relative paths."""
    if repo is None:
        return
    index = repo.index
    for rel_path in rel_paths:
        index.add(rel_path.replace("\\", "/"))
    index.write()


def stage_all(repo: pygit2.Repository | None) -> None:
    """Stage all repository changes."""
    if repo is None:
        return
    index = repo.index
    index.add_all()
    index.write()


def unstage_paths(repo: pygit2.Repository | None, rel_paths: list[str]) -> None:
    """Unstage selected repository-relative paths."""
    if repo is None:
        return
    normalized = [path.replace("\\", "/") for path in rel_paths]
    if not normalized:
        return
    try:
        repo.reset_default(normalized)
    except Exception:
        index = repo.index
        for path in normalized:
            try:
                index.remove(path)
            except KeyError:
                continue
        index.write()


def unstage_all(repo: pygit2.Repository | None, staged_paths: set[str]) -> None:
    """Unstage all currently staged paths."""
    if repo is None:
        return
    if not staged_paths:
        return
    if repo.head_is_unborn:
        index = repo.index
        index.clear()
        index.write()
        return
    index = repo.index
    try:
        head_tree = repo.head.peel(pygit2.Tree)
    except (KeyError, pygit2.GitError):
        head_tree = None
    if head_tree is None:
        index.clear()
    else:
        index.read_tree(head_tree)
    index.write()


def commit(repo: pygit2.Repository | None, message: str) -> str | None:
    """Commit staged changes and return commit SHA."""
    if repo is None:
        return None
    index = repo.index
    tree = index.write_tree()
    if tree is None:
        return None
    signature = default_signature(repo)
    parents = [repo.head.target] if not repo.head_is_unborn else []
    oid = repo.create_commit(
        "HEAD",
        signature,
        signature,
        message.strip() or "Update knowledge repository",
        tree,
        parents,
    )
    return str(oid)


def revert_file(repo: pygit2.Repository | None, repository_root: Path, rel_path: str) -> None:
    """Revert one file to HEAD state in working tree and index."""
    if repo is None or repo.head_is_unborn:
        return
    normalized = rel_path.replace("\\", "/")
    status_flag = repo.status().get(normalized, pygit2.GIT_STATUS_CURRENT)
    is_untracked = bool(status_flag & (
        pygit2.GIT_STATUS_WT_NEW | pygit2.GIT_STATUS_INDEX_NEW))

    if is_untracked:
        file_path = repository_root / normalized
        try:
            if file_path.exists():
                file_path.unlink()
        except Exception:
            pass
        try:
            repo.index.remove(normalized)
            repo.index.write()
        except Exception:
            pass
        return

    try:
        repo.checkout_head(
            paths=[normalized],
            strategy=pygit2.GIT_CHECKOUT_FORCE,
        )
    except Exception:
        pass
    try:
        head_tree = repo.head.peel(pygit2.Tree)
        index = repo.index
        index.read_tree(head_tree)
        index.write()
    except Exception:
        pass


def ensure_bootstrap_commit(repo: pygit2.Repository | None, repository_root: Path) -> None:
    """Create initial commit for an unborn repository."""
    if repo is None or not repo.head_is_unborn:
        return
    gitignore_path = repository_root / ".gitignore"
    required_lines = ["__pycache__/", ".DS_Store", "*.tmp", ".lks/shelves/"]
    existing_lines: list[str] = []
    if gitignore_path.exists():
        existing_lines = [
            line.strip()
            for line in gitignore_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    merged_lines = list(existing_lines)
    for line in required_lines:
        if line not in merged_lines:
            merged_lines.append(line)
    gitignore_path.write_text("\n".join(merged_lines) + "\n", encoding="utf-8")
    index = repo.index
    index.add_all()
    index.write()
    tree = index.write_tree()
    signature = default_signature(repo)
    repo.create_commit(
        "HEAD",
        signature,
        signature,
        "Initialize knowledge repo",
        tree,
        [],
    )
