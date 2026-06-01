"""
Pattern preset management for file filtering.

Provides reusable pattern collections for excluding/including files,
similar to .gitignore functionality. Supports built-in presets and
custom user presets stored in JSON format.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lks_utils.logging import log_debug, log_warn


@dataclass
class PatternPreset:
    """A named collection of file patterns.

    Attributes:
        name: Preset identifier (e.g., "version_control")
        description: Human-readable description
        patterns: List of fnmatch patterns
        category: Grouping category (builtin/custom)
    """
    name: str
    description: str
    patterns: list[str]
    category: str = "custom"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "patterns": self.patterns,
            "category": self.category,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> PatternPreset:
        """Deserialize from dictionary."""
        return PatternPreset(
            name=data["name"],
            description=data["description"],
            patterns=data.get("patterns", []),
            category=data.get("category", "custom"),
        )


def get_presets_directory() -> Path:
    """Get the directory containing preset files.

    Returns bundled presets directory: data/pattern_presets/
    """
    return Path(__file__).parent / "data" / "pattern_presets"


def list_presets() -> list[PatternPreset]:
    """List all available pattern presets.

    Returns:
        List of PatternPreset objects (bundled + custom)
    """
    presets: list[PatternPreset] = []
    presets_dir = get_presets_directory()

    if not presets_dir.exists():
        log_warn("pattern_presets",
                 f"Presets directory not found: {presets_dir}")
        return presets

    # Load all JSON files
    for json_file in presets_dir.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                preset = PatternPreset.from_dict(data)
                presets.append(preset)
        except Exception as e:
            log_warn("pattern_presets",
                     f"Failed to load preset {json_file.name}: {e}")

    return presets


def load_preset(name: str) -> PatternPreset:
    """Load a preset by name.

    Args:
        name: Preset name (without .json extension)

    Returns:
        PatternPreset object

    Raises:
        FileNotFoundError: If preset doesn't exist
    """
    presets_dir = get_presets_directory()
    json_file = presets_dir / f"{name}.json"

    if not json_file.exists():
        raise FileNotFoundError(f"Preset not found: {name}")

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        return PatternPreset.from_dict(data)


def save_preset(preset: PatternPreset, overwrite: bool = False) -> Path:
    """Save a pattern preset to the presets directory.

    Args:
        preset: PatternPreset to save
        overwrite: Allow overwriting existing preset

    Returns:
        Path to saved preset file

    Raises:
        FileExistsError: If preset exists and overwrite=False
    """
    presets_dir = get_presets_directory()
    presets_dir.mkdir(parents=True, exist_ok=True)

    json_file = presets_dir / f"{preset.name}.json"

    if json_file.exists() and not overwrite:
        raise FileExistsError(f"Preset already exists: {preset.name}")

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(preset.to_dict(), f, indent=2)

    log_debug("pattern_presets", f"Saved preset: {preset.name}")
    return json_file


def delete_preset(name: str, allow_builtin: bool = False) -> bool:
    """Delete a preset by name.

    Args:
        name: Preset name
        allow_builtin: Allow deleting builtin presets (dangerous)

    Returns:
        True if deleted, False if not found

    Raises:
        ValueError: If trying to delete builtin preset without allow_builtin=True
    """
    # Load preset to check category
    try:
        preset = load_preset(name)
    except FileNotFoundError:
        return False

    if preset.category == "builtin" and not allow_builtin:
        raise ValueError(f"Cannot delete builtin preset: {name}")

    presets_dir = get_presets_directory()
    json_file = presets_dir / f"{name}.json"

    if json_file.exists():
        json_file.unlink()
        log_debug("pattern_presets", f"Deleted preset: {name}")
        return True

    return False


def export_preset(preset: PatternPreset, output_path: Path) -> None:
    """Export preset to a specific file path.

    Args:
        preset: PatternPreset to export
        output_path: Where to save the preset
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(preset.to_dict(), f, indent=2)

    log_debug("pattern_presets", f"Exported preset to: {output_path}")


def import_preset(input_path: Path) -> PatternPreset:
    """Import preset from a file.

    Args:
        input_path: Path to preset JSON file

    Returns:
        Loaded PatternPreset

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is invalid
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Preset file not found: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        return PatternPreset.from_dict(data)


def get_combined_patterns(preset_names: list[str]) -> list[str]:
    """Get combined patterns from multiple presets.

    Args:
        preset_names: List of preset names to combine

    Returns:
        Deduplicated list of all patterns
    """
    if not preset_names:
        return []

    all_patterns: set[str] = set()

    for name in preset_names:
        try:
            preset = load_preset(name)
            all_patterns.update(preset.patterns)
        except FileNotFoundError:
            log_warn("pattern_presets", f"Preset not found: {name}")

    return sorted(all_patterns)
