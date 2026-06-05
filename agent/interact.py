#!/usr/bin/env python3
"""Interactive AIOR CLI — natural language → RISK-OPTI routing plan."""

from __future__ import annotations

import argparse
import sys

from agent.aior_agent import AIORAgent
from agent.deepseek_client import DeepSeekClient


def main() -> int:
    parser = argparse.ArgumentParser(description="AIOR interactive agent (DeepSeek optional)")
    parser.add_argument("--local", action="store_true", help="Use rule-based parser only")
    parser.add_argument("--prompt", type=str, help="Single-shot intent (non-interactive)")
    args = parser.parse_args()

    client = DeepSeekClient()
    agent = AIORAgent(deepseek=client)
    use_llm = not args.local and client.available

    if not use_llm:
        print("[AIOR] DeepSeek unavailable — using local rule parser. Set DEEPSEEK_API_KEY to enable LLM.")

    if args.prompt:
        print(agent.handle(args.prompt, use_deepseek=use_llm))
        return 0

    print("AICAP AIOR Agent — type swap intent (empty line to quit)")
    print("Example: Swap 10 BTC from BSC to Base, prioritize low latency\n")

    while True:
        try:
            line = input("intent> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            break
        try:
            print(agent.handle(line, use_deepseek=use_llm))
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
