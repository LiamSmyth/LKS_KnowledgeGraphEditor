"""
Path manipulation utilities.

Provides helpers for parsing, normalizing, and manipulating file paths.
"""
from __future__ import annotations

from lks_utils.path.file_set import FileSet
from lks_utils.path.pattern_presets import (
    PatternPreset,
    list_presets,
    load_preset,
    save_preset,
    delete_preset,
    export_preset,
    import_preset,
    get_combined_patterns,
)
from lks_utils.path.path_utils import parse_path_string, paths_to_string, normalize_path, get_parent_directory, get_filename, get_file_extension, join_paths, path_exists, is_file, is_directory, get_path_parts, change_extension, make_safe_filename, ensure_extension, is_folder_empty, find_empty_folders, safe_rmdir, walk_folders, find_files_by_extension, is_unc_path, is_network_path, get_drive_type, is_docker_accessible_path, DRIVE_UNKNOWN, DRIVE_NO_ROOT_DIR, DRIVE_REMOVABLE, DRIVE_FIXED, DRIVE_REMOTE, DRIVE_CDROM, DRIVE_RAMDISK

__all__ = [
    # File sets
    "FileSet",
    # Pattern presets
    "PatternPreset",
    "list_presets",
    "load_preset",
    "save_preset",
    "delete_preset",
    "export_preset",
    "import_preset",
    "get_combined_patterns",
    # Path utilities
    "parse_path_string",
    "paths_to_string",
    "normalize_path",
    "get_parent_directory",
    "get_filename",
    "get_file_extension",
    "join_paths",
    "path_exists",
    "is_file",
    "is_directory",
    "get_path_parts",
    "change_extension",
    "make_safe_filename",
    "ensure_extension",
    # Directory operations
    "is_folder_empty",
    "find_empty_folders",
    "safe_rmdir",
    "walk_folders",
    "find_files_by_extension",
    # Windows path utilities
    "is_unc_path",
    "is_network_path",
    "get_drive_type",
    "is_docker_accessible_path",
    # Drive type constants
    "DRIVE_UNKNOWN",
    "DRIVE_NO_ROOT_DIR",
    "DRIVE_REMOVABLE",
    "DRIVE_FIXED",
    "DRIVE_REMOTE",
    "DRIVE_CDROM",
    "DRIVE_RAMDISK",
]
