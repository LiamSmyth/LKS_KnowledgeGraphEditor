"""
File Source Utilities - Generic file collection from folders or file selections.

Provides reusable logic for:
- Collecting files from a folder (with optional recursive search)
- Handling direct file selections
- Building file dialog filters from extension sets

This module is framework-agnostic and can be used with both tkinter and Qt.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FileSource:
    """
    Represents a source of files - either a folder to scan or a list of files.

    Attributes:
        folder_path: Path to folder to scan (mutually exclusive with files)
        files: List of specific file paths (mutually exclusive with folder_path)
        recursive: Whether to scan subfolders (only applies to folder_path mode)
    """
    folder_path: Path | None = None
    files: list[Path] = field(default_factory=list)
    recursive: bool = True

    @property
    def is_folder_mode(self) -> bool:
        """Check if source is folder mode."""
        return self.folder_path is not None and not self.files

    @property
    def is_files_mode(self) -> bool:
        """Check if source is files mode."""
        return bool(self.files)

    @property
    def is_valid(self) -> bool:
        """Check if source has valid selection."""
        if self.is_folder_mode:
            return self.folder_path is not None and self.folder_path.exists() and self.folder_path.is_dir()
        elif self.is_files_mode:
            return len(self.files) > 0
        return False

    @property
    def display_text(self) -> str:
        """Get display text for the current selection."""
        if self.is_folder_mode and self.folder_path:
            return str(self.folder_path)
        elif self.is_files_mode:
            if len(self.files) == 1:
                return str(self.files[0])
            return f"{len(self.files)} files selected"
        return ""

    def set_folder(self, path: str | Path) -> None:
        """Set folder mode with given path."""
        self.folder_path = Path(path) if isinstance(path, str) else path
        self.files = []

    def set_files(self, files: list[str | Path]) -> None:
        """Set files mode with given file list."""
        self.files = [Path(f) if isinstance(f, str) else f for f in files]
        self.folder_path = None

    def clear(self) -> None:
        """Clear the selection."""
        self.folder_path = None
        self.files = []

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize to dict for JSON persistence.

        Returns:
            Dict with folder_path, files, and recursive.
        """
        return {
            "folder_path": str(self.folder_path) if self.folder_path else None,
            "files": [str(f) for f in self.files],
            "recursive": self.recursive,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileSource:
        """
        Deserialize from dict.

        Args:
            data: Dict with folder_path, files, recursive.

        Returns:
            FileSource instance.
        """
        folder_path = Path(data["folder_path"]) if data.get(
            "folder_path") else None
        files = [Path(f) for f in data.get("files", [])]
        recursive = data.get("recursive", True)
        return cls(folder_path=folder_path, files=files, recursive=recursive)


def find_files_by_extensions(
    source: FileSource,
    extensions: set[str],
) -> list[Path]:
    """
    Find files matching the given extensions from a FileSource.

    Args:
        source: FileSource specifying folder or file list
        extensions: Set of extensions to match (with leading dot, e.g., {'.mp4', '.avi'})

    Returns:
        List of matching file paths, sorted alphabetically
    """
    if not source.is_valid:
        logger.warning("Invalid file source")
        return []

    # Normalize extensions to lowercase
    extensions_lower: set[str] = {ext.lower() for ext in extensions}

    if source.is_files_mode:
        # Filter provided files by extension
        matching: list[Path] = [
            f for f in source.files
            if f.suffix.lower() in extensions_lower and f.exists()
        ]
        return sorted(matching)

    # Folder mode - scan directory
    folder = source.folder_path
    matching_files: list[Path] = []

    if not folder or not folder.exists():
        logger.error(f"Path does not exist: {folder}")
        return []

    if not folder.is_dir():
        logger.error(f"Path is not a directory: {folder}")
        return []

    if source.recursive:
        for root, _, files in os.walk(folder):
            for filename in files:
                file_path: Path = Path(root) / filename
                if file_path.suffix.lower() in extensions_lower:
                    matching_files.append(file_path)
    else:
        for file_path in folder.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in extensions_lower:
                matching_files.append(file_path)

    return sorted(matching_files)


def build_file_dialog_filter(
    extensions: set[str],
    description: str = "Files"
) -> str:
    """
    Build a file dialog filter string from a set of extensions.

    Args:
        extensions: Set of extensions (with or without leading dot)
        description: Description for the file type group

    Returns:
        Filter string for file dialogs (e.g., "*.mp4 *.avi *.mkv")
    """
    # Normalize: ensure extensions have leading dot and are lowercase
    normalized: list[str] = []
    for ext in sorted(extensions):
        ext = ext.lower()
        if not ext.startswith('.'):
            ext = '.' + ext
        normalized.append(f"*{ext}")

    return ' '.join(normalized)


def get_filetypes_tuple(
    extensions: set[str],
    description: str = "Files",
    include_all_files: bool = True
) -> list[tuple[str, str]]:
    """
    Build filetypes list for file dialogs.

    Args:
        extensions: Set of extensions (with or without leading dot)
        description: Description for the file type group
        include_all_files: Whether to include "All files (*.*)" option

    Returns:
        List of tuples for file dialog filetypes parameter
    """
    filter_str: str = build_file_dialog_filter(extensions, description)
    filetypes: list[tuple[str, str]] = [(description, filter_str)]

    if include_all_files:
        filetypes.append(("All files", "*.*"))

    return filetypes


def collect_files_from_source(
    source: FileSource,
    extensions: list[str] | set[str] | None = None,
) -> list[Path]:
    """Backward-compatible alias for collecting files from a source.

    Args:
        source: File source definition.
        extensions: Optional extensions to filter by.

    Returns:
        Collected file paths.
    """
    if source.is_files_mode:
        files = [f for f in source.files if f.exists()]
        if not extensions:
            return sorted(files)
        ext_set = {e.lower() if e.startswith(
            ".") else f".{e.lower()}" for e in extensions}
        return sorted([f for f in files if f.suffix.lower() in ext_set])

    if not source.folder_path or not source.folder_path.exists():
        return []

    if not extensions:
        if source.recursive:
            return sorted([p for p in source.folder_path.rglob("*") if p.is_file()])
        return sorted([p for p in source.folder_path.iterdir() if p.is_file()])

    ext_set = {e.lower() if e.startswith(
        ".") else f".{e.lower()}" for e in extensions}
    return find_files_by_extensions(source, ext_set)


def build_filter_string(
    extensions: list[str] | set[str],
    description: str = "Files",
) -> str:
    """Backward-compatible alias returning Qt-style filter string.

    Example output: ``Text Files (*.txt *.md)``
    """
    filter_part = build_file_dialog_filter(set(extensions), description)
    return f"{description} ({filter_part})"
