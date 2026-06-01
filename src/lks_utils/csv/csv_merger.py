"""Core logic for merging multiple CSV files.

Provides functionality to:
- Merge multiple CSV files row by row
- Sort by column (alphabetical or numerical)
- Detect and optionally skip duplicate rows
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class SortMode(str, Enum):
    """Sort mode for merged data."""

    NONE = "none"
    ALPHABETICAL = "alphabetical"
    NUMERICAL = "numerical"


@dataclass
class MergeConfig:
    """Configuration for CSV merge operation.

    Attributes:
        input_files: List of CSV file paths to merge
        output_file: Path for merged output CSV
        has_headers: Whether CSV files have a header row
        skip_duplicates: Whether to skip duplicate rows
        sort_column: Column name to sort by (empty for no sorting)
        sort_mode: How to sort (none/alphabetical/numerical)
        include_source_column: Add column with source file name
    """

    input_files: list[str] = field(default_factory=list)
    output_file: str = ""
    has_headers: bool = True
    skip_duplicates: bool = False
    sort_column: str = ""
    sort_mode: SortMode = SortMode.NONE
    include_source_column: bool = False


@dataclass
class MergeResult:
    """Result of merge operation.

    Attributes:
        success: Whether merge was successful
        total_rows: Total rows in merged output
        duplicate_rows_skipped: Number of duplicate rows skipped
        source_file_counts: Dict mapping source file to row count
        error_message: Error message if failed
    """

    success: bool
    total_rows: int = 0
    duplicate_rows_skipped: int = 0
    source_file_counts: dict[str, int] = field(default_factory=dict)
    error_message: str = ""


def merge_csv_files(config: MergeConfig) -> MergeResult:
    """Merge multiple CSV files into one.

    Args:
        config: Merge configuration

    Returns:
        Result of merge operation
    """
    if not config.input_files:
        return MergeResult(success=False, error_message="No input files specified")

    if not config.output_file:
        return MergeResult(success=False, error_message="No output file specified")

    try:
        # Collect all rows from all files
        all_rows: list[dict[str, str]] = []
        source_counts: dict[str, int] = {}
        first_file_headers: list[str] = []
        all_columns: set[str] = set()

        for idx, file_path in enumerate(config.input_files):
            path = Path(file_path)
            if not path.exists():
                return MergeResult(
                    success=False,
                    error_message=f"Input file not found: {file_path}"
                )

            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                if config.has_headers:
                    reader = csv.DictReader(f)

                    # Preserve column order from first file
                    if idx == 0 and reader.fieldnames:
                        first_file_headers = [
                            h for h in reader.fieldnames if h is not None]

                    if reader.fieldnames:
                        valid_headers = [
                            h for h in reader.fieldnames if h is not None]
                        all_columns.update(valid_headers)

                    file_rows = list(reader)
                else:
                    # Headerless CSV: use csv.reader and generate column names
                    raw_reader = csv.reader(f)
                    raw_rows = list(raw_reader)

                    if raw_rows:
                        num_cols = max(len(r) for r in raw_rows)
                        generated_headers = [
                            f"Column_{i + 1}" for i in range(num_cols)]

                        if idx == 0:
                            first_file_headers = generated_headers.copy()
                        all_columns.update(generated_headers)

                        # Convert list rows to dict rows
                        file_rows = []
                        for raw_row in raw_rows:
                            row_dict: dict[str, str] = {}
                            for col_idx, header in enumerate(generated_headers):
                                row_dict[header] = raw_row[col_idx] if col_idx < len(
                                    raw_row) else ""
                            file_rows.append(row_dict)
                    else:
                        file_rows = []

                source_counts[path.name] = len(file_rows)

                # Clean rows: remove None keys and add source column
                for row in file_rows:
                    if None in row:
                        del row[None]
                    if config.include_source_column:
                        row["_source_file"] = path.name

                all_rows.extend(file_rows)

        if not all_rows:
            return MergeResult(success=False, error_message="No data to merge")

        # Build complete header list: preserve first file's column order,
        # then append any new columns from other files (sorted)
        final_headers = first_file_headers.copy()
        for col in sorted(all_columns - set(first_file_headers)):
            final_headers.append(col)

        # Add source column at the end if requested
        if config.include_source_column:
            if "_source_file" not in final_headers:
                final_headers.append("_source_file")
            elif "_source_file" in first_file_headers:
                # Move to end if it was in first file
                final_headers.remove("_source_file")
                final_headers.append("_source_file")

        # Handle duplicate detection
        duplicate_count = 0
        if config.skip_duplicates:
            seen_rows: set[tuple[tuple[str, str], ...]] = set()
            unique_rows: list[dict[str, str]] = []

            for row in all_rows:
                # Create a hashable representation (sorted tuple of items)
                row_tuple = tuple(sorted(row.items()))
                if row_tuple not in seen_rows:
                    seen_rows.add(row_tuple)
                    unique_rows.append(row)
                else:
                    duplicate_count += 1

            all_rows = unique_rows

        # Handle sorting
        if config.sort_mode != SortMode.NONE and config.sort_column:
            if config.sort_column in final_headers:
                if config.sort_mode == SortMode.NUMERICAL:
                    # Try numeric sort, fallback to alphabetical on error
                    def numeric_key(row: dict[str, str]) -> float | str:
                        try:
                            return float(row.get(config.sort_column, "0"))
                        except ValueError:
                            return row.get(config.sort_column, "")

                    all_rows.sort(key=numeric_key)
                else:  # ALPHABETICAL
                    all_rows.sort(key=lambda row: row.get(
                        config.sort_column, ""))

        # Write merged output
        output_path = Path(config.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=final_headers)
            writer.writeheader()
            writer.writerows(all_rows)

        return MergeResult(
            success=True,
            total_rows=len(all_rows),
            duplicate_rows_skipped=duplicate_count,
            source_file_counts=source_counts,
        )

    except Exception as e:
        return MergeResult(
            success=False,
            error_message=f"Merge failed: {str(e)}"
        )
