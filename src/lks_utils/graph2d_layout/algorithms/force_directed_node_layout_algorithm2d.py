"""Force-directed layout algorithm with directional bias."""
from __future__ import annotations

import math

from lks_utils.graph2d_layout._graph_utils import (
    build_adjacency,
    build_components,
    segment_intersection,
)
from lks_utils.graph2d_layout.algorithms.sugiyama_node_layout_algorithm2d import (
    SugiyamaNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.node_layout_algorithm2d import NodeLayoutAlgorithm2D
from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D

__all__ = ["ForceDirectedNodeLayoutAlgorithm2D"]

_DIRECTION = str


class ForceDirectedNodeLayoutAlgorithm2D(NodeLayoutAlgorithm2D):
    """Directional force-directed layout seeded from a Sugiyama pass.

    **Tier**: graph-aware — uses edge topology, node sizes, and
    directional flow bias.

    The simulation runs five forces per iteration (in priority order):

    1. Anti-overlap + pairwise repulsion (strongest)
    2. Edge-spring attraction + directional gap enforcement
    3. Mild centre-line alignment to neighbours
    4. Edge-crossing pressure
    5. A final rect-overlap cleanup pass

    Nodes are seeded from a Sugiyama layout for stable, directional
    initialisation. Disconnected components are packed with a gap.

    Args:
        direction: Flow direction. One of ``"left_to_right"``,
            ``"right_to_left"``, ``"top_to_bottom"``, ``"bottom_to_top"``.
        repulsion: Pairwise repulsion multiplier.
        attraction: Spring attraction multiplier.
        iterations: Number of simulation steps.
        edge_length: Preferred edge length (px).
        overlap_strength: Multiplier for overlap separation force.
        flow_strength: Multiplier for directional flow bias.
        alignment_strength: Multiplier for neighbour centre-line alignment.
        crossing_strength: Multiplier for edge-crossing pressure.
        damping: Velocity retention (0.1–0.99). Higher = smoother,
            slower convergence.
        temperature: Initial force cap (px). Decays each step.
        final_padding: Minimum gap between rects after cleanup (px).
        component_gap: Gap between disconnected components (px).
        origin_x: X origin of the entire layout.
        origin_y: Y origin of the entire layout.
    """

    def __init__(
        self,
        *,
        direction: _DIRECTION = "left_to_right",
        repulsion: float = 1.0,
        attraction: float = 0.1,
        iterations: int = 100,
        edge_length: float = 220.0,
        overlap_strength: float = 1.0,
        flow_strength: float = 1.0,
        alignment_strength: float = 1.0,
        crossing_strength: float = 1.0,
        damping: float = 0.86,
        temperature: float = 140.0,
        final_padding: float = 12.0,
        prevent_shape_overlaps: bool = True,
        shape_overlap_iterations: int = 64,
        component_gap: float = 140.0,
        origin_x: float = 0.0,
        origin_y: float = 0.0,
    ) -> None:
        self.direction = direction
        self.repulsion = repulsion
        self.attraction = attraction
        self.iterations = iterations
        self.edge_length = edge_length
        self.overlap_strength = overlap_strength
        self.flow_strength = flow_strength
        self.alignment_strength = alignment_strength
        self.crossing_strength = crossing_strength
        self.damping = max(0.10, min(0.99, damping))
        self.temperature = max(10.0, temperature)
        self.final_padding = max(0.0, final_padding)
        self.prevent_shape_overlaps = prevent_shape_overlaps
        self.shape_overlap_iterations = shape_overlap_iterations
        self.component_gap = component_gap
        self.origin_x = origin_x
        self.origin_y = origin_y

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def compute(
        self,
        nodes: list[LayoutNode2D],
        edges: list[LayoutEdge2D],
    ) -> dict[str, tuple[float, float]]:
        if not nodes:
            return {}

        node_map = {n.node_id: n for n in nodes}
        node_ids = [n.node_id for n in nodes]
        components = build_components(node_ids, edges)

        horizontal = self.direction in ("left_to_right", "right_to_left")
        offset_x = self.origin_x
        offset_y = self.origin_y
        all_positions: dict[str, tuple[float, float]] = {}

        for component in components:
            comp_set = set(component)
            comp_edges = [e for e in edges if e.source_id in comp_set and e.target_id in comp_set]
            local_pos, width, height = self._compute_component(component, comp_edges, node_map)
            for nid, (lx, ly) in local_pos.items():
                all_positions[nid] = (offset_x + lx, offset_y + ly)

            if horizontal:
                offset_y += height + self.component_gap
            else:
                offset_x += width + self.component_gap

        return self._finalize_positions(
            nodes,
            all_positions,
            prevent_shape_overlaps=self.prevent_shape_overlaps,
            overlap_padding=self.final_padding,
            overlap_iterations=self.shape_overlap_iterations,
        )

    # ------------------------------------------------------------------ #
    # Internal — component solver                                          #
    # ------------------------------------------------------------------ #

    def _compute_component(
        self,
        node_ids: list[str],
        edges: list[LayoutEdge2D],
        node_map: dict[str, LayoutNode2D],
    ) -> tuple[dict[str, tuple[float, float]], float, float]:
        if len(node_ids) == 1:
            nid = node_ids[0]
            n = node_map[nid]
            return {nid: (0.0, 0.0)}, n.width, n.height

        succ, pred = build_adjacency(node_ids, edges)

        # Seed from Sugiyama for directional initialisation.
        sugiyama = SugiyamaNodeLayoutAlgorithm2D(
            direction=self.direction,
            layer_spacing=120,
            node_spacing=70,
        )
        comp_nodes = [node_map[nid] for nid in node_ids]
        seed_positions = sugiyama.compute(comp_nodes, edges)
        pos: dict[str, list[float]] = {
            nid: [seed_positions[nid][0], seed_positions[nid][1]]
            for nid in node_ids
        }

        sizes = {nid: (node_map[nid].width, node_map[nid].height) for nid in node_ids}
        avg_w = sum(sizes[n][0] for n in node_ids) / len(node_ids)

        desired_len = max(float(self.edge_length), avg_w * 0.8)
        overlap_push = 1800.0 * self.overlap_strength
        flow_push = 8.0 * self.flow_strength
        align_push = 0.07 * self.alignment_strength
        crossing_push = 600.0 * self.crossing_strength
        damping = self.damping
        temperature = self.temperature

        horizontal = self.direction in ("left_to_right", "right_to_left")
        reverse_flow = self.direction in ("right_to_left", "bottom_to_top")

        velocity: dict[str, list[float]] = {nid: [0.0, 0.0] for nid in node_ids}
        edge_pairs = [(e.source_id, e.target_id) for e in edges]

        for _ in range(max(1, self.iterations)):
            forces: dict[str, list[float]] = {nid: [0.0, 0.0] for nid in node_ids}

            # 1) Anti-overlap + pairwise repulsion
            for i, a in enumerate(node_ids):
                ax, ay = pos[a]
                aw, ah = sizes[a]
                for b in node_ids[i + 1:]:
                    bx, by = pos[b]
                    bw, bh = sizes[b]
                    acx = ax + aw * 0.5
                    acy = ay + ah * 0.5
                    bcx = bx + bw * 0.5
                    bcy = by + bh * 0.5
                    dx = acx - bcx
                    dy = acy - bcy
                    dist2 = dx * dx + dy * dy + 1e-6
                    dist = math.sqrt(dist2)
                    nx_d = dx / dist
                    ny_d = dy / dist
                    base = (self.repulsion * 3000.0) / dist2
                    fx = nx_d * base
                    fy = ny_d * base
                    overlap_x = min(ax + aw, bx + bw) - max(ax, bx)
                    overlap_y = min(ay + ah, by + bh) - max(ay, by)
                    if overlap_x > 0.0 and overlap_y > 0.0:
                        if overlap_x <= overlap_y:
                            sep = overlap_x + 6.0
                            dir_x = 1.0 if acx >= bcx else -1.0
                            fx += dir_x * overlap_push * sep / max(40.0, aw, bw)
                        else:
                            sep = overlap_y + 6.0
                            dir_y = 1.0 if acy >= bcy else -1.0
                            fy += dir_y * overlap_push * sep / max(30.0, ah, bh)
                    forces[a][0] += fx
                    forces[a][1] += fy
                    forces[b][0] -= fx
                    forces[b][1] -= fy

            # 2) Edge springs + directional ordering
            min_gap = max(avg_w * 0.25, 40.0)
            for src, dst in edge_pairs:
                sx, sy = pos[src]
                sw, sh = sizes[src]
                dx, dy = pos[dst]
                dw, dh = sizes[dst]
                scx = sx + sw * 0.5
                scy = sy + sh * 0.5
                dcx = dx + dw * 0.5
                dcy = dy + dh * 0.5
                vx = dcx - scx
                vy = dcy - scy
                dist = math.sqrt(vx * vx + vy * vy) + 1e-6
                spring = self.attraction * (dist - desired_len)
                sfx = (vx / dist) * spring
                sfy = (vy / dist) * spring
                forces[src][0] += sfx
                forces[src][1] += sfy
                forces[dst][0] -= sfx
                forces[dst][1] -= sfy
                if horizontal:
                    flow_delta = (dx - (sx + sw)) if not reverse_flow else (sx - (dx + dw))
                    if flow_delta < min_gap:
                        p = flow_push * (min_gap - flow_delta)
                        if not reverse_flow:
                            forces[src][0] -= p
                            forces[dst][0] += p
                        else:
                            forces[src][0] += p
                            forces[dst][0] -= p
                else:
                    flow_delta = (dy - (sy + sh)) if not reverse_flow else (sy - (dy + dh))
                    if flow_delta < min_gap:
                        p = flow_push * (min_gap - flow_delta)
                        if not reverse_flow:
                            forces[src][1] -= p
                            forces[dst][1] += p
                        else:
                            forces[src][1] += p
                            forces[dst][1] -= p

            # 3) Centre-line alignment to neighbours
            for nid in node_ids:
                neigh = list(pred[nid] | succ[nid])
                if not neigh:
                    continue
                if horizontal:
                    target = sum(pos[n][1] for n in neigh) / len(neigh)
                    forces[nid][1] += (target - pos[nid][1]) * align_push
                else:
                    target = sum(pos[n][0] for n in neigh) / len(neigh)
                    forces[nid][0] += (target - pos[nid][0]) * align_push

            # 4) Edge crossing pressure
            for i, (a, b) in enumerate(edge_pairs):
                ab_set = {a, b}
                a1 = (pos[a][0], pos[a][1])
                a2 = (pos[b][0], pos[b][1])
                for c, d in edge_pairs[i + 1:]:
                    if ab_set & {c, d}:
                        continue
                    b1 = (pos[c][0], pos[c][1])
                    b2 = (pos[d][0], pos[d][1])
                    if not segment_intersection(a1, a2, b1, b2):
                        continue
                    if horizontal:
                        dir_a = -1.0 if ((a1[1] + a2[1]) * 0.5) > ((b1[1] + b2[1]) * 0.5) else 1.0
                        forces[a][1] += crossing_push * dir_a
                        forces[b][1] += crossing_push * dir_a
                        forces[c][1] -= crossing_push * dir_a
                        forces[d][1] -= crossing_push * dir_a
                    else:
                        dir_a = -1.0 if ((a1[0] + a2[0]) * 0.5) > ((b1[0] + b2[0]) * 0.5) else 1.0
                        forces[a][0] += crossing_push * dir_a
                        forces[b][0] += crossing_push * dir_a
                        forces[c][0] -= crossing_push * dir_a
                        forces[d][0] -= crossing_push * dir_a

            # Integrate with momentum damping + temperature cap
            for nid in node_ids:
                fx = forces[nid][0]
                fy = forces[nid][1]
                mag = math.sqrt(fx * fx + fy * fy)
                if mag > temperature:
                    scale = temperature / mag
                    fx *= scale
                    fy *= scale
                velocity[nid][0] = velocity[nid][0] * damping + fx * (1.0 - damping)
                velocity[nid][1] = velocity[nid][1] * damping + fy * (1.0 - damping)
                pos[nid][0] += velocity[nid][0]
                pos[nid][1] += velocity[nid][1]

            temperature = max(2.0, temperature * 0.97)

        # 5) Final rect-overlap cleanup
        self._resolve_rect_overlaps(node_ids, pos, sizes, succ, pred)

        # Normalize to positive space
        min_x = min(pos[n][0] for n in node_ids)
        min_y = min(pos[n][1] for n in node_ids)
        norm_pos: dict[str, tuple[float, float]] = {}
        max_x = 0.0
        max_y = 0.0
        for nid in node_ids:
            x = pos[nid][0] - min_x
            y = pos[nid][1] - min_y
            norm_pos[nid] = (x, y)
            max_x = max(max_x, x + sizes[nid][0])
            max_y = max(max_y, y + sizes[nid][1])

        return norm_pos, max_x, max_y

    def _resolve_rect_overlaps(
        self,
        node_ids: list[str],
        pos: dict[str, list[float]],
        sizes: dict[str, tuple[float, float]],
        succ: dict[str, set[str]],
        pred: dict[str, set[str]],
    ) -> None:
        """Deterministically separate any remaining overlapping rectangles."""
        horizontal = self.direction in ("left_to_right", "right_to_left")
        reverse_flow = self.direction in ("right_to_left", "bottom_to_top")
        padding = self.final_padding
        ordered = sorted(node_ids)

        for _ in range(32):
            moved = False
            for i, a in enumerate(ordered):
                ax, ay = pos[a]
                aw, ah = sizes[a]
                for b in ordered[i + 1:]:
                    bx, by = pos[b]
                    bw, bh = sizes[b]
                    ov_x = min(ax + aw, bx + bw) - max(ax, bx)
                    ov_y = min(ay + ah, by + bh) - max(ay, by)
                    if ov_x <= 0.0 or ov_y <= 0.0:
                        continue
                    moved = True
                    connected = b in succ[a] or a in succ[b]
                    prefer_v = connected and horizontal
                    prefer_h = connected and not horizontal
                    sep_x = ov_x <= ov_y
                    if prefer_v:
                        sep_x = False
                    elif prefer_h:
                        sep_x = True
                    if sep_x:
                        shift = (ov_x + padding) * 0.5
                        acx = ax + aw * 0.5
                        bcx = bx + bw * 0.5
                        dir_x = 1.0 if acx >= bcx else -1.0
                        if b in succ[a]:
                            mult = -1.0 if reverse_flow else 1.0
                            pos[a][0] -= shift * mult
                            pos[b][0] += shift * mult
                        elif a in succ[b]:
                            mult = -1.0 if reverse_flow else 1.0
                            pos[b][0] -= shift * mult
                            pos[a][0] += shift * mult
                        else:
                            pos[a][0] += dir_x * shift
                            pos[b][0] -= dir_x * shift
                    else:
                        shift = (ov_y + padding) * 0.5
                        acy = ay + ah * 0.5
                        bcy = by + bh * 0.5
                        dir_y = 1.0 if acy >= bcy else -1.0
                        pos[a][1] += dir_y * shift
                        pos[b][1] -= dir_y * shift
            if not moved:
                break

        # Re-apply minimal directional edge gap
        min_gap = 20.0
        for src, dsts in succ.items():
            sx, sy = pos[src]
            sw, sh = sizes[src]
            for dst in dsts:
                dx, dy = pos[dst]
                dw, dh = sizes[dst]
                if horizontal:
                    gap = (dx - (sx + sw)) if not reverse_flow else (sx - (dx + dw))
                    if gap < min_gap:
                        delta = min_gap - gap
                        if not reverse_flow:
                            pos[src][0] -= delta * 0.5
                            pos[dst][0] += delta * 0.5
                        else:
                            pos[src][0] += delta * 0.5
                            pos[dst][0] -= delta * 0.5
                else:
                    gap = (dy - (sy + sh)) if not reverse_flow else (sy - (dy + dh))
                    if gap < min_gap:
                        delta = min_gap - gap
                        if not reverse_flow:
                            pos[src][1] -= delta * 0.5
                            pos[dst][1] += delta * 0.5
                        else:
                            pos[src][1] += delta * 0.5
                            pos[dst][1] -= delta * 0.5
