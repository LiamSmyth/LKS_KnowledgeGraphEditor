"""GPU detection, VRAM management, context factory, and compute dispatch.

This module provides utilities for CUDA/VRAM management (requires PyTorch)
and OpenGL compute shader dispatch (requires ModernGL).
"""

from __future__ import annotations
from lks_utils.gpu.gpu_utils import detect_cuda, get_vram_total, get_vram_available, get_vram_used, clear_vram, estimate_can_fit, get_gpu_info, GPUInfo
from lks_utils.gpu.gpu_context import GPUContext, HAS_MODERNGL
from lks_utils.gpu.compute_dispatch import ComputeDispatch, ComputeResult
from lks_utils.gpu.gpu_timer_query import GpuTimerQuery, HAS_GPU_TIMER_QUERY
from lks_utils.gpu.gpu_handoff_timer import GpuHandoffTimer

__all__ = [
    "detect_cuda",
    "get_vram_total",
    "get_vram_available",
    "get_vram_used",
    "clear_vram",
    "estimate_can_fit",
    "get_gpu_info",
    "GPUInfo",
    "GPUContext",
    "HAS_MODERNGL",
    "ComputeDispatch",
    "ComputeResult",
    "GpuTimerQuery",
    "HAS_GPU_TIMER_QUERY",
    "GpuHandoffTimer",
]
