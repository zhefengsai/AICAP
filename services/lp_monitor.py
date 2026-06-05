#!/usr/bin/env python3
"""
LP Monitor — watch LPManager / SwapExecutor events and refresh R_k(t).

Feeds updated credit scores into the local LPManager used by RISK-OPTI.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from aicap.graph import attach_risk_to_graph, build_liquidity_multigraph, initialize_lp_profiles
from aicap.lp_manager import LPManager
from aicap.models import ExecutionOutcome

STATE_PATH = Path("data/monitor_state.json")

# Minimal ABI fragments for event indexing
LPMANAGER_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "lpId", "type": "bytes32"},
            {"indexed": False, "name": "outcome", "type": "uint8"},
            {"indexed": False, "name": "timestamp", "type": "uint256"},
            {"indexed": False, "name": "sJ", "type": "uint8"},
        ],
        "name": "ExecutionRecorded",
        "type": "event",
    },
]

OUTCOME_MAP = {
    0: ExecutionOutcome.SUCCESS,
    1: ExecutionOutcome.TIMEOUT_REFUND,
    2: ExecutionOutcome.SLASHING_ARBITRATION,
}


def _bytes32_to_lp_id(raw: bytes) -> str:
    """Map on-chain bytes32 LP id to simulator LP_XXXX label if hex-encoded index."""
    hex_str = raw.hex()
    try:
        idx = int(hex_str[-4:], 16) % 10000
        return f"LP_{idx:04d}"
    except ValueError:
        return f"LP_{hex_str[:8]}"


class LPMonitor:
    def __init__(
        self,
        rpc_url: str,
        contract_address: str,
        lp_manager: Optional[LPManager] = None,
        poll_interval_s: float = 12.0,
    ):
        self.rpc_url = rpc_url
        self.contract_address = contract_address
        self.poll_interval_s = poll_interval_s
        self.lp_manager = lp_manager or LPManager(initialize_lp_profiles(200))
        self.graph = build_liquidity_multigraph(self.lp_manager.profiles, num_edges=200)
        self._w3 = None
        self._contract = None
        self._last_block = 0

    def _connect(self) -> None:
        from web3 import Web3

        self._w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        if not self._w3.is_connected():
            raise ConnectionError(f"RPC not reachable: {self.rpc_url}")
        self._contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(self.contract_address),
            abi=LPMANAGER_ABI,
        )
        self._last_block = self._w3.eth.block_number

    def poll_events(self) -> List[Dict[str, Any]]:
        if self._contract is None:
            self._connect()

        assert self._w3 is not None and self._contract is not None
        current = self._w3.eth.block_number
        if current <= self._last_block:
            return []

        logs = self._contract.events.ExecutionRecorded.get_logs(
            fromBlock=self._last_block + 1,
            toBlock=current,
        )
        self._last_block = current

        events: List[Dict[str, Any]] = []
        for log in logs:
            args = log["args"]
            lp_id = _bytes32_to_lp_id(args["lpId"])
            outcome_idx = int(args["outcome"])
            outcome = OUTCOME_MAP.get(outcome_idx, ExecutionOutcome.SUCCESS)
            events.append({
                "lp_id": lp_id,
                "outcome": outcome.value,
                "timestamp": float(args["timestamp"]),
                "block": log["blockNumber"],
            })
        return events

    def sync(self, events: List[Dict[str, Any]]) -> Dict[str, float]:
        self.lp_manager.sync_from_chain_events(events)
        attach_risk_to_graph(self.graph, self.lp_manager)
        return {lp_id: p.R_k for lp_id, p in self.lp_manager.profiles.items()}

    def run_loop(self, max_iterations: Optional[int] = None) -> None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        it = 0
        print(f"[LPMonitor] watching {self.contract_address} @ {self.rpc_url}")

        while max_iterations is None or it < max_iterations:
            try:
                events = self.poll_events()
                if events:
                    scores = self.sync(events)
                    payload = {
                        "updated_at": time.time(),
                        "events": events,
                        "R_k_sample": dict(list(scores.items())[:5]),
                    }
                    STATE_PATH.write_text(json.dumps(payload, indent=2))
                    print(f"[LPMonitor] synced {len(events)} events → {STATE_PATH}")
                else:
                    print(f"[LPMonitor] no new events (block {self._last_block})")
            except Exception as exc:
                print(f"[LPMonitor] error: {exc}")

            it += 1
            time.sleep(self.poll_interval_s)


def main() -> int:
    parser = argparse.ArgumentParser(description="AICAP LP on-chain monitor")
    parser.add_argument("--contract", required=True, help="LPManager contract address")
    parser.add_argument("--rpc", default=os.environ.get("SEPOLIA_RPC_URL", ""), help="JSON-RPC URL")
    parser.add_argument("--interval", type=float, default=12.0, help="Poll interval (seconds)")
    parser.add_argument("--once", action="store_true", help="Single poll then exit")
    args = parser.parse_args()

    if not args.rpc:
        print("Set --rpc or SEPOLIA_RPC_URL")
        return 1

    monitor = LPMonitor(args.rpc, args.contract, poll_interval_s=args.interval)
    if args.once:
        events = monitor.poll_events()
        scores = monitor.sync(events)
        print(json.dumps({"events": events, "n_lps": len(scores)}, indent=2))
        return 0

    monitor.run_loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
