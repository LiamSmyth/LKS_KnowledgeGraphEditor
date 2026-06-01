"""Export lks_utils theme objects to CSS custom properties."""
from __future__ import annotations

import dataclasses
from pathlib import Path

from lks_utils.core import atomic_write
from lks_utils.theme.theme import Theme

_PT_TO_PX = 1.333


def _to_kebab_case(name: str) -> str:
    return name.replace("_", "-")


def _font_var_name(field_name: str) -> str:
    if field_name.endswith("_family"):
        base_name = field_name[: -len("_family")]
        return f"--lks-font-{_to_kebab_case(base_name)}-family"
    if field_name.endswith("_size_pt"):
        base_name = field_name[: -len("_size_pt")]
        return f"--lks-font-{_to_kebab_case(base_name)}-size"
    return f"--lks-font-{_to_kebab_case(field_name)}"


def _pt_to_px(value_pt: int) -> int:
    return int(round(float(value_pt) * _PT_TO_PX))


def theme_to_css(theme: Theme) -> str:
    """Convert a Theme object into a CSS stylesheet string."""
    lines: list[str] = [
        "/* Generated from lks_utils.theme - do not edit by hand. */",
        ":root {",
    ]

    for field in dataclasses.fields(theme.palette):
        color_value = getattr(theme.palette, field.name).to_hex()
        lines.append(
            f"  --lks-palette-{_to_kebab_case(field.name)}: {color_value};")

    for field in dataclasses.fields(theme.metrics):
        field_name = field.name
        if field_name.endswith("_px"):
            field_name = field_name[: -len("_px")]
        metric_value = int(getattr(theme.metrics, field.name))
        lines.append(
            f"  --lks-metric-{_to_kebab_case(field_name)}: {metric_value}px;")

    for field in dataclasses.fields(theme.typography):
        value = getattr(theme.typography, field.name)
        var_name = _font_var_name(field.name)
        if field.name.endswith("_pt"):
            lines.append(f"  {var_name}: {_pt_to_px(int(value))}px;")
        else:
            lines.append(f"  {var_name}: \"{value}\";")

    lines.extend(
        [
            "}",
            "",
            "body {",
            "  background: var(--lks-palette-canvas-bg);",
            "  color: var(--lks-palette-text-primary);",
            "  font-family: var(--lks-font-ui-family);",
            "  font-size: var(--lks-font-ui-size);",
            "}",
            "",
            "button {",
            "  background: var(--lks-palette-button-bg);",
            "  color: var(--lks-palette-button-fg);",
            "  border: var(--lks-metric-border) solid var(--lks-palette-border);",
            "  border-radius: var(--lks-metric-button-radius);",
            "  padding: var(--lks-metric-spacing-sm) var(--lks-metric-spacing-md);",
            "}",
            "",
            "input, textarea {",
            "  background: var(--lks-palette-input-bg);",
            "  color: var(--lks-palette-input-fg);",
            "  border: var(--lks-metric-border) solid var(--lks-palette-input-border);",
            "}",
            "",
            "h1, h2, h3 {",
            "  font-size: var(--lks-font-heading-size);",
            "}",
            "",
        ]
    )
    return "\n".join(lines)


def theme_to_css_file(theme: Theme, path: Path) -> None:
    """Write theme CSS to disk atomically."""
    atomic_write(str(path), theme_to_css(theme))


__all__ = ["theme_to_css", "theme_to_css_file"]
