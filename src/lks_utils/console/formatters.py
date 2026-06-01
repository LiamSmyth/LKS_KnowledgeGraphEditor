"""
Console output formatters for tables, panels, progress bars, and values.

Provides beautiful console output with ASCII/Unicode box drawing characters
and proper alignment. Falls back to simpler formatting when colors or
Unicode are not supported.

Usage:
    from lks_utils.console.formatters import Table, Panel, format_duration
    
    # Create a table
    table = Table(["Name", "Value", "Status"])
    table.add_row(["load", "1.23s", "OK"])
    table.add_row(["encode", "4.56s", "SLOW"])
    print(table.render())
    
    # Format values
    print(format_duration(1.234))  # "1.23s"
    print(format_size(1024 * 1024))  # "1.00 MB"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lks_utils.console.colors import RESET, SemanticColor, get_color_enabled, strip_ansi, style_text, colorize_by_duration, colorize_by_percentage

# Box drawing characters
BOX_HORIZONTAL: str = "─"
BOX_VERTICAL: str = "│"
BOX_TOP_LEFT: str = "┌"
BOX_TOP_RIGHT: str = "┐"
BOX_BOTTOM_LEFT: str = "└"
BOX_BOTTOM_RIGHT: str = "┘"
BOX_CROSS: str = "┼"
BOX_T_DOWN: str = "┬"
BOX_T_UP: str = "┴"
BOX_T_RIGHT: str = "├"
BOX_T_LEFT: str = "┤"

def format_duration(
    seconds: float,
    precision: int = 2,
    colorize: bool = True,
    thresholds: tuple[float, float] = (1.0, 5.0),
) -> str:
    """
    Format a duration in seconds to a human-readable string.

    Args:
        seconds: Duration in seconds
        precision: Decimal places for display
        colorize: Whether to apply color based on speed
        thresholds: (fast, slow) thresholds for coloring

    Returns:
        Formatted duration string like "1.23s" or "2m 30s"

    Examples:
        >>> format_duration(0.5)
        '0.50s'
        >>> format_duration(125.5)
        '2m 5.50s'
    """
    if seconds < 0:
        seconds = 0.0

    # Format based on magnitude
    if seconds < 60:
        if seconds < 0.001:
            text: str = f"{seconds * 1000000:.0f}us"
        elif seconds < 1:
            text = f"{seconds * 1000:.{precision}f}ms"
        else:
            text = f"{seconds:.{precision}f}s"
    elif seconds < 3600:
        minutes: int = int(seconds // 60)
        secs: float = seconds % 60
        text = f"{minutes}m {secs:.{precision}f}s"
    else:
        hours: int = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        text = f"{hours}h {minutes}m {secs:.0f}s"

    if colorize and get_color_enabled():
        color: SemanticColor = colorize_by_duration(seconds, thresholds)
        return style_text(text, color)

    return text

def format_percentage(
    value: float,
    precision: int = 1,
    colorize: bool = False,
    invert: bool = False,
) -> str:
    """
    Format a percentage value.

    Args:
        value: Percentage value (0-100)
        precision: Decimal places
        colorize: Whether to apply color
        invert: If True, high values are bad (e.g., CPU usage)

    Returns:
        Formatted percentage string like "75.5%"
    """
    text: str = f"{value:.{precision}f}%"

    if colorize and get_color_enabled():
        color: SemanticColor = colorize_by_percentage(value, invert=invert)
        return style_text(text, color)

    return text

def format_size(
    bytes_value: int | float,
    precision: int = 2,
    binary: bool = True,
) -> str:
    """
    Format a byte size to human-readable string.

    Args:
        bytes_value: Size in bytes
        precision: Decimal places
        binary: Use binary (1024) vs decimal (1000) units

    Returns:
        Formatted size string like "1.23 MB" or "1.23 MiB"
    """
    if bytes_value < 0:
        bytes_value = 0

    if binary:
        units: list[str] = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
        divisor: int = 1024
    else:
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        divisor = 1000

    value: float = float(bytes_value)
    unit_index: int = 0

    while value >= divisor and unit_index < len(units) - 1:
        value /= divisor
        unit_index += 1

    if unit_index == 0:
        return f"{int(value)} {units[unit_index]}"

    return f"{value:.{precision}f} {units[unit_index]}"

def create_progress_bar(
    progress: float,
    width: int = 30,
    filled_char: str = "█",
    empty_char: str = "░",
    colorize: bool = True,
) -> str:
    """
    Create an ASCII progress bar.

    Args:
        progress: Progress value 0.0 to 1.0
        width: Width of the bar in characters
        filled_char: Character for filled portion
        empty_char: Character for empty portion
        colorize: Whether to colorize based on progress

    Returns:
        Progress bar string like "[████████░░░░] 66%"
    """
    progress = max(0.0, min(1.0, progress))
    filled_width: int = int(width * progress)
    empty_width: int = width - filled_width

    bar: str = filled_char * filled_width + empty_char * empty_width
    percentage: str = f"{progress * 100:.0f}%"

    if colorize and get_color_enabled():
        if progress < 0.33:
            bar = style_text(bar, SemanticColor.ERROR)
        elif progress < 0.66:
            bar = style_text(bar, SemanticColor.WARNING)
        else:
            bar = style_text(bar, SemanticColor.SUCCESS)

    return f"[{bar}] {percentage}"

@dataclass
class Table:
    """
    A simple ASCII table renderer with optional colors.

    Usage:
        table = Table(["Name", "Duration", "Status"])
        table.add_row(["load", "1.23s", "OK"])
        table.add_row(["encode", "4.56s", "SLOW"])
        print(table.render())

    Output:
        ┌──────────┬──────────┬────────┐
        │ Name     │ Duration │ Status │
        ├──────────┼──────────┼────────┤
        │ load     │ 1.23s    │ OK     │
        │ encode   │ 4.56s    │ SLOW   │
        └──────────┴──────────┴────────┘
    """

    headers: list[str]
    rows: list[list[str]] = field(default_factory=list)
    padding: int = 1
    min_width: int = 3

    def add_row(self, row: list[Any]) -> None:
        """Add a row to the table."""
        self.rows.append([str(cell) for cell in row])

    def _get_column_widths(self) -> list[int]:
        """Calculate the width of each column."""
        widths: list[int] = [
            max(self.min_width, len(strip_ansi(h))) for h in self.headers
        ]

        for row in self.rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    cell_width: int = len(strip_ansi(cell))
                    widths[i] = max(widths[i], cell_width)

        return widths

    def _pad_cell(self, cell: str, width: int) -> str:
        """Pad a cell to the given width, accounting for ANSI codes."""
        visible_len: int = len(strip_ansi(cell))
        padding_needed: int = width - visible_len
        return cell + " " * padding_needed

    def render(self, use_unicode: bool = True) -> str:
        """
        Render the table to a string.

        Args:
            use_unicode: Use Unicode box drawing characters

        Returns:
            Rendered table string
        """
        widths: list[int] = self._get_column_widths()
        pad: str = " " * self.padding

        # Box characters
        if use_unicode:
            h, v = BOX_HORIZONTAL, BOX_VERTICAL
            tl, tr = BOX_TOP_LEFT, BOX_TOP_RIGHT
            bl, br = BOX_BOTTOM_LEFT, BOX_BOTTOM_RIGHT
            td, tu = BOX_T_DOWN, BOX_T_UP
            tl_mid, tr_mid = BOX_T_RIGHT, BOX_T_LEFT
            cross = BOX_CROSS
        else:
            h, v = "-", "|"
            tl, tr, bl, br = "+", "+", "+", "+"
            td, tu, tl_mid, tr_mid, cross = "+", "+", "+", "+", "+"

        lines: list[str] = []

        # Top border
        top_border: str = tl
        for i, w in enumerate(widths):
            top_border += h * (w + 2 * self.padding)
            top_border += td if i < len(widths) - 1 else tr
        lines.append(top_border)

        # Header row
        header_line: str = v
        for i, header in enumerate(self.headers):
            cell: str = self._pad_cell(header, widths[i])
            if get_color_enabled():
                cell = style_text(cell, SemanticColor.PRIMARY, bold=True)
            header_line += f"{pad}{cell}{pad}{v}"
        lines.append(header_line)

        # Header separator
        sep_line: str = tl_mid
        for i, w in enumerate(widths):
            sep_line += h * (w + 2 * self.padding)
            sep_line += cross if i < len(widths) - 1 else tr_mid
        lines.append(sep_line)

        # Data rows
        for row in self.rows:
            row_line: str = v
            for i, cell in enumerate(row):
                width: int = widths[i] if i < len(widths) else self.min_width
                padded: str = self._pad_cell(cell, width)
                row_line += f"{pad}{padded}{pad}{v}"
            lines.append(row_line)

        # Bottom border
        bottom_border: str = bl
        for i, w in enumerate(widths):
            bottom_border += h * (w + 2 * self.padding)
            bottom_border += tu if i < len(widths) - 1 else br
        lines.append(bottom_border)

        return "\n".join(lines)

@dataclass
class Panel:
    """
    A bordered panel for displaying grouped content.

    Usage:
        panel = Panel("Summary", ["Total: 100", "Success: 95", "Failed: 5"])
        print(panel.render())

    Output:
        ┌─ Summary ──────────────┐
        │ Total: 100             │
        │ Success: 95            │
        │ Failed: 5              │
        └────────────────────────┘
    """

    title: str
    content: list[str]
    min_width: int = 20
    padding: int = 1

    def render(self, use_unicode: bool = True) -> str:
        """
        Render the panel to a string.

        Args:
            use_unicode: Use Unicode box drawing characters

        Returns:
            Rendered panel string
        """
        # Calculate width
        content_widths: list[int] = [
            len(strip_ansi(line)) for line in self.content]
        title_width: int = len(strip_ansi(self.title)) + \
            4  # " Title " with padding
        max_content: int = max(content_widths) if content_widths else 0
        inner_width: int = max(self.min_width, title_width,
                               max_content + 2 * self.padding)

        # Box characters
        if use_unicode:
            h, v = BOX_HORIZONTAL, BOX_VERTICAL
            tl, tr = BOX_TOP_LEFT, BOX_TOP_RIGHT
            bl, br = BOX_BOTTOM_LEFT, BOX_BOTTOM_RIGHT
        else:
            h, v = "-", "|"
            tl, tr, bl, br = "+", "+", "+", "+"

        lines: list[str] = []

        # Top border with title
        styled_title: str = self.title
        if get_color_enabled():
            styled_title = style_text(
                self.title, SemanticColor.HIGHLIGHT, bold=True)

        title_section: str = f"{h} {styled_title} "
        title_visible_len: int = len(strip_ansi(title_section))
        remaining: int = inner_width - title_visible_len
        top_border: str = f"{tl}{title_section}{h * remaining}{tr}"
        lines.append(top_border)

        # Content lines
        pad: str = " " * self.padding
        for line in self.content:
            visible_len: int = len(strip_ansi(line))
            padding_needed: int = inner_width - visible_len - 2 * self.padding
            lines.append(f"{v}{pad}{line}{' ' * padding_needed}{pad}{v}")

        # Bottom border
        bottom_border: str = f"{bl}{h * inner_width}{br}"
        lines.append(bottom_border)

        return "\n".join(lines)

def format_key_value(
    key: str,
    value: Any,
    key_width: int = 15,
    separator: str = ":",
    colorize_key: bool = True,
) -> str:
    """
    Format a key-value pair with aligned output.

    Args:
        key: The key/label
        value: The value
        key_width: Width to pad the key to
        separator: Separator between key and value
        colorize_key: Whether to colorize the key

    Returns:
        Formatted string like "Name:           example"
    """
    padded_key: str = key.ljust(key_width)

    if colorize_key and get_color_enabled():
        padded_key = style_text(padded_key, SemanticColor.MUTED)

    return f"{padded_key}{separator} {value}"

def format_list_item(
    item: str,
    bullet: str = "•",
    indent: int = 2,
    colorize_bullet: bool = True,
) -> str:
    """
    Format a list item with a bullet point.

    Args:
        item: The item text
        bullet: Bullet character
        indent: Spaces before bullet
        colorize_bullet: Whether to colorize the bullet

    Returns:
        Formatted list item like "  • Item text"
    """
    prefix: str = " " * indent

    if colorize_bullet and get_color_enabled():
        bullet = style_text(bullet, SemanticColor.MUTED)

    return f"{prefix}{bullet} {item}"
