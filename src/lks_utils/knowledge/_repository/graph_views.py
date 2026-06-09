"""Graph-view persistence helpers for Repository."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lks_utils.core.file_io import atomic_write, safe_filename
from lks_utils.knowledge._repository.disk_io import load_index_data
from lks_utils.knowledge.canvas.canvas_document import CanvasDocument
from lks_utils.knowledge.models.graph_view import GraphView
from lks_utils.knowledge.models.graph_view_edge_proxy import GraphViewEdgeProxy
from lks_utils.knowledge.models.graph_view_node_proxy import GraphViewNodeProxy


_DEFAULT_NODE_WIDTH = 280.0
_DEFAULT_NODE_HEIGHT = 90.0
_GRAPH_VIEW_ID_KEY = "graph_view_id"
_GRAPH_VIEW_NAME_KEY = "graph_view_name"
_SCHEMA_TYPE_KEY = "schema_type"
_SCHEMA_TYPE_VALUE = "knowledge_graph_view"
_KB_REPO_PATH_KEY = "kb_repo_path"
_LINK_TYPE_VISIBILITY_KEY = "link_type_visibility"


def _is_graph_view_file(candidate: Path) -> bool:
    return candidate.suffix.lower() == ".json" and not candidate.stem.endswith("_viewport")


def _name_from_filename(path: Path) -> str:
    return path.stem.replace("_", " ")


def _ensure_unique_local_id(base: str, used_ids: set[str]) -> str:
    candidate = base or "node"
    if candidate not in used_ids:
        used_ids.add(candidate)
        return candidate
    suffix = 2
    while True:
        next_candidate = f"{candidate}_{suffix}"
        if next_candidate not in used_ids:
            used_ids.add(next_candidate)
            return next_candidate
        suffix += 1


def _graph_view_from_canvas_payload(payload: object, *, fallback_path: Path) -> GraphView | None:
    if not isinstance(payload, dict):
        return None
    raw_objects = payload.get("objects", payload.get("items"))
    if not isinstance(raw_objects, list):
        return None

    document = CanvasDocument.from_dict(payload)
    metadata = dict(document.metadata)

    raw_id = metadata.get(_GRAPH_VIEW_ID_KEY)
    view_id = str(raw_id).strip() if raw_id is not None else ""
    if not view_id:
        view_id = fallback_path.stem

    raw_name = metadata.get(_GRAPH_VIEW_NAME_KEY)
    view_name = str(raw_name).strip() if raw_name is not None else ""
    if not view_name:
        view_name = _name_from_filename(fallback_path)

    nodes: dict[str, GraphViewNodeProxy] = {}
    node_local_by_global: dict[str, str] = {}
    used_local_ids: set[str] = set()
    for obj in document.objects:
        item_type = obj.get("type")
        if item_type != "knowledge.kb_node":
            continue
        global_id_obj = obj.get("node_id")
        if global_id_obj is None:
            continue
        global_id = str(global_id_obj)
        if not global_id.strip():
            continue
        x = float(obj.get("x", 0.0))
        y = float(obj.get("y", 0.0))
        cached_name_obj = obj.get("label")
        cached_name = str(
            cached_name_obj) if cached_name_obj is not None else ""
        raw_local_id = obj.get("local_id")
        base_local_id = str(
            raw_local_id) if raw_local_id is not None else global_id
        local_id = _ensure_unique_local_id(base_local_id, used_local_ids)
        node_local_by_global[global_id] = local_id
        nodes[local_id] = GraphViewNodeProxy(
            global_id=global_id,
            x=x,
            y=y,
            cached_name=cached_name,
        )

    edges: dict[str, GraphViewEdgeProxy] = {}
    used_edge_ids: set[str] = set()
    for obj in document.objects:
        item_type = obj.get("type")
        if item_type != "knowledge.kb_edge":
            continue
        link_id_obj = obj.get("link_id")
        from_node_obj = obj.get("from_node_id")
        to_node_obj = obj.get("to_node_id")
        if link_id_obj is None or from_node_obj is None or to_node_obj is None:
            continue
        link_id = str(link_id_obj)
        from_global = str(from_node_obj)
        to_global = str(to_node_obj)
        source_local = None
        target_local = None
        source_local_obj = obj.get("source_local_id")
        target_local_obj = obj.get("target_local_id")
        if source_local_obj is not None and target_local_obj is not None:
            source_local = str(source_local_obj)
            target_local = str(target_local_obj)
        if source_local is None or target_local is None:
            source_local = node_local_by_global.get(from_global)
            target_local = node_local_by_global.get(to_global)
        if source_local is None or target_local is None:
            continue
        raw_edge_local = obj.get("local_id")
        base_edge_local = str(
            raw_edge_local) if raw_edge_local is not None else link_id
        edge_local = _ensure_unique_local_id(base_edge_local, used_edge_ids)
        edges[edge_local] = GraphViewEdgeProxy(
            global_link_id=link_id,
            source_local_id=source_local,
            target_local_id=target_local,
        )

    return GraphView(id=view_id, name=view_name, nodes=nodes, edges=edges)


def _graph_view_to_canvas_payload(view: GraphView) -> dict[str, Any]:
    objects: list[dict[str, Any]] = []
    global_by_local = {
        local_id: proxy.global_id for local_id, proxy in view.nodes.items()
    }

    for local_id, proxy in view.nodes.items():
        object_payload: dict[str, Any] = {
            "type": "knowledge.kb_node",
            "local_id": local_id,
            "node_id": proxy.global_id,
            "x": float(proxy.x),
            "y": float(proxy.y),
            "width": _DEFAULT_NODE_WIDTH,
            "height": _DEFAULT_NODE_HEIGHT,
        }
        if proxy.cached_name:
            object_payload["label"] = proxy.cached_name
        objects.append(object_payload)

    for local_id, edge in view.edges.items():
        from_global = global_by_local.get(edge.source_local_id)
        to_global = global_by_local.get(edge.target_local_id)
        if from_global is None or to_global is None:
            continue
        objects.append(
            {
                "type": "knowledge.kb_edge",
                "local_id": local_id,
                "link_id": edge.global_link_id,
                "source_local_id": edge.source_local_id,
                "target_local_id": edge.target_local_id,
                "from_node_id": from_global,
                "to_node_id": to_global,
            }
        )

    document = CanvasDocument(
        version=1,
        objects=objects,
        metadata={
            _SCHEMA_TYPE_KEY: _SCHEMA_TYPE_VALUE,
            _KB_REPO_PATH_KEY: "../",
            _LINK_TYPE_VISIBILITY_KEY: {},
            _GRAPH_VIEW_ID_KEY: view.id,
            _GRAPH_VIEW_NAME_KEY: view.name,
        },
        overlays=[],
        bookmarks=[],
    )
    return document.to_dict()


def _try_parse_graph_view_payload(payload: object, *, fallback_path: Path) -> GraphView | None:
    """Return GraphView projected from the canonical canvas document payload."""
    return _graph_view_from_canvas_payload(payload, fallback_path=fallback_path)


def _resolve_unique_view_name(base: str, used_casefold: set[str]) -> str:
    name = base.strip() or "Graph View"
    if name.casefold() not in used_casefold:
        used_casefold.add(name.casefold())
        return name
    suffix = 2
    while True:
        candidate = f"{name} ({suffix})"
        if candidate.casefold() not in used_casefold:
            used_casefold.add(candidate.casefold())
            return candidate
        suffix += 1


def _dedupe_graph_view_names(views: list[GraphView]) -> list[GraphView]:
    used_casefold: set[str] = set()
    deduped: list[GraphView] = []
    for view in views:
        resolved_name = _resolve_unique_view_name(view.name, used_casefold)
        if resolved_name == view.name:
            deduped.append(view)
            continue
        deduped.append(
            GraphView(
                id=view.id,
                name=resolved_name,
                nodes=dict(view.nodes),
                edges=dict(view.edges),
            )
        )
    return deduped


def save_graph_view(*, repository: object, view: GraphView) -> None:
    root = repository._require_repo_root()  # noqa: SLF001
    views_dir = root / "views"
    views_dir.mkdir(parents=True, exist_ok=True)
    resolved_name = ensure_unique_graph_view_name(
        repository=repository,
        desired=view.name,
        exclude_id=view.id,
    )
    effective_view = view
    if resolved_name != view.name:
        effective_view = GraphView(
            id=view.id,
            name=resolved_name,
            nodes=dict(view.nodes),
            edges=dict(view.edges),
        )

    previous_relpath = repository.graph_view_relpath(view.id)
    previous_name = Path(
        previous_relpath).name if previous_relpath is not None else None

    used_filenames: set[str] = set()
    for candidate in sorted(views_dir.glob("*.json")):
        if candidate.name == previous_name:
            continue
        used_filenames.add(candidate.name)

    base_name = safe_filename(effective_view.name) or "graph_view"
    filename = f"{base_name}.json"
    suffix = 2
    while filename in used_filenames:
        filename = f"{base_name}_{suffix}.json"
        suffix += 1

    target = views_dir / filename
    atomic_write(str(target), repository._pretty_json(_graph_view_to_canvas_payload(effective_view)))  # noqa: SLF001
    if previous_name is not None and previous_name != target.name:
        stale = views_dir / previous_name
        stale.unlink(missing_ok=True)
    repository._sync_index()  # noqa: SLF001


def load_graph_view(*, repository: object, view_id: str) -> GraphView:
    root = repository._require_repo_root()  # noqa: SLF001
    relpath = repository.graph_view_relpath(view_id)
    target = root / relpath if relpath is not None else root / \
        "views" / f"{view_id}.json"
    if not target.exists():
        raise KeyError(f"Graph view not found: {view_id}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    view = _try_parse_graph_view_payload(payload, fallback_path=target)
    if view is None:
        raise ValueError(f"Malformed graph view payload for {view_id}")
    return view


def list_graph_views(*, repository: object) -> list[GraphView]:
    root = repository._require_repo_root()  # noqa: SLF001
    views_dir = root / "views"
    if not views_dir.exists():
        return []
    views: list[GraphView] = []
    for candidate in sorted(views_dir.glob("*.json")):
        if not _is_graph_view_file(candidate):
            continue
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        view = _try_parse_graph_view_payload(payload, fallback_path=candidate)
        if view is not None:
            views.append(view)
    return _dedupe_graph_view_names(views)


def delete_graph_view(*, repository: object, view_id: str) -> None:
    root = repository._require_repo_root()  # noqa: SLF001
    relpath = repository.graph_view_relpath(view_id)
    target = root / relpath if relpath is not None else root / \
        "views" / f"{view_id}.json"
    target.unlink(missing_ok=True)
    repository._sync_index()  # noqa: SLF001


def graph_view_relpath(*, repository: object, view_id: str) -> str | None:
    root = repository._require_repo_root()  # noqa: SLF001
    index_data = load_index_data(root)
    if isinstance(index_data, dict):
        views_obj = index_data.get("views")
        if isinstance(views_obj, dict):
            relpath_obj = views_obj.get(view_id)
            if isinstance(relpath_obj, str) and relpath_obj:
                return relpath_obj

    views_dir = root / "views"
    if not views_dir.exists():
        return None
    for candidate in sorted(views_dir.glob("*.json")):
        if not _is_graph_view_file(candidate):
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        view = _try_parse_graph_view_payload(payload, fallback_path=candidate)
        if view is not None and view.id == view_id:
            return candidate.relative_to(root).as_posix()
    return None


def ensure_unique_graph_view_name(*, repository: object, desired: str, exclude_id: str | None = None) -> str:
    base = desired.strip() or "Graph View"
    existing = {view.name: view.id for view in repository.list_graph_views()}
    owner = existing.get(base)
    if owner is None or owner == exclude_id:
        return base
    suffix = 2
    while True:
        candidate = f"{base} ({suffix})"
        owner = existing.get(candidate)
        if owner is None or owner == exclude_id:
            return candidate
        suffix += 1


def build_views_index(*, root: Path) -> dict[str, str]:
    """Return ``{view_id: relative_filename}`` for ``views/*.json`` files."""
    views_dir = root / "views"
    if not views_dir.exists():
        return {}
    views_index: dict[str, str] = {}
    for candidate in sorted(views_dir.glob("*.json")):
        if not _is_graph_view_file(candidate):
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        view = _try_parse_graph_view_payload(payload, fallback_path=candidate)
        if view is None:
            continue
        views_index[view.id] = candidate.relative_to(root).as_posix()
    return views_index
