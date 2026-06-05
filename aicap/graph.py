"""Liquidity multigraph construction and LP profile initialization."""

from __future__ import annotations

import random
from typing import Dict, Optional

import networkx as nx

from aicap.config import (
    CHAIN_IDS,
    CHAINS,
    K_MIN_COLLATERAL,
    LP_INVENTORY_BTC_MAX,
    LP_INVENTORY_BTC_MIN,
    LP_TYPE_RATIOS,
    NUM_LP_EDGES,
    RNG_SEED,
)
from aicap.lp_manager import LPManager
from aicap.models import LPProfile, LPTrueType


def initialize_lp_profiles(num_lps: int = NUM_LP_EDGES, seed: int = RNG_SEED) -> Dict[str, LPProfile]:
    rng = random.Random(seed)
    type_pool: list[LPTrueType] = []
    for type_name, ratio in LP_TYPE_RATIOS.items():
        count = int(num_lps * ratio)
        type_pool.extend([LPTrueType(type_name)] * count)
    while len(type_pool) < num_lps:
        type_pool.append(LPTrueType.HONEST)
    type_pool = type_pool[:num_lps]
    rng.shuffle(type_pool)

    profiles: Dict[str, LPProfile] = {}
    for i in range(num_lps):
        lp_id = f"LP_{i:04d}"
        host_chain = rng.choice(CHAIN_IDS)
        collateral = rng.uniform(K_MIN_COLLATERAL, 25.0)
        inventory = {
            chain: round(rng.uniform(LP_INVENTORY_BTC_MIN, LP_INVENTORY_BTC_MAX), 6)
            for chain in CHAIN_IDS
        }
        eth_inv = {chain: round(rng.uniform(5.0, 40.0), 4) for chain in CHAIN_IDS}
        profiles[lp_id] = LPProfile(
            lp_id=lp_id,
            true_type=type_pool[i],
            fee_rate_f=rng.uniform(0.0001, 0.0015),
            host_chain=host_chain,
            source_chain_collateral=collateral,
            target_chain_inventory=inventory,
            eth_inventory=eth_inv,
        )
    return profiles


def build_liquidity_multigraph(
    lp_profiles: Optional[Dict[str, LPProfile]] = None,
    num_edges: int = NUM_LP_EDGES,
    seed: int = RNG_SEED,
) -> nx.MultiDiGraph:
    rng = random.Random(seed)
    if lp_profiles is None:
        lp_profiles = initialize_lp_profiles(num_edges, seed=seed)

    G = nx.MultiDiGraph()
    for chain_id in CHAIN_IDS:
        G.add_node(chain_id, **CHAINS[chain_id])

    channel_pairs = [(u, v) for u in CHAIN_IDS for v in CHAIN_IDS if u != v]
    for i in range(num_edges):
        lp_id = f"LP_{i:04d}"
        profile = lp_profiles[lp_id]
        src, dst = rng.choice(channel_pairs)
        base_gas = CHAINS[src]["base_gas_multiplier"]
        G.add_edge(
            src,
            dst,
            key=i,
            lp_id=lp_id,
            true_type=profile.true_type.value,
            f_e=profile.fee_rate_f,
            g_e=base_gas * 20.0,
            C_max=0.0,
            C_locked=0.0,
            chain_gas_key=src,
            host_chain=profile.host_chain,
            settle_asset="BTC",
        )
    return G


def sync_graph_capacities(G: nx.MultiDiGraph, lp_manager: LPManager) -> None:
    for _u, _v, _k, data in G.edges(keys=True, data=True):
        lp_id = data["lp_id"]
        data["C_max"] = lp_manager.get_c_max(lp_id)
        data["C_locked"] = lp_manager.profiles[lp_id].total_locked


def attach_risk_to_graph(G: nx.MultiDiGraph, lp_manager: LPManager) -> None:
    for _u, _v, _k, data in G.edges(keys=True, data=True):
        data["R_k"] = lp_manager.profiles[data["lp_id"]].R_k


def apply_gas_prices(G: nx.MultiDiGraph, gas_row: Dict[str, float]) -> None:
    for u, _v, _k, data in G.edges(keys=True, data=True):
        chain_key = data.get("chain_gas_key", u)
        gas_price = gas_row.get(chain_key, 1.0)
        multiplier = CHAINS[chain_key]["base_gas_multiplier"]
        data["g_e"] = float(gas_price) * float(multiplier)
