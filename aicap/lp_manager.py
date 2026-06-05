"""LPManager — collateral capacity C_max and credit score R_k (Eq. 1, 14)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from aicap.config import ALPHA_HEDGE, CREDIT_EPSILON, LAMBDA_DECAY
from aicap.models import ExecutionOutcome, LPProfile


class LPManager:
    """
    Symmetric LP arbitration pool.

    Mirrors ``LPManager`` in aicap_exp/simulation.py; used by RISK-OPTI and LP monitor.
    On-chain counterpart: ``contracts/LPManager.sol``.
    """

    def __init__(
        self,
        profiles: Dict[str, LPProfile],
        alpha_hedge: float = ALPHA_HEDGE,
        lambda_decay: float = LAMBDA_DECAY,
        epsilon: float = CREDIT_EPSILON,
        clock: float = 0.0,
    ):
        self.profiles = profiles
        self.alpha_hedge = alpha_hedge
        self.lambda_decay = lambda_decay
        self.epsilon = epsilon
        self.clock = clock
        self.event_log: List[Dict[str, Any]] = []

    def tick(self, dt: float) -> None:
        self.clock += dt

    def get_c_max(self, lp_id: str) -> float:
        """Eq. (1): C_max,k = (V_coll - Σ L_k,i) / α_hedge."""
        p = self.profiles[lp_id]
        unreserved = p.source_chain_collateral - p.total_locked
        return max(0.0, unreserved / self.alpha_hedge)

    def reserve_collateral(self, lp_id: str, amount: float, subpath_id: str) -> bool:
        if amount <= 0 or amount > self.get_c_max(lp_id):
            return False
        p = self.profiles[lp_id]
        p.locked_subpaths[subpath_id] = p.locked_subpaths.get(subpath_id, 0.0) + amount
        return True

    def release_collateral(self, lp_id: str, subpath_id: str) -> None:
        self.profiles[lp_id].locked_subpaths.pop(subpath_id, None)

    def record_execution_event(
        self,
        lp_id: str,
        outcome: ExecutionOutcome,
        at_time: Optional[float] = None,
    ) -> float:
        t = self.clock if at_time is None else at_time
        if outcome == ExecutionOutcome.SUCCESS:
            s_j = 1
        elif outcome == ExecutionOutcome.SLASHING_ARBITRATION:
            s_j = 0
        else:
            s_j = 1

        p = self.profiles[lp_id]
        p.history.append((t, s_j))
        self.event_log.append({"t": t, "lp_id": lp_id, "outcome": outcome.value, "s_j": s_j})
        return self.update_credit_score(lp_id, t)

    def update_credit_score(self, lp_id: str, at_time: Optional[float] = None) -> float:
        """Eq. (14): exponential decay filter on event history H_k."""
        t = self.clock if at_time is None else at_time
        p = self.profiles[lp_id]
        if not p.history:
            p.R_k = 0.0
            return p.R_k

        numer = 0.0
        denom = self.epsilon
        for t_j, s_j in p.history:
            w = np.exp(-self.lambda_decay * (t - t_j))
            numer += s_j * w
            denom += w

        p.R_k = float(np.clip(1.0 - numer / denom, 0.0, 1.0))
        return p.R_k

    def slash_collateral(
        self,
        lp_id: str,
        slash_amount: float,
        subpath_id: Optional[str] = None,
    ) -> float:
        p = self.profiles[lp_id]
        if subpath_id:
            self.release_collateral(lp_id, subpath_id)
        p.source_chain_collateral = max(0.0, p.source_chain_collateral - slash_amount)
        self.record_execution_event(lp_id, ExecutionOutcome.SLASHING_ARBITRATION)
        return slash_amount

    def sync_from_chain_events(self, events: List[Dict[str, Any]]) -> None:
        """Ingest LPManager.sol ExecutionRecorded events (LP monitor feed)."""
        for ev in sorted(events, key=lambda e: e.get("block", 0)):
            lp_id = ev["lp_id"]
            if lp_id not in self.profiles:
                continue
            outcome = ExecutionOutcome(ev["outcome"])
            ts = float(ev.get("timestamp", self.clock))
            self.record_execution_event(lp_id, outcome, at_time=ts)
