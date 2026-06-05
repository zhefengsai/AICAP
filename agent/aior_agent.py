"""AIOR agent — NL intent → preference P → RISK-OPTI routing plan."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import networkx as nx

from aicap.config import MACRO_ORDER_BTC
from aicap.graph import apply_gas_prices, build_liquidity_multigraph, initialize_lp_profiles
from aicap.lp_manager import LPManager
from aicap.models import PreferenceVector
from aicap.risk_opti import RiskOptiEngine
from agent.deepseek_client import DeepSeekClient

CHAIN_ALIASES = {
    "ethereum": "Chain_1", "sepolia": "Chain_1", "eth": "Chain_1", "chain_1": "Chain_1",
    "bsc": "Chain_2", "binance": "Chain_2", "chain_2": "Chain_2",
    "base": "Chain_3", "chain_3": "Chain_3",
}


@dataclass
class SwapIntent:
    src_chain: str
    dst_chain: str
    quantity_btc: float
    settle_asset: str
    preference: PreferenceVector
    raw_text: str
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "src_chain": self.src_chain,
            "dst_chain": self.dst_chain,
            "quantity_btc": self.quantity_btc,
            "settle_asset": self.settle_asset,
            "preference": self.preference.as_dict(),
            "notes": self.notes,
        }


class AIORAgent:
    """
    AI Offline Routing agent.

    1. Parse user intent (DeepSeek or local rules)
    2. Build / refresh liquidity graph with LPManager state
    3. Run RISK-OPTI
    4. Emit offline routing plan (sub-orders + collateral requirements)
    """

    def __init__(
        self,
        lp_manager: Optional[LPManager] = None,
        graph: Optional[nx.MultiDiGraph] = None,
        deepseek: Optional[DeepSeekClient] = None,
        seed: int = 42,
    ):
        profiles = initialize_lp_profiles(num_lps=200, seed=seed)
        self.lp_manager = lp_manager or LPManager(profiles)
        self.graph = graph or build_liquidity_multigraph(profiles, num_edges=200, seed=seed)
        self.engine = RiskOptiEngine()
        self.deepseek = deepseek or DeepSeekClient()

    def parse_intent_local(self, text: str) -> SwapIntent:
        """Rule-based fallback when DeepSeek is unavailable."""
        lower = text.lower()
        src, dst = "Chain_2", "Chain_3"
        for alias, chain in CHAIN_ALIASES.items():
            if alias in lower:
                if "from" in lower and lower.index(alias) < lower.find("to") if "to" in lower else True:
                    src = chain
                else:
                    dst = chain

        qty_match = re.search(r"(\d+(?:\.\d+)?)\s*btc", lower)
        quantity = float(qty_match.group(1)) if qty_match else MACRO_ORDER_BTC

        if any(w in lower for w in ("fast", "quick", "latency", "speed")):
            P = PreferenceVector(0.1, 0.8, 0.1)
        elif any(w in lower for w in ("cheap", "cost", "fee", "gas")):
            P = PreferenceVector(0.8, 0.1, 0.1)
        elif any(w in lower for w in ("safe", "risk", "secure", "trust")):
            P = PreferenceVector(0.1, 0.1, 0.8)
        else:
            P = PreferenceVector(1 / 3, 1 / 3, 1 / 3)

        asset = "ETH" if "eth" in lower and "btc" not in lower else "BTC"
        return SwapIntent(src, dst, quantity, asset, P.normalized(), text, notes="local-parser")

    def parse_intent(self, text: str, *, use_deepseek: bool = True) -> SwapIntent:
        if use_deepseek and self.deepseek.available:
            try:
                data = self.deepseek.parse_intent(text)
                pref = data.get("preference", {})
                P = PreferenceVector(
                    float(pref.get("cost", 0.33)),
                    float(pref.get("time", 0.33)),
                    float(pref.get("risk", 0.34)),
                ).normalized()
                return SwapIntent(
                    src_chain=data.get("src_chain", "Chain_2"),
                    dst_chain=data.get("dst_chain", "Chain_3"),
                    quantity_btc=float(data.get("quantity_btc", MACRO_ORDER_BTC)),
                    settle_asset=data.get("settle_asset", "BTC"),
                    preference=P,
                    raw_text=text,
                    notes=data.get("notes", "deepseek"),
                )
            except Exception:
                pass
        return self.parse_intent_local(text)

    def route(self, intent: SwapIntent, gas_prices: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        G = self.graph.copy()
        for _u, _v, _k, data in G.edges(keys=True, data=True):
            data["settle_asset"] = intent.settle_asset
        if gas_prices:
            apply_gas_prices(G, gas_prices)

        result = self.engine.route(
            G, intent.src_chain, intent.dst_chain,
            intent.quantity_btc, self.lp_manager, intent.preference,
        )
        return {
            "intent": intent.to_dict(),
            "routing": result.to_dict(),
            "offline_plan": self._build_offline_plan(result),
        }

    def _build_offline_plan(self, result) -> Dict[str, Any]:
        """Pre-signed execution matrix skeleton for REE / TEE layer."""
        legs = []
        for i, so in enumerate(result.sub_orders):
            legs.append({
                "leg_id": f"leg_{i}",
                "quantity_btc": so.quantity,
                "collateral_required": so.coll_req,
                "max_exec_time_s": so.T_exec,
                "path_lp_ids": [e.lp_id for e in so.path],
                "hashlock_placeholder": f"0x{'0' * 64}",
            })
        return {
            "n_splits": result.n_splits,
            "legs": legs,
            "signing_note": "Offline matrix: sign per-leg HTLC params before broadcast",
        }

    def handle(self, user_text: str, *, use_deepseek: bool = True) -> str:
        intent = self.parse_intent(user_text, use_deepseek=use_deepseek)
        plan = self.route(intent)
        return json.dumps(plan, indent=2)
