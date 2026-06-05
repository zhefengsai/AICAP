"""Shared datatypes for AICAP routing and LP state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple


class LPTrueType(str, Enum):
    HONEST = "Type-I"
    UNSTABLE = "Type-II"
    BYZANTINE = "Type-III"


class ExecutionOutcome(str, Enum):
    SUCCESS = "Success"
    TIMEOUT_REFUND = "Timeout-Refund"
    SLASHING_ARBITRATION = "Slashing-Arbitration"


@dataclass
class LPProfile:
    lp_id: str
    true_type: LPTrueType
    fee_rate_f: float
    host_chain: str
    source_chain_collateral: float
    target_chain_inventory: Dict[str, float]
    eth_inventory: Dict[str, float] = field(default_factory=dict)
    history: List[Tuple[float, int]] = field(default_factory=list)
    R_k: float = 0.0
    locked_subpaths: Dict[str, float] = field(default_factory=dict)

    @property
    def total_locked(self) -> float:
        return sum(self.locked_subpaths.values())

    @property
    def free_inventory_btc(self) -> float:
        return sum(self.target_chain_inventory.values())


@dataclass
class PreferenceVector:
    omega_cost: float
    omega_time: float
    omega_risk: float

    def normalized(self) -> PreferenceVector:
        s = self.omega_cost + self.omega_time + self.omega_risk
        if s <= 0:
            return PreferenceVector(1 / 3, 1 / 3, 1 / 3)
        return PreferenceVector(self.omega_cost / s, self.omega_time / s, self.omega_risk / s)

    def as_dict(self) -> Dict[str, float]:
        p = self.normalized()
        return {"cost": p.omega_cost, "time": p.omega_time, "risk": p.omega_risk}


@dataclass
class PathEdge:
    u: str
    v: str
    key: int
    lp_id: str
    f_e: float
    g_e: float
    l_e: float
    R_k: float


@dataclass
class SubOrder:
    quantity: float
    path: List[PathEdge]
    T_exec: float
    coll_req: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quantity": self.quantity,
            "T_exec_s": self.T_exec,
            "collateral_required": self.coll_req,
            "hops": [
                {"from": e.u, "to": e.v, "lp_id": e.lp_id, "fee": e.f_e, "gas": e.g_e, "R_k": e.R_k}
                for e in self.path
            ],
        }


@dataclass
class RoutingResult:
    engine: str
    src: str
    dst: str
    total_qty: float
    sub_orders: List[SubOrder]
    total_utility: float
    n_splits: int
    compute_ms: float
    feasible: bool = True
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine": self.engine,
            "src": self.src,
            "dst": self.dst,
            "total_qty": self.total_qty,
            "n_splits": self.n_splits,
            "total_utility": self.total_utility,
            "compute_ms": self.compute_ms,
            "feasible": self.feasible,
            "note": self.note,
            "sub_orders": [so.to_dict() for so in self.sub_orders],
        }
