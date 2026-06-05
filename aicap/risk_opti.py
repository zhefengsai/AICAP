"""RISK-OPTI — multi-split risk-aware A* routing (AICAP core algorithm)."""

from __future__ import annotations

import time
from heapq import heappop, heappush
from typing import Any, Callable, Dict, List, Optional, Tuple

import networkx as nx
import numpy as np

from aicap.config import (
    BETA_EXEC,
    CHAINS,
    GAMMA_GAS,
    GAMMA_RISK_COLL,
    N_MAX_SPLITS,
    P_PROCESSING_S,
    T_BUFFER_S,
)
from aicap.graph import attach_risk_to_graph, sync_graph_capacities
from aicap.lp_manager import LPManager
from aicap.models import LPProfile, PathEdge, PreferenceVector, RoutingResult, SubOrder


def edge_latency(chain_id: str) -> float:
    return float(CHAINS[chain_id]["confirm_delay_s"])


def bound_splits(q_total: float, G: nx.MultiDiGraph) -> int:
    caps = [d["C_max"] for _, _, d in G.edges(data=True) if d.get("C_max", 0) > 0]
    if not caps:
        return 1
    min_cap = min(caps)
    return max(1, min(N_MAX_SPLITS, int(np.ceil(q_total / max(min_cap, 1e-9)))))


def equi_partition(q_total: float, n: int) -> List[float]:
    base = q_total / n
    parts = [base] * n
    parts[-1] = q_total - base * (n - 1)
    return parts


def _multiedges(G: nx.MultiDiGraph) -> List[Tuple[str, str, int, Dict[str, Any]]]:
    return list(G.edges(keys=True, data=True))


def _heuristic_to_dst(G: nx.MultiDiGraph, node: str, dst: str, P: PreferenceVector) -> float:
    if node == dst:
        return 0.0
    h = CHAINS[dst]["confirm_delay_s"] - CHAINS[node]["confirm_delay_s"]
    return max(0.0, P.omega_time * h)


def astar_search(
    G: nx.MultiDiGraph,
    src: str,
    dst: str,
    edge_weight: Callable[[str, str, int, Dict[str, Any]], float],
    min_capacity: float = 0.0,
    P: Optional[PreferenceVector] = None,
    qty_need: float = 0.0,
    profiles: Optional[Dict[str, LPProfile]] = None,
) -> List[PathEdge]:
    if src == dst:
        return []

    P = P or PreferenceVector(1 / 3, 1 / 3, 1 / 3)
    open_set: List[Tuple[float, float, str, List[PathEdge]]] = []
    heappush(open_set, (0.0, 0.0, src, []))
    best_g: Dict[str, float] = {src: 0.0}

    while open_set:
        _f, g_score, node, path = heappop(open_set)
        if node == dst:
            return path
        if g_score > best_g.get(node, float("inf")):
            continue

        for u, v, key, data in _multiedges(G):
            if u != node:
                continue
            if min_capacity > 0 and data.get("C_max", 0.0) < min_capacity:
                continue
            if profiles is not None and qty_need > 0 and v == dst:
                lp = profiles[data["lp_id"]]
                asset = data.get("settle_asset", "BTC")
                lp_inv = lp.eth_inventory.get(v, 0.0) if asset == "ETH" else lp.target_chain_inventory.get(v, 0.0)
                if lp_inv + 1e-9 < qty_need:
                    continue
            w = edge_weight(u, v, key, data)
            new_g = g_score + w
            if new_g < best_g.get(v, float("inf")):
                best_g[v] = new_g
                step = PathEdge(
                    u=u, v=v, key=key, lp_id=data["lp_id"],
                    f_e=data["f_e"], g_e=data["g_e"],
                    l_e=edge_latency(u), R_k=data.get("R_k", 0.0),
                )
                h = _heuristic_to_dst(G, v, dst, P)
                heappush(open_set, (new_g + h, new_g, v, path + [step]))

    return []


def path_utility(path: List[PathEdge], P: PreferenceVector) -> float:
    P = P.normalized()
    total = 0.0
    for e in path:
        total += (
            P.omega_cost * (e.f_e + e.g_e)
            + P.omega_time * (e.l_e + P_PROCESSING_S)
            + P.omega_risk * e.R_k
        )
    return total


class RiskOptiEngine:
    """
    AICAP RISK-OPTI router.

    Searches split count n ∈ [1, n_cap], equi-partitions the macro order,
    runs capacity-pruned A* per chunk, adds ψ(n) = γ·n², picks minimum utility.
    """

    name = "RISK-OPTI"

    def __init__(
        self,
        gamma_gas: float = GAMMA_GAS,
        n_max: Optional[int] = None,
        min_splits: int = 1,
        apply_psi: bool = True,
        use_credit: bool = True,
    ):
        self.gamma_gas = gamma_gas
        self.n_max = n_max
        self.min_splits = max(1, min_splits)
        self.apply_psi = apply_psi
        self.use_credit = use_credit

    def route(
        self,
        G: nx.MultiDiGraph,
        src: str,
        dst: str,
        q_total: float,
        lp_manager: LPManager,
        P: Optional[PreferenceVector] = None,
    ) -> RoutingResult:
        t0 = time.perf_counter()
        P = (P or PreferenceVector(0.33, 0.33, 0.34)).normalized()
        attach_risk_to_graph(G, lp_manager)
        sync_graph_capacities(G, lp_manager)

        n_cap = self.n_max or bound_splits(q_total, G)
        best_orders: List[SubOrder] = []
        best_utility = float("inf")
        best_n = 0

        def edge_w(_u: str, _v: str, _k: int, d: Dict[str, Any]) -> float:
            risk_term = P.omega_risk * d.get("R_k", 0.0) if self.use_credit else 0.0
            return (
                P.omega_cost * (d["f_e"] + d["g_e"])
                + P.omega_time * (edge_latency(_u) + P_PROCESSING_S)
                + risk_term
            )

        for n in range(self.min_splits, n_cap + 1):
            chunks = equi_partition(q_total, n)
            current_orders: List[SubOrder] = []
            current_utility = 0.0
            failed = False

            for q_i in chunks:
                path = astar_search(
                    G, src, dst, edge_weight=edge_w,
                    min_capacity=q_i, P=P, qty_need=q_i,
                    profiles=lp_manager.profiles,
                )
                if not path:
                    failed = True
                    break
                current_utility += path_utility(path, P)
                coll = GAMMA_RISK_COLL * q_i * sum(e.R_k for e in path)
                t_exec = BETA_EXEC * sum(e.l_e + P_PROCESSING_S for e in path) + T_BUFFER_S
                current_orders.append(SubOrder(quantity=q_i, path=path, T_exec=t_exec, coll_req=coll))

            if failed:
                continue
            if self.apply_psi:
                current_utility += self.gamma_gas * (n**2)

            if current_utility < best_utility:
                best_utility = current_utility
                best_orders = current_orders
                best_n = n

        feasible = len(best_orders) > 0
        label = self.name
        if not self.apply_psi:
            label += "_w/o_psi"
        if not self.use_credit:
            label += "_w/o_R"

        return RoutingResult(
            engine=label,
            src=src,
            dst=dst,
            total_qty=q_total,
            sub_orders=best_orders,
            total_utility=best_utility if feasible else float("inf"),
            n_splits=best_n,
            compute_ms=(time.perf_counter() - t0) * 1000,
            feasible=feasible,
            note=f"searched n=1..{n_cap}, psi={'on' if self.apply_psi else 'off'}",
        )
