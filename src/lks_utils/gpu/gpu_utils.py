"""GPU detection and VRAM management utilities.

This module provides functions for detecting CUDA availability, querying GPU
memory, and managing VRAM budgets for model loading workflows.

Example:
    from lks_utils.gpu import detect_cuda, get_vram_available, estimate_can_fit
    
    if detect_cuda():
        available_gb = get_vram_available()
        if estimate_can_fit(4.0):  # Need 4GB for model
            # Safe to load model
            pass

Environment Variables:
    CUDA_VISIBLE_DEVICES: Controls which GPUs are visible to PyTorch.
"""

from __future__ import annotations

from dataclasses import dataclass

# Memory conversion constant
BYTES_PER_GB: int = 1024 ** 3

# Default values
DEFAULT_SAFETY_MARGIN_GB: float = 0.5
DEFAULT_MAX_BATCH: int = 32
DEFAULT_TARGET_UTILIZATION: float = 0.7
DEFAULT_DEVICE_INDEX: int = 0

# Error messages
ERROR_TORCH_NOT_INSTALLED: str = (
    "PyTorch is required for GPU utilities. "
    "Install with: pip install torch --index-url https://download.pytorch.org/whl/cu121"
)

# Lazy import torch to avoid import-time dependency
_torch = None


def _get_torch():
    """Lazy import of torch module."""
    global _torch
    if _torch is None:
        try:
            import torch
            _torch = torch
        except ImportError:
            raise ImportError(ERROR_TORCH_NOT_INSTALLED)
    return _torch


def _check_torch_available() -> bool:
    """Check if PyTorch is available without raising an error."""
    try:
        import torch
        return True
    except ImportError:
        return False


@dataclass
class GPUInfo:
    """GPU information container.

    Attributes:
        available: Whether CUDA is available.
        device_count: Number of CUDA devices.
        device_index: Index of the primary device (0 if available).
        device_name: Name of the GPU (e.g., "NVIDIA GeForce RTX 3080").
        cuda_version: CUDA version string (e.g., "12.1").
        vram_total_gb: Total VRAM in gigabytes.
        vram_available_gb: Available VRAM in gigabytes.
        vram_used_gb: Used VRAM in gigabytes.
        compute_capability: Compute capability tuple (major, minor).
    """
    available: bool
    device_count: int = 0
    device_index: int = 0
    device_name: str | None = None
    cuda_version: str | None = None
    vram_total_gb: float = 0.0
    vram_available_gb: float = 0.0
    vram_used_gb: float = 0.0
    compute_capability: tuple[int, int] | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "available": self.available,
            "device_count": self.device_count,
            "device_index": self.device_index,
            "device_name": self.device_name,
            "cuda_version": self.cuda_version,
            "vram_total_gb": round(self.vram_total_gb, 2),
            "vram_available_gb": round(self.vram_available_gb, 2),
            "vram_used_gb": round(self.vram_used_gb, 2),
            "compute_capability": self.compute_capability,
        }


def detect_cuda() -> bool:
    """Check if CUDA is available.

    Returns:
        True if CUDA is available, False otherwise.

    Example:
        if detect_cuda():
            device = "cuda"
        else:
            device = "cpu"
    """
    if not _check_torch_available():
        return False

    torch = _get_torch()
    return torch.cuda.is_available()


def get_gpu_info(device_index: int = DEFAULT_DEVICE_INDEX) -> GPUInfo:
    """Get comprehensive GPU information.

    Args:
        device_index: Index of the GPU to query (default 0).

    Returns:
        GPUInfo dataclass with GPU details.

    Example:
        info = get_gpu_info()
        print(f"GPU: {info.device_name}, VRAM: {info.vram_total_gb:.1f}GB")
    """
    if not _check_torch_available():
        return GPUInfo(available=False)

    torch = _get_torch()

    if not torch.cuda.is_available():
        return GPUInfo(available=False)

    device_count = torch.cuda.device_count()
    if device_index >= device_count:
        return GPUInfo(available=False)

    props = torch.cuda.get_device_properties(device_index)

    # Get memory info
    total_bytes: int = props.total_memory
    # Use memory_stats for more accurate available memory
    try:
        torch.cuda.set_device(device_index)
        free_bytes: int
        total_check: int
        free_bytes, total_check = torch.cuda.mem_get_info(device_index)
        used_bytes: int = total_bytes - free_bytes
    except Exception:
        # Fallback if mem_get_info not available
        used_bytes = torch.cuda.memory_allocated(device_index)
        free_bytes = total_bytes - used_bytes

    return GPUInfo(
        available=True,
        device_count=device_count,
        device_index=device_index,
        device_name=props.name,
        cuda_version=torch.version.cuda,
        vram_total_gb=total_bytes / BYTES_PER_GB,
        vram_available_gb=free_bytes / BYTES_PER_GB,
        vram_used_gb=used_bytes / BYTES_PER_GB,
        compute_capability=(props.major, props.minor),
    )


def get_vram_total(device_index: int = DEFAULT_DEVICE_INDEX) -> float:
    """Get total VRAM in gigabytes.

    Args:
        device_index: Index of the GPU to query.

    Returns:
        Total VRAM in GB, or 0.0 if CUDA is not available.
    """
    info = get_gpu_info(device_index)
    return info.vram_total_gb


def get_vram_available(device_index: int = DEFAULT_DEVICE_INDEX) -> float:
    """Get available (free) VRAM in gigabytes.

    This queries the actual free memory on the GPU, accounting for
    memory used by other processes.

    Args:
        device_index: Index of the GPU to query.

    Returns:
        Available VRAM in GB, or 0.0 if CUDA is not available.
    """
    info = get_gpu_info(device_index)
    return info.vram_available_gb


def get_vram_used(device_index: int = DEFAULT_DEVICE_INDEX) -> float:
    """Get used VRAM in gigabytes.

    Args:
        device_index: Index of the GPU to query.

    Returns:
        Used VRAM in GB, or 0.0 if CUDA is not available.
    """
    info = get_gpu_info(device_index)
    return info.vram_used_gb


def clear_vram() -> None:
    """Clear CUDA memory cache.

    This calls torch.cuda.empty_cache() to release cached memory back
    to the GPU. Note that this does not free memory held by tensors;
    those must be deleted first.

    Example:
        # After unloading a model
        del model
        clear_vram()
    """
    if not _check_torch_available():
        return

    torch = _get_torch()

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()


def estimate_can_fit(
    required_gb: float,
    safety_margin_gb: float = DEFAULT_SAFETY_MARGIN_GB,
    device_index: int = DEFAULT_DEVICE_INDEX
) -> bool:
    """Estimate if a model requiring given VRAM can fit.

    Args:
        required_gb: Required VRAM in gigabytes.
        safety_margin_gb: Extra headroom to leave free (default 0.5GB).
        device_index: Index of the GPU to check.

    Returns:
        True if there's enough available VRAM, False otherwise.

    Example:
        # Check if we can load a 4GB model
        if estimate_can_fit(4.0):
            model = load_model()
    """
    available: float = get_vram_available(device_index)
    return available >= (required_gb + safety_margin_gb)


def estimate_batch_size(
    per_item_gb: float,
    max_batch: int = DEFAULT_MAX_BATCH,
    target_utilization: float = DEFAULT_TARGET_UTILIZATION,
    device_index: int = DEFAULT_DEVICE_INDEX
) -> int:
    """Estimate optimal batch size based on available VRAM.

    Args:
        per_item_gb: Estimated VRAM per item in the batch.
        max_batch: Maximum batch size to consider.
        target_utilization: Target fraction of available VRAM to use (0.0-1.0).
        device_index: Index of the GPU to check.

    Returns:
        Recommended batch size (minimum 1).

    Example:
        # Each image takes ~0.1GB during CLIP inference
        batch_size = estimate_batch_size(0.1, max_batch=16)
    """
    available: float = get_vram_available(device_index)
    usable: float = available * target_utilization

    if per_item_gb <= 0:
        return max_batch

    estimated: int = int(usable / per_item_gb)
    return max(1, min(estimated, max_batch))
