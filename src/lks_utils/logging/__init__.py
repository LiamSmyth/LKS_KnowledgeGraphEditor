"""Logging utilities for lks_utils with optional color support.

Provides structured logging helpers with optional verbose/debug mode
controlled via the LKS_VERBOSE_LOGGING environment variable.

Color support is automatic when lks_utils.console is available.
Disable colors with LKS_CONSOLE_COLOR=0 or NO_COLOR environment variable.
"""
from __future__ import annotations

from lks_utils.logging.logging_utils import log_info, log_warn, log_error, log_debug, log_success, safe_print, timed, timeit, VERBOSE_LOGGING, HAS_CONSOLE

__all__ = [
    "log_info",
    "log_warn",
    "log_error",
    "log_debug",
    "log_success",
    "safe_print",
    "timed",
    "timeit",
    "VERBOSE_LOGGING",
    "HAS_CONSOLE",
]
