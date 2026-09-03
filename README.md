# AICAP: Intent-Centric Graph Analytics for Risk-Aware Atomic Cross-Chain Data Routing

Reference implementation of the **AICAP** protocol for cross-chain atomic swaps with risk-aware routing (**RISK-OPTI**), on-chain collateral arbitration (**LPManager**), and HTLC-style settlement (**SwapExecutor**). Includes the **AIOR** (AI Offline Routing) agent layer with optional [DeepSeek](https://platform.deepseek.com/) intent parsing.

> Companion repository for the AICAP paper. 

## Repository layout

```
AICAP/
├── contracts/          # Solidity: LPManager + SwapExecutor
├── aicap/              # Python: RISK-OPTI router, LPManager model, graph builder
├── agent/              # AIOR agent + DeepSeek interactive CLI
├── services/           # LP on-chain monitor (credit score sync)
├── scripts/            # Demo routing + smoke tests
└── docs/               # Architecture & paper citation
```

## Quick start

```bash
cd AICAP
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Demo: RISK-OPTI routing without LLM
python scripts/demo_route.py

# Interactive AIOR agent (DeepSeek optional)
export DEEPSEEK_API_KEY=sk-...   # or use --local for rule-based parsing
python -m agent.interact

# LP monitor (testnet RPC)
export SEPOLIA_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com
python -m services.lp_monitor --contract 0xYourLPManager
```

## Components

| Module | Role | Paper mapping |
|--------|------|---------------|
| `contracts/LPManager.sol` | Collateral bonds, `C_max`, slashing, credit events | Eq. (1), (13)–(14) |
| `contracts/SwapExecutor.sol` | Per-chain HTLC vault (lock / reveal / refund) | Four-stage swap |
| `aicap/risk_opti.py` | Multi-split A* with `ψ(n)=γn²` | RISK-OPTI algorithm |
| `agent/aior_agent.py` | NL intent → preference `P` → routing plan | AIOR / REE intent layer |
| `services/lp_monitor.py` | Index chain events, refresh `R_k(t)` | LP credit oracle |

## Solidity contracts

Contracts target **Solidity ^0.8.20**. Deploy per chain:

1. Deploy `LPManager` with `alphaHedge` (default `1.25e18` fixed-point).
2. Deploy `SwapExecutor(lpManager, timelockBlocks)` on each chain.
3. LPs call `registerLP(collateral)` then `depositInventory` on destination executors.

See `scripts/deploy_notes.md` for testnet addresses template.


## Relationship to `aicap_exp`

| | **AICAP** (this repo) | **aicap_exp** |
|--|----------------------|---------------|
| Purpose | Deployable reference / GitHub artifact | Paper experiment simulator |
| Contracts | Solidity | Python SimPy models |
| Figures | — | RQ1–RQ4 reproducible grid |

Algorithm semantics are aligned; `aicap_exp/simulation.py` is the behavioral spec used to port this code.

## License

MIT — see [LICENSE](LICENSE).
