"""Performance target declaration and discovery for the perf specialist system."""
from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lks_utils.profiling.device import Device
from lks_utils.profiling.perf_budget import PerfBudget
from lks_utils.profiling.surface_kind import SurfaceKind


@dataclass(frozen=True)
class PerfTarget:
    """A named performance target with a declared budget and test location.

    Each module that has measurable performance characteristics should expose
    a ``TARGETS: dict[str, PerfTarget]`` mapping in a co-located
    ``perf_targets.py`` file. The ``discover_targets`` function walks the
    repository to collect them.

    Attributes:
        name: Dotted name, e.g. ``"painter.brush_stroke"``.
        description: Human-readable description of what is being measured.
        budget: Latency budget declared via :class:`PerfBudget`.
        test_id: Pytest node id that runs the perf benchmark, e.g.
            ``"src/lks_utils/paint/test/brush_perf_test.py::test_stroke"``.
        scenario_callable: Optional dotted Python path (``"module.func"``)
            for a live scenario that can be invoked directly without pytest.
        surface_kind: Whether this is an interactive, batch, or init surface.
        device_focus: Which devices matter for this target (CPU, GPU, HANDOFF).
    """

    name: str
    description: str
    budget: PerfBudget
    test_id: str
    scenario_callable: str | None
    surface_kind: SurfaceKind
    device_focus: tuple[Device, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("PerfTarget.name must be non-empty")
        if not self.test_id:
            raise ValueError("PerfTarget.test_id must be non-empty")
        if not self.device_focus:
            raise ValueError(
                "PerfTarget.device_focus must list at least one device")

    @classmethod
    def from_dict(cls, target_id: str, data: dict[str, Any]) -> "PerfTarget":
        """Construct from a plain dict as stored in ``perf_targets.json``.

        The ``name`` field defaults to *target_id* when omitted (the JSON
        schema makes ``name`` optional since the key already carries it).
        """
        device_focus = tuple(
            Device(v) for v in data.get("device_focus", ["CPU"])
        )
        return cls(
            name=data.get("name", target_id),
            description=data["description"],
            budget=PerfBudget.from_dict(data["budget"]),
            test_id=data["test_id"],
            scenario_callable=data.get("scenario_callable"),
            surface_kind=SurfaceKind(data["surface_kind"]),
            device_focus=device_focus,
        )


def discover_targets(repo_root: str | Path) -> list[dict[str, Any]]:
    """Walk *repo_root* for ``perf_targets.json`` files and collect all targets.

    Each JSON file is parsed (no import needed), its ``targets`` dict is read,
    and each entry is converted to a plain dict with a ``source_file`` key.

    Legacy ``perf_targets.py`` files (with a ``TARGETS`` dict) are also
    supported for backwards compatibility.

    Returns:
        List of dicts with keys: ``id``, ``name``, ``description``, ``budget``,
        ``surface_kind``, ``test_id``, ``scenario_callable``, ``source_file``.
    """
    root = Path(repo_root)
    results: list[dict[str, Any]] = []

    # Primary: JSON files.
    for pt_file in sorted(root.rglob("perf_targets.json")):
        try:
            raw = json.loads(pt_file.read_text(encoding="utf-8"))
        except Exception as exc:
            results.append({"id": f"ERROR:{pt_file}",
                           "source_file": str(pt_file), "error": str(exc)})
            continue
        targets_raw: dict[str, Any] = raw.get("targets", {})
        for target_id, data in targets_raw.items():
            try:
                target = PerfTarget.from_dict(target_id, data)
            except Exception as exc:
                results.append({"id": f"ERROR:{target_id}",
                               "source_file": str(pt_file), "error": str(exc)})
                continue
            results.append(_target_to_dict(target_id, target, pt_file))

    # Legacy fallback: Python files (no JSON sibling).
    for pt_file in sorted(root.rglob("perf_targets.py")):
        # Skip if a JSON counterpart already handled this directory.
        if (pt_file.parent / "perf_targets.json").exists():
            continue
        module_name = _module_name_for(pt_file, root)
        try:
            module = _import_file(module_name, pt_file)
        except Exception as exc:
            results.append({"id": f"ERROR:{pt_file}",
                           "source_file": str(pt_file), "error": str(exc)})
            continue
        targets: dict[str, PerfTarget] | None = getattr(
            module, "TARGETS", None)
        if not isinstance(targets, dict):
            continue
        for target_id, target in targets.items():
            if not isinstance(target, PerfTarget):
                continue
            results.append(_target_to_dict(target_id, target, pt_file))

    return results


def _target_to_dict(target_id: str, target: PerfTarget, source_file: Path) -> dict[str, Any]:
    return {
        "id": target_id,
        "name": target.name,
        "description": target.description,
        "budget": {
            "p95_ms": target.budget.p95_ms,
            "p99_ms": target.budget.p99_ms_resolved,
        },
        "surface_kind": target.surface_kind.value,
        "test_id": target.test_id,
        "scenario_callable": target.scenario_callable,
        "device_focus": [d.value for d in target.device_focus],
        "source_file": str(source_file),
    }


def _module_name_for(file: Path, root: Path) -> str:
    """Derive a dotted module name from a file path relative to *root*."""
    try:
        rel = file.relative_to(root)
    except ValueError:
        rel = file
    parts = list(rel.with_suffix("").parts)
    # Strip leading 'src' segment if present (editable installs)
    if parts and parts[0] == "src":
        parts = parts[1:]
    return ".".join(parts)


def _import_file(module_name: str, file: Path) -> Any:
    """Import a Python file as a module, caching in sys.modules."""
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create spec for {file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


__all__ = ["PerfTarget", "discover_targets"]
