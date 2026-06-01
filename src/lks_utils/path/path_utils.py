"""
Path manipulation utilities.

Provides helpers for parsing, normalizing, and manipulating file paths.
Works with pathlib internally while accepting and returning string paths.

Usage:
    from lks_utils.path import parse_path_string, normalize_path, get_filename

    # Parse semicolon-separated paths
    paths = parse_path_string("C:/a.txt;C:/b.txt")  # ['C:/a.txt', 'C:/b.txt']

    # Normalize path
    norm = normalize_path("./foo/../bar")  # Resolved absolute path

    # Get filename with or without extension
    name = get_filename("/path/to/file.txt")  # "file.txt"
    stem = get_filename("/path/to/file.txt", with_extension=False)  # "file"
"""
from __future__ import annotations

from pathlib import Path
import ctypes
import os
import re
from lks_utils.text.sanitization import clamp_length, ensure_non_empty, remove_filesystem_unsafe_chars, strip_leading_trailing_chars

# Default values
DEFAULT_PATH_SEPARATOR: str = ";"
DEFAULT_MAX_FILENAME_LENGTH: int = 255
DEFAULT_FALLBACK_FILENAME: str = "file"

# Unsafe filesystem characters (Windows)
UNSAFE_FILESYSTEM_CHARS: str = '<>:"/\\|?*'
MIN_PRINTABLE_CHAR_CODE: int = 32

def parse_path_string(path_string: str, separator: str = DEFAULT_PATH_SEPARATOR) -> list[str]:
    """Parse a separator-delimited path string into a list of paths.

    Args:
        path_string: String containing paths separated by `separator`.
        separator: Delimiter between paths (default: ";").

    Returns:
        List of individual path strings, stripped of whitespace.
        Empty strings are filtered out.

    Examples:
        >>> parse_path_string("C:/a.txt;C:/b.txt")
        ['C:/a.txt', 'C:/b.txt']
        >>> parse_path_string("  a.txt ; b.txt ; ")
        ['a.txt', 'b.txt']
    """
    if not path_string or path_string.strip() == "":
        return []

    paths: list[str] = path_string.split(separator)
    return [path.strip() for path in paths if path.strip()]

def paths_to_string(paths: list[str], separator: str = DEFAULT_PATH_SEPARATOR) -> str:
    """Convert a list of paths to a separator-delimited string.

    Args:
        paths: List of path strings.
        separator: Delimiter between paths (default: ";").

    Returns:
        Joined string of paths.

    Examples:
        >>> paths_to_string(['C:/a.txt', 'C:/b.txt'])
        'C:/a.txt;C:/b.txt'
    """
    if not paths:
        return ""
    return separator.join(str(path) for path in paths)

def normalize_path(path: str) -> str:
    """Normalize a path to an absolute, resolved path string.

    Args:
        path: Path string to normalize.

    Returns:
        Absolute, normalized path string.

    Examples:
        >>> normalize_path("./foo/../bar")  # doctest: +SKIP
        'C:/current/bar'  # (actual result depends on cwd)
    """
    try:
        return str(Path(path).resolve())
    except Exception:
        return str(path)

def get_parent_directory(path: str) -> str:
    """Get the parent directory of a path.

    Args:
        path: Path string.

    Returns:
        Parent directory as string.

    Examples:
        >>> get_parent_directory("/home/user/file.txt")
        '/home/user'
    """
    try:
        return str(Path(path).parent)
    except Exception:
        return str(path)

def get_filename(path: str, with_extension: bool = True) -> str:
    """Get the filename from a path.

    Args:
        path: Path string.
        with_extension: If True, include extension; if False, return stem only.

    Returns:
        Filename as string.

    Examples:
        >>> get_filename("/path/to/file.txt")
        'file.txt'
        >>> get_filename("/path/to/file.txt", with_extension=False)
        'file'
    """
    try:
        p = Path(path)
        if with_extension:
            return p.name
        else:
            return p.stem
    except Exception:
        return str(path)

def get_file_extension(path: str) -> str:
    """Get the file extension from a path (including the dot).

    Args:
        path: Path string.

    Returns:
        Extension string including dot (e.g., ".txt"), or empty string.

    Examples:
        >>> get_file_extension("/path/to/file.txt")
        '.txt'
        >>> get_file_extension("/path/to/file")
        ''
    """
    try:
        return Path(path).suffix
    except Exception:
        return ""

def join_paths(base_path: str, *parts: str) -> str:
    """Join path components safely.

    Args:
        base_path: Base path.
        *parts: Additional path components to join.

    Returns:
        Joined path as string.

    Examples:
        >>> join_paths("/home", "user", "file.txt")
        '/home/user/file.txt'
    """
    try:
        return str(Path(base_path).joinpath(*parts))
    except Exception:
        return str(base_path)

def path_exists(path: str) -> bool:
    """Check if a path exists.

    Args:
        path: Path string to check.

    Returns:
        True if path exists, False otherwise.
    """
    try:
        return Path(path).exists()
    except Exception:
        return False

def is_file(path: str) -> bool:
    """Check if path is a file.

    Args:
        path: Path string to check.

    Returns:
        True if path is a file, False otherwise.
    """
    try:
        return Path(path).is_file()
    except Exception:
        return False

def is_directory(path: str) -> bool:
    """Check if path is a directory.

    Args:
        path: Path string to check.

    Returns:
        True if path is a directory, False otherwise.
    """
    try:
        return Path(path).is_dir()
    except Exception:
        return False

def get_path_parts(path: str) -> list[str]:
    """Get all parts of a path as a list.

    Args:
        path: Path string.

    Returns:
        List of path components.

    Examples:
        >>> get_path_parts("/home/user/file.txt")
        ['/', 'home', 'user', 'file.txt']
    """
    try:
        return list(Path(path).parts)
    except Exception:
        return [str(path)]

def change_extension(path: str, new_extension: str) -> str:
    """Change the extension of a path.

    Args:
        path: Original path string.
        new_extension: New extension (with or without leading dot).

    Returns:
        Path with new extension.

    Examples:
        >>> change_extension("/path/to/file.txt", ".json")
        '/path/to/file.json'
        >>> change_extension("/path/to/file.txt", "json")
        '/path/to/file.json'
    """
    try:
        p = Path(path)
        if not new_extension.startswith("."):
            new_extension = "." + new_extension
        return str(p.with_suffix(new_extension))
    except Exception:
        return str(path)

def ensure_extension(path: str, extension: str) -> str:
    """Ensure a path has a specific extension.

    If the path already has the extension, it is returned unchanged.
    Otherwise, the extension is appended.

    Args:
        path: Path string.
        extension: Extension to ensure (with or without leading dot).

    Returns:
        Path with the specified extension.
    """
    if not extension.startswith("."):
        extension = "." + extension

    if path.lower().endswith(extension.lower()):
        return path

    return path + extension

def make_safe_filename(filename: str, max_length: int = DEFAULT_MAX_FILENAME_LENGTH) -> str:
    """Make a filename safe for filesystem use.

    Args:
        filename: Original filename.
        max_length: Maximum allowed filename length.

    Returns:
        Sanitized filename safe for all major filesystems.

    Examples:
        >>> make_safe_filename('file<>:name.txt')
        'file___name.txt'
    """
    safe_filename: str = remove_filesystem_unsafe_chars(filename)
    # Remove control characters
    safe_filename = "".join(
        char for char in safe_filename if ord(char) >= MIN_PRINTABLE_CHAR_CODE)
    safe_filename = clamp_length(
        safe_filename, max_length, preserve_extension=True)
    safe_filename = strip_leading_trailing_chars(safe_filename, " ")
    safe_filename = ensure_non_empty(
        safe_filename, DEFAULT_FALLBACK_FILENAME)

    return safe_filename
# =============================================================================
# Directory/Folder Operations
# =============================================================================

def is_folder_empty(folder_path: str) -> bool:
    """Check if a folder is empty (no files or subdirectories).

    Args:
        folder_path: Path to check.

    Returns:
        True if folder exists and is empty, False otherwise.
        Returns False on permission errors or if path doesn't exist.

    Examples:
        >>> is_folder_empty("/path/to/empty_folder")
        True
        >>> is_folder_empty("/path/to/folder_with_files")
        False
    """
    try:
        p = Path(folder_path)
        if not p.exists() or not p.is_dir():
            return False
        return not any(p.iterdir())
    except (PermissionError, OSError):
        return False

def find_empty_folders(base_path: str, recursive: bool = True) -> list[str]:
    """Find all empty folders in the given path.

    Args:
        base_path: Base directory to search.
        recursive: If True, search all subdirectories.

    Returns:
        Sorted list of empty folder paths (as strings).

    Raises:
        RuntimeError: If there's an error accessing the path.

    Examples:
        >>> empty = find_empty_folders("/path/to/search")
        >>> for folder in empty:
        ...     print(folder)
    """
    p = Path(base_path)
    if not p.exists():
        raise RuntimeError(f"Path does not exist: {base_path}")
    if not p.is_dir():
        raise RuntimeError(f"Path is not a directory: {base_path}")

    empty_folders = []

    try:
        if recursive:
            # Use walk bottom-up to find empty folders
            for root, dirs, files in os.walk(str(p), topdown=False):
                root_path = Path(root)
                for dir_name in dirs:
                    dir_path = root_path / dir_name
                    if is_folder_empty(str(dir_path)):
                        empty_folders.append(str(dir_path))
        else:
            # Non-recursive: only check immediate subdirectories
            for item in p.iterdir():
                if item.is_dir() and is_folder_empty(str(item)):
                    empty_folders.append(str(item))

    except (PermissionError, OSError) as e:
        raise RuntimeError(f"Error accessing path: {e}")

    return sorted(empty_folders)

def safe_rmdir(folder_path: str) -> bool:
    """Safely remove an empty directory.

    Args:
        folder_path: Path to the directory to remove.

    Returns:
        True if removal succeeded, False otherwise.

    Notes:
        Only removes empty directories. Will fail silently if
        directory is not empty or doesn't exist.
    """
    try:
        Path(folder_path).rmdir()
        return True
    except (OSError, PermissionError):
        return False

def walk_folders(
    base_path: str,
    recursive: bool = True,
    include_base: bool = False,
) -> list[str]:
    """Get list of folders in a directory.

    Args:
        base_path: Base directory to walk.
        recursive: If True, walk all subdirectories.
        include_base: If True, include the base path itself.

    Returns:
        Sorted list of folder paths.

    Examples:
        >>> folders = walk_folders("/path/to/dir", recursive=True)
    """
    p = Path(base_path)
    if not p.exists() or not p.is_dir():
        return []

    folders = []
    if include_base:
        folders.append(str(p))

    try:
        if recursive:
            for item in p.rglob("*"):
                if item.is_dir():
                    folders.append(str(item))
        else:
            for item in p.iterdir():
                if item.is_dir():
                    folders.append(str(item))
    except (PermissionError, OSError):
        pass

    return sorted(folders)

def find_files_by_extension(
    base_path: str,
    extensions: set,
    recursive: bool = True,
) -> list[str]:
    """Find files matching given extensions.

    Args:
        base_path: Base directory to search.
        extensions: Set of extensions to match (with or without leading dot).
        recursive: If True, search subdirectories.

    Returns:
        Sorted list of matching file paths.

    Examples:
        >>> files = find_files_by_extension("/path", {".txt", ".md"})
        >>> files = find_files_by_extension("/path", {"txt", "md"})
    """
    p = Path(base_path)
    if not p.exists() or not p.is_dir():
        return []

    # Normalize extensions to lowercase with leading dot
    normalized_exts = set()
    for ext in extensions:
        ext_lower = ext.lower()
        if not ext_lower.startswith("."):
            ext_lower = "." + ext_lower
        normalized_exts.add(ext_lower)

    matching = []

    try:
        if recursive:
            for root, _, files in os.walk(str(p)):
                for filename in files:
                    file_path = Path(root) / filename
                    if file_path.suffix.lower() in normalized_exts:
                        matching.append(str(file_path))
        else:
            for item in p.iterdir():
                if item.is_file() and item.suffix.lower() in normalized_exts:
                    matching.append(str(item))
    except (PermissionError, OSError):
        pass

    return sorted(matching)

# =============================================================================
# Windows Path Utilities
# =============================================================================

# Windows drive type constants
DRIVE_UNKNOWN: int = 0
DRIVE_NO_ROOT_DIR: int = 1
DRIVE_REMOVABLE: int = 2
DRIVE_FIXED: int = 3
DRIVE_REMOTE: int = 4
DRIVE_CDROM: int = 5
DRIVE_RAMDISK: int = 6

def is_unc_path(path: str | Path) -> bool:
    """Check if a path is a UNC path (\\\\server\\share).

    Args:
        path: Path to check (string or Path object)

    Returns:
        True if the path starts with \\\\ (UNC format)

    Examples:
        >>> is_unc_path("\\\\\\\\server\\\\share\\\\folder")
        True
        >>> is_unc_path("C:\\\\Users")
        False
    """
    path_str = str(path)
    return path_str.startswith("\\\\")

def is_network_path(path: str | Path) -> bool:
    """Check if a path is on a network/remote drive.

    Detects both UNC paths (\\\\server\\share) and mapped network drives (Z:).
    Uses Windows API on Windows, path heuristics on other platforms.

    Args:
        path: Path to check (string or Path object)

    Returns:
        True if the path is on a network location

    Examples:
        >>> is_network_path("\\\\\\\\server\\\\share")  # UNC path
        True
        >>> is_network_path("Z:\\\\backup")  # Mapped network drive
        True  # (if Z: is mapped to a network location)
        >>> is_network_path("C:\\\\Users")  # Local drive
        False
    """
    path_obj = Path(path)

    # Resolve to get actual path (Z: might resolve to UNC)
    try:
        resolved = str(path_obj.resolve())
    except (OSError, ValueError):
        resolved = str(path_obj)

    # Check for UNC path
    if resolved.startswith("\\\\"):
        return True

    # Check drive letter on Windows
    if len(resolved) >= 2 and resolved[1] == ":":
        drive_letter = resolved[0].upper()
        drive_type = get_drive_type(drive_letter)
        return drive_type == DRIVE_REMOTE

    return False

def get_drive_type(drive_letter: str) -> int:
    """Get the type of a Windows drive.

    Args:
        drive_letter: Single letter (e.g., 'C', 'Z') or with colon (e.g., 'C:')

    Returns:
        Drive type constant:
        - DRIVE_UNKNOWN (0): Unknown
        - DRIVE_NO_ROOT_DIR (1): Invalid root path
        - DRIVE_REMOVABLE (2): Removable (USB, etc.)
        - DRIVE_FIXED (3): Fixed (internal HDD/SSD)
        - DRIVE_REMOTE (4): Network drive
        - DRIVE_CDROM (5): CD-ROM
        - DRIVE_RAMDISK (6): RAM disk

        Returns DRIVE_UNKNOWN on non-Windows or on error.
    """
        # Strip colon if present (accept both 'C' and 'C:')
    letter = drive_letter[0].upper()
    return ctypes.windll.kernel32.GetDriveTypeW(f"{letter}:\\")
def is_docker_accessible_path(path: str | Path) -> bool:
    """Check if a path is directly accessible by Docker Desktop.

    Docker Desktop on Windows cannot directly mount:
    - UNC paths (\\\\server\\share)
    - Network/mapped drives (Z: pointing to network)

    Args:
        path: Path to check

    Returns:
        True if Docker can mount this path directly
    """
    return not is_network_path(path)
