"""GPU compute shader dispatch framework.

Primary module location — canonical import path:
``from lks_utils.gpu.compute_dispatch import ComputeDispatch, ComputeResult``

The legacy import path ``from lks_utils.gui_qt.viewport.compute_dispatch``
re-exports from here for backward compatibility.

Provides a thin abstraction for binding input textures, running GLSL 4.3
compute kernels, and reading results back to CPU memory.

Requires: moderngl >= 5.12.0, numpy.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

try:
    import moderngl
    HAS_MODERNGL = True
except ImportError:
    HAS_MODERNGL = False


@dataclass
class ComputeResult:
    """Result from a compute shader dispatch.

    Attributes:
        data: Output array (float32 or uint8 depending on format).
        width: Output texture width.
        height: Output texture height.
        channels: Number of output channels.
    """

    data: np.ndarray
    width: int
    height: int
    channels: int


class ComputeDispatch:
    """Dispatch GLSL 4.3 compute shaders on a ModernGL context.

    Usage::

        dispatch = ComputeDispatch(ctx)
        dispatch.load_shader("my_filter", source_code)

        result = dispatch.run(
            "my_filter",
            input_textures={"heightmap": my_texture},
            uniforms={"sigma": 2.0},
            output_size=(width, height),
        )
        # result.data is a numpy array
    """

    def __init__(self, ctx: Any) -> None:
        self._ctx: Any = ctx
        self._programs: dict[str, Any] = {}
        # Paths of shaders registered for *lazy* compilation — compiled on
        # the first run() call so the correct GL context is always current.
        self._shader_paths: dict[str, Path] = {}

    def load_shader(self, name: str, source: str) -> None:
        """Compile and cache a compute shader program."""
        if not HAS_MODERNGL or self._ctx is None:
            return
        self._programs[name] = self._ctx.compute_shader(source)

    def load_shader_file(self, name: str, path: Path) -> None:
        """Register a compute shader file for lazy compilation on first use.

        Compilation is deferred to the first :meth:`run` call so that the
        correct OpenGL context is guaranteed to be current (critical on
        Windows where multiple OpenGL contexts can race for WGL "current"
        status).  The shader is compiled at most once per dispatch instance.
        """
        self._shader_paths[name] = path

    def run(
        self,
        shader_name: str,
        input_textures: dict[str, Any] | None = None,
        uniforms: dict[str, Any] | None = None,
        buffer_uniforms: dict[str, bytes] | None = None,
        output_size: tuple[int, int] = (256, 256),
        output_channels: int = 4,
        output_dtype: str = "f2",
        work_group_size: tuple[int, int, int] = (16, 16, 1),
    ) -> ComputeResult:
        """Run a compute shader and return the output as a NumPy array.

        Args:
            shader_name: Name of a previously loaded shader.
            input_textures: ``{uniform_name: moderngl.Texture}`` bindings
                (bound as ``image2D`` for ``imageLoad``).
            uniforms: Scalar uniform values ``{name: value}``.
            buffer_uniforms: Raw byte-buffer uniform values ``{name: bytes}``
                for mat4, vec3 arrays, etc. Written via ``prog[name].write()``.
            output_size: ``(width, height)`` of the output texture.
            output_channels: Number of channels in the output (1–4).
            output_dtype: ModernGL dtype for output texture (``"f2"`` = float16,
                ``"f4"`` = float32, ``"f1"`` = uint8 normalized).
            work_group_size: Compute shader local work group dimensions.

        Returns:
            ComputeResult with the output array.

        Raises:
            KeyError: If ``shader_name`` was not previously loaded.
            RuntimeError: If ModernGL is not available.
        """
        if not HAS_MODERNGL or self._ctx is None:
            msg = "ModernGL context not available"
            raise RuntimeError(msg)

        # Lazily compile any shaders that were registered via load_shader_file
        # but not yet compiled (deferred so the correct GL context is current).
        if shader_name in self._shader_paths and shader_name not in self._programs:
            source = self._shader_paths[shader_name].read_text(
                encoding="utf-8")
            self.load_shader(shader_name, source)

        prog = self._programs[shader_name]
        w, h = output_size

        # Create output texture (image2D binding)
        numpy_dtype = {"f1": np.uint8, "f2": np.float16,
                       "f4": np.float32}[output_dtype]
        out_tex = self._ctx.texture(
            (w, h), output_channels, dtype=output_dtype)
        out_tex.bind_to_image(0, read=False, write=True)

        # Bind input textures (as image2D for imageLoad/imageStore)
        bind_slot = 1
        if input_textures:
            for name, tex in input_textures.items():
                tex.bind_to_image(bind_slot, read=True, write=False)
                if name in prog:
                    prog[name].value = bind_slot
                bind_slot += 1

        # Set scalar uniforms
        if uniforms:
            for name, value in uniforms.items():
                if name in prog:
                    prog[name].value = value

        # Set buffer uniforms (mat4, vec3 arrays, etc.)
        if buffer_uniforms:
            for name, data in buffer_uniforms.items():
                if name in prog:
                    prog[name].write(data)

        # Dispatch
        gx = max(1, (w + work_group_size[0] - 1) // work_group_size[0])
        gy = max(1, (h + work_group_size[1] - 1) // work_group_size[1])
        prog.run(gx, gy, work_group_size[2])

        # Synchronise — glFinish() ensures the GPU has completed all pending
        # writes before the CPU reads back the output texture.  Without this,
        # the first dispatch on a cold context can return an uninitialised
        # (all-zero / black) result on some drivers.
        self._ctx.finish()

        # Readback
        raw = out_tex.read()
        data = np.frombuffer(raw, dtype=numpy_dtype).reshape(
            h, w, output_channels)
        out_tex.release()

        return ComputeResult(data=data, width=w, height=h, channels=output_channels)

    def create_texture(
        self,
        width: int,
        height: int,
        channels: int = 1,
        data: np.ndarray | None = None,
        dtype: str = "f4",
    ) -> Any:
        """Create a GPU texture, optionally filled with *data*.

        Useful for intermediate textures in multi-pass pipelines
        (e.g., Gaussian pyramid levels).

        Args:
            width: Texture width.
            height: Texture height.
            channels: Number of channels (1–4).
            data: Optional NumPy array to upload (must match size and dtype).
            dtype: ModernGL dtype (``"f4"`` = float32, ``"f2"`` = float16).

        Returns:
            A ``moderngl.Texture`` instance.
        """
        if not HAS_MODERNGL or self._ctx is None:
            msg = "ModernGL context not available"
            raise RuntimeError(msg)
        raw_data = data.tobytes() if data is not None else None
        return self._ctx.texture((width, height), channels,
                                 data=raw_data, dtype=dtype)

    @property
    def available_shaders(self) -> list[str]:
        """Return names of loaded (compiled or pending) compute shaders."""
        return list(set(self._programs) | set(self._shader_paths))


__all__ = ["ComputeDispatch", "ComputeResult"]
