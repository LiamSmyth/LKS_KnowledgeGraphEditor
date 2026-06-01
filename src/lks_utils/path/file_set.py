"""
FileSet dataclass for representing collections of files with a common root.

Provides utilities for creating, filtering, and managing sets of files
for batch operations like archiving, backup, sync, and processing.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lks_utils.logging import log_debug, log_warn


def _find_common_ancestor(paths: list[Path]) -> Path:
    """Find the lowest common ancestor directory of all paths.

    Args:
        paths: List of file or directory paths

    Returns:
        Path to the common ancestor directory

    Raises:
        ValueError: If paths list is empty

    Examples:
        >>> _find_common_ancestor([Path("C:/a/b/file1.txt"), Path("C:/a/c/file2.txt")])
        WindowsPath('C:/a')

        >>> _find_common_ancestor([Path("C:/file.txt")])
        WindowsPath('C:/')
    """
    if not paths:
        raise ValueError("Cannot find common ancestor of empty path list")

    # Resolve all paths to absolute
    resolved = [p.resolve() for p in paths]

    # If single path, return its parent (or root if it's a root path)
    if len(resolved) == 1:
        path = resolved[0]
        if path.is_file():
            return path.parent
        return path

    # Check if paths are on different drives (Windows)
    drives = {p.drive for p in resolved if p.drive}
    if len(drives) > 1:
        # Paths on different drives - use the drive root of the first path
        log_warn(
            f"Paths span multiple drives: {drives}. Using first drive as root.")
        return Path(resolved[0].drive + os.sep)

    # Find common parts by comparing path components
    parts_lists = [list(p.parts) for p in resolved]

    # Find the shortest path length
    min_length = min(len(parts) for parts in parts_lists)

    # Find common prefix
    common_parts = []
    for i in range(min_length):
        parts_at_i = {parts[i] for parts in parts_lists}
        if len(parts_at_i) == 1:
            common_parts.append(parts_at_i.pop())
        else:
            break

    # If no common parts, use drive root or current directory
    if not common_parts:
        if resolved[0].drive:
            return Path(resolved[0].drive + os.sep)
        return Path.cwd()

    return Path(*common_parts)


@dataclass
class FileSet:
    """A collection of files with a common root directory.

    Represents a set of files relative to a root path, useful for
    batch operations that need to preserve directory structure.

    Attributes:
        root_path: Base directory for all relative paths
        relative_paths: List of file paths relative to root_path
        name: Optional name for this file set (e.g., "MyProject")
    """
    root_path: Path
    relative_paths: list[Path] = field(default_factory=list)
    name: str = ""

    def __post_init__(self) -> None:
        """Convert paths to Path objects if needed."""
        if isinstance(self.root_path, str):
            self.root_path = Path(self.root_path)

        self.relative_paths = [
            Path(p) if isinstance(p, str) else p
            for p in self.relative_paths
        ]

    @staticmethod
    def from_paths(paths: list[str | Path], name: str = "") -> FileSet:
        """Create a FileSet from a list of file paths.

        Automatically determines the common root directory and computes
        relative paths for all files.

        Args:
            paths: List of file or directory paths (absolute or relative)
            name: Optional name for the file set

        Returns:
            New FileSet instance

        Raises:
            ValueError: If paths list is empty
            FileNotFoundError: If any path doesn't exist

        Examples:
            >>> FileSet.from_paths(["C:/project/src/a.py", "C:/project/docs/b.md"])
            FileSet(root_path=Path('C:/project'), relative_paths=[...])
        """
        if not paths:
            raise ValueError("Cannot create FileSet from empty path list")

        # Convert to Path objects and resolve
        path_objs = [Path(p).resolve() for p in paths]

        # Check all paths exist
        for p in path_objs:
            if not p.exists():
                raise FileNotFoundError(f"Path does not exist: {p}")

        # Handle single file case
        if len(path_objs) == 1 and path_objs[0].is_file():
            file_path = path_objs[0]
            return FileSet(
                root_path=file_path.parent,
                relative_paths=[file_path.name],
                name=name or file_path.stem,
            )

        # Collect all files from paths (expand directories)
        all_files: list[Path] = []
        for p in path_objs:
            if p.is_file():
                all_files.append(p)
            elif p.is_dir():
                # Recursively walk directory
                for root, dirs, files in os.walk(p):
                    root_path = Path(root)
                    for file in files:
                        all_files.append(root_path / file)

        if not all_files:
            log_warn("No files found in provided paths")
            return FileSet(
                root_path=path_objs[0] if path_objs[0].is_dir(
                ) else path_objs[0].parent,
                relative_paths=[],
                name=name,
            )

        # Find common ancestor
        root = _find_common_ancestor(all_files)

        # Compute relative paths
        relative = [f.relative_to(root) for f in all_files]

        # Determine name if not provided
        if not name:
            name = root.name if root.name else "files"

        return FileSet(root_path=root, relative_paths=relative, name=name)

    @staticmethod
    def from_directory(directory: str | Path, recursive: bool = True, name: str = "") -> FileSet:
        """Create a FileSet from a directory.

        Args:
            directory: Path to directory
            recursive: Include subdirectories
            name: Optional name for the file set

        Returns:
            New FileSet instance

        Raises:
            FileNotFoundError: If directory doesn't exist
            ValueError: If path is not a directory
        """
        dir_path = Path(directory).resolve()

        if not dir_path.exists():
            raise FileNotFoundError(f"Directory does not exist: {dir_path}")

        if not dir_path.is_dir():
            raise ValueError(f"Path is not a directory: {dir_path}")

        files: list[Path] = []

        if recursive:
            for root, dirs, filenames in os.walk(dir_path):
                root_path = Path(root)
                for filename in filenames:
                    file_path = root_path / filename
                    files.append(file_path.relative_to(dir_path))
        else:
            for item in dir_path.iterdir():
                if item.is_file():
                    files.append(item.relative_to(dir_path))

        return FileSet(
            root_path=dir_path,
            relative_paths=files,
            name=name or dir_path.name,
        )

    def apply_patterns(
        self,
        exclude_patterns: list[str] | None = None,
        include_patterns: list[str] | None = None,
    ) -> FileSet:
        """Filter files using fnmatch patterns.

        Patterns are matched against:
        - Full relative path (e.g., "src/utils/helper.py")
        - Each path component (e.g., "utils", "helper.py")
        - Filename only (e.g., "helper.py")

        Args:
            exclude_patterns: Patterns to exclude (e.g., ["*.pyc", "*.log"])
            include_patterns: Patterns to include (only these will be kept)

        Returns:
            New FileSet with filtered paths

        Examples:
            >>> fs = FileSet.from_directory("project")
            >>> filtered = fs.apply_patterns(exclude_patterns=["*.pyc", "__pycache__"])
        """
        exclude_patterns = exclude_patterns or []
        include_patterns = include_patterns or []

        filtered: list[Path] = []

        for rel_path in self.relative_paths:
            # Convert to string with forward slashes for consistency
            path_str = str(rel_path).replace("\\", "/")
            path_parts = path_str.split("/")
            filename = path_parts[-1]

            # Check exclude patterns
            excluded = False
            for pattern in exclude_patterns:
                # Match against full path
                if fnmatch.fnmatch(path_str, pattern):
                    excluded = True
                    break
                # Match against any path component
                if any(fnmatch.fnmatch(part, pattern) for part in path_parts):
                    excluded = True
                    break
                # Match against filename only
                if fnmatch.fnmatch(filename, pattern):
                    excluded = True
                    break

            if excluded:
                continue

            # Check include patterns (if any)
            if include_patterns:
                included = False
                for pattern in include_patterns:
                    if fnmatch.fnmatch(path_str, pattern):
                        included = True
                        break
                    if any(fnmatch.fnmatch(part, pattern) for part in path_parts):
                        included = True
                        break
                    if fnmatch.fnmatch(filename, pattern):
                        included = True
                        break

                if not included:
                    continue

            filtered.append(rel_path)

        return FileSet(
            root_path=self.root_path,
            relative_paths=filtered,
            name=self.name,
        )

    @property
    def file_count(self) -> int:
        """Get the number of files in this set."""
        return len(self.relative_paths)

    @property
    def total_size(self) -> int:
        """Get total size of all files in bytes."""
        total = 0
        for rel_path in self.relative_paths:
            full_path = self.root_path / rel_path
            if full_path.exists():
                total += full_path.stat().st_size
        return total

    def get_base_name(self) -> str:
        """Get the base name for this file set.

        Returns the explicit name if set, otherwise the root directory name.
        """
        return self.name if self.name else self.root_path.name

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "root_path": str(self.root_path),
            "relative_paths": [str(p) for p in self.relative_paths],
            "name": self.name,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> FileSet:
        """Deserialize from dictionary.

        Args:
            data: Dictionary with root_path, relative_paths, and name keys

        Returns:
            New FileSet instance
        """
        return FileSet(
            root_path=Path(data["root_path"]),
            relative_paths=[Path(p) for p in data.get("relative_paths", [])],
            name=data.get("name", ""),
        )
