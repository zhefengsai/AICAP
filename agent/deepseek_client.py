"""DeepSeek API client for natural-language intent parsing."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import requests

DEFAULT_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"

INTENT_SYSTEM_PROMPT = """You are the AIOR intent parser for AICAP cross-chain atomic swaps.
Extract structured routing preferences from user text.

Return ONLY valid JSON with keys:
- src_chain: one of "Chain_1" (Ethereum Sepolia), "Chain_2" (BSC Testnet), "Chain_3" (Base Sepolia)
- dst_chain: same enum
- quantity_btc: float (macro order size in BTC)
- settle_asset: "BTC" or "ETH"
- preference: object with cost, time, risk floats summing to ~1.0
- notes: short string

Examples:
- "fast swap 10 BTC from BSC to Base, minimize latency" → time-heavy P
- "cheapest route, I can wait" → cost-heavy P
- "safest LP, avoid risky nodes" → risk-heavy P
"""


class DeepSeekClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = (base_url or os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE)).rstrip("/")
        self.model = model or os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL)

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def parse_intent(self, user_text: str) -> Dict[str, Any]:
        if not self.available:
            raise RuntimeError("DEEPSEEK_API_KEY not set")

        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)
