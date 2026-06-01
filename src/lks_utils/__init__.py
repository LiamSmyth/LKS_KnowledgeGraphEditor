"""
lks_utils - Shared utilities for LKS projects.

Configuration via environment variables:
- LKS_VERBOSE_LOGGING: Set to "1" to enable debug logging (default: "0")
- LKS_PATCH_PRINT: Set to "0" to disable global print normalization (default: "1")

Quick usage:
    from lks_utils import log_info, log_warn, log_error, log_debug
    log_info("MyComponent", "Processing complete")

Available submodules:
    - lks_utils.bin: Binary dependency management
    - lks_utils.cancel: Cooperative cancellation helpers
    - lks_utils.concurrency: Parallel execution utilities
    - lks_utils.core: File I/O, hashing utilities
    - lks_utils.csv: CSV loading and parsing
    - lks_utils.filetype: File extension and category classification
    - lks_utils.image: Image processing (requires [image] extra)
    - lks_utils.json: JSON utilities
    - lks_utils.logging: Logging helpers
    - lks_utils.path: Path manipulation utilities
    - lks_utils.progress: Progress reporting
    - lks_utils.subtitles: VTT/SRT parsing
    - lks_utils.text: Text processing
    - lks_utils.time: Timestamp utilities
    - lks_utils.video: Video processing (requires FFmpeg)
    - lks_utils.web: Web/URL utilities
"""
from __future__ import annotations

# Re-export logging functions at package level for convenience
from lks_utils.logging import log_info, log_warn, log_error, log_debug, safe_print, timed, timeit

__version__ = "0.1.0"

__all__ = [
    # Logging
    "log_info",
    "log_warn",
    "log_error",
    "log_debug",
    "safe_print",
    "timed",
    "timeit",
    # Version
    "__version__",
]
