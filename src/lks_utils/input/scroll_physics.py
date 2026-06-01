"""Pure-Python scroll physics primitives (Phase 17i).

Three small headless value/state classes that drive smooth wheel
scrolling, velocity sampling, and momentum decay. Zero Qt
dependencies so the math is unit-testable without a display server.

* `WheelLerp` — animates a smooth approach to a target offset
  produced by discrete wheel notches. Each call to ``step(dt)``
  advances the animation by ``dt`` seconds and returns the
  *delta offset* to apply this frame (positive = same direction
  as the most recent ``add_notch`` call).

* `VelocitySampler` — feed ``(t, position)`` samples; on
  ``release()`` returns a smoothed velocity computed from the
  samples that fall inside the configured window. Stale samples
  outside the window are discarded.

* `MomentumDecay` — exponential decay of an initial velocity with
  time constant ``tau`` (decays to ``1/e`` in ``tau`` seconds; to
  half in ``tau * ln(2)`` seconds).

Convention: distances are floats in *display pixels*; velocity in
``px/s``; ``dt`` in seconds. Positive direction is left to caller —
the math is sign-agnostic.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
# WheelLerp                                                                    #
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class WheelLerp:
    """Critically-damped smooth approach to a wheel-driven target.

    Each ``add_notch(direction)`` adds ``distance_per_notch *
    direction`` to ``target``. ``step(dt)`` advances ``current``
    toward ``target`` and returns the delta to apply this frame.

    The lerp uses an exponential-decay model parameterised by
    ``lerp_ms`` (the time constant of the approach in milliseconds —
    after ``lerp_ms`` ms the remaining distance has decayed to
    ``1/e`` of the initial gap).

    Attributes:
        distance_per_notch: Pixels per wheel notch.
        lerp_ms: Time constant of the smoothing in milliseconds.
            Larger = slower / silkier; smaller = snappier.
    """

    distance_per_notch: float
    lerp_ms: float
    _target: float = 0.0
    _current: float = 0.0

    def __post_init__(self) -> None:
        if self.distance_per_notch <= 0:
            raise ValueError("distance_per_notch must be > 0")
        if self.lerp_ms <= 0:
            raise ValueError("lerp_ms must be > 0")

    @property
    def target(self) -> float:
        """Current target offset (cumulative)."""
        return self._target

    @property
    def current(self) -> float:
        """Current animated offset."""
        return self._current

    @property
    def remaining(self) -> float:
        """Signed distance still to travel (target - current)."""
        return self._target - self._current

    @property
    def is_settled(self) -> bool:
        """True once ``current`` is within 0.5 px of ``target``."""
        return abs(self.remaining) < 0.5

    def add_notch(self, direction: float = 1.0) -> None:
        """Append ``direction * distance_per_notch`` to the target."""
        self._target += float(direction) * self.distance_per_notch

    def reset(self) -> None:
        """Snap current and target to zero."""
        self._target = 0.0
        self._current = 0.0

    def snap_to_target(self) -> float:
        """Skip to ``target`` immediately and return the consumed delta."""
        delta = self._target - self._current
        self._current = self._target
        return delta

    def step(self, dt: float) -> float:
        """Advance the lerp by ``dt`` seconds; return delta to apply.

        Uses the closed-form exponential-decay solution
        ``new = current + (target - current) * (1 - exp(-dt / tau))``
        which is frame-rate independent.
        """
        if dt <= 0:
            return 0.0
        tau = self.lerp_ms / 1000.0
        gap = self._target - self._current
        if abs(gap) < 1e-9:
            return 0.0
        alpha = 1.0 - math.exp(-dt / tau)
        delta = gap * alpha
        # When close enough, snap to avoid endless tiny deltas.
        if abs(gap - delta) < 0.5:
            delta = gap
        self._current += delta
        return delta


# --------------------------------------------------------------------------- #
# VelocitySampler                                                              #
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class VelocitySampler:
    """Rolling-window velocity estimator.

    Feed ``(t, position)`` samples; ``velocity()`` and ``release()``
    return the average velocity computed over samples within the
    last ``window_ms`` of the most recent sample. Older samples are
    pruned automatically.

    Useful for kinetic-scroll release: sample every wheel/touch
    move during the gesture; on release, query the smoothed
    velocity to seed a `MomentumDecay`.

    Attributes:
        window_ms: Width of the smoothing window in milliseconds.
    """

    window_ms: float
    _samples: deque[tuple[float, float]] = field(default_factory=deque)

    def __post_init__(self) -> None:
        if self.window_ms <= 0:
            raise ValueError("window_ms must be > 0")

    def add_sample(self, t: float, position: float) -> None:
        """Record a ``(time_seconds, position_px)`` sample.

        Samples must arrive in non-decreasing time order. The
        method prunes any sample older than ``window_ms`` before
        the newly added one.
        """
        if self._samples and t < self._samples[-1][0]:
            raise ValueError("samples must arrive in non-decreasing time order")
        self._samples.append((float(t), float(position)))
        cutoff = t - self.window_ms / 1000.0
        while len(self._samples) > 1 and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def velocity(self) -> float:
        """Return mean velocity (px/s) over the current window.

        Returns 0 if fewer than 2 samples are available, or if the
        time span is degenerate.
        """
        if len(self._samples) < 2:
            return 0.0
        t0, p0 = self._samples[0]
        t1, p1 = self._samples[-1]
        dt = t1 - t0
        if dt <= 0:
            return 0.0
        return (p1 - p0) / dt

    def release(self) -> float:
        """Return ``velocity()`` then clear the buffer."""
        v = self.velocity()
        self._samples.clear()
        return v

    def clear(self) -> None:
        """Drop all stored samples."""
        self._samples.clear()

    @property
    def sample_count(self) -> int:
        """Number of samples currently inside the window."""
        return len(self._samples)


# --------------------------------------------------------------------------- #
# MomentumDecay                                                                #
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class MomentumDecay:
    """Exponentially-decaying momentum integrator.

    Initialise with an initial velocity (``px/s``) and a time
    constant ``tau`` (seconds). Each ``step(dt)`` returns the
    delta-offset for this frame and decays the internal velocity.

    Velocity model: ``v(t) = v0 * exp(-t / tau)``. Integrating
    over a frame of length ``dt`` gives a closed-form delta:
    ``delta = v_now * tau * (1 - exp(-dt / tau))``. After the
    step, ``v_now`` is set to ``v_now * exp(-dt / tau)``.

    Attributes:
        initial_velocity: Initial velocity in px/s (signed).
        tau: Time constant in seconds. Velocity decays to ``1/e``
            of its previous value every ``tau`` seconds; to half
            every ``tau * ln(2)`` seconds.
        min_velocity: Velocities below this magnitude (px/s) are
            clamped to zero — flagged via ``is_settled``.
    """

    initial_velocity: float
    tau: float
    min_velocity: float = 1.0
    _velocity: float = field(init=False)

    def __post_init__(self) -> None:
        if self.tau <= 0:
            raise ValueError("tau must be > 0")
        if self.min_velocity < 0:
            raise ValueError("min_velocity must be >= 0")
        self._velocity = float(self.initial_velocity)

    @property
    def velocity(self) -> float:
        """Current velocity (px/s, signed)."""
        return self._velocity

    @property
    def is_settled(self) -> bool:
        """True when |velocity| has decayed below ``min_velocity``."""
        return abs(self._velocity) < self.min_velocity

    def step(self, dt: float) -> float:
        """Advance momentum by ``dt`` seconds; return delta-offset."""
        if dt <= 0 or self.is_settled:
            return 0.0
        decay = math.exp(-dt / self.tau)
        delta = self._velocity * self.tau * (1.0 - decay)
        self._velocity *= decay
        if self.is_settled:
            self._velocity = 0.0
        return delta

    def stop(self) -> None:
        """Force-stop momentum immediately."""
        self._velocity = 0.0


__all__ = [
    "MomentumDecay",
    "VelocitySampler",
    "WheelLerp",
]
