#!/usr/bin/env python3
"""Smoke test: RISK-OPTI routing on synthetic 200-LP graph."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicap.config import MACRO_ORDER_BTC
from aicap.graph import build_liquidity_multigraph, initialize_lp_profiles
from aicap.lp_manager import LPManager
from aicap.models import PreferenceVector
from aicap.risk_opti import RiskOptiEngine


def main() -> int:
    profiles = initialize_lp_profiles(num_lps=200, seed=42)
    lp_manager = LPManager(profiles)
    G = build_liquidity_multigraph(profiles, num_edges=200, seed=42)

    P = PreferenceVector(1 / 3, 1 / 3, 1 / 3).normalized()
    engine = RiskOptiEngine()
    result = engine.route(G, "Chain_2", "Chain_3", MACRO_ORDER_BTC, lp_manager, P)

    print("=== AICAP RISK-OPTI Demo ===")
    print(f"feasible: {result.feasible}")
    print(f"splits:   {result.n_splits}")
    print(f"utility:  {result.total_utility:.4f}")
    print(f"compute:  {result.compute_ms:.2f} ms")
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.feasible else 1


if __name__ == "__main__":
    raise SystemExit(main())
