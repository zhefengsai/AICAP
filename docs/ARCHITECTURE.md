# AICAP architecture

## Layer stack

```
┌─────────────────────────────────────────────────────────┐
│  AIOR Agent (agent/)                                    │
│  NL intent → preference P → offline routing plan        │
│  Optional: DeepSeek API for intent parsing                │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│  RISK-OPTI Router (aicap/risk_opti.py)                  │
│  Multi-split A* + C_max pruning + ψ(n)=γn²              │
└──────────────────────────┬──────────────────────────────┘
                           │ reads R_k, C_max
┌──────────────────────────▼──────────────────────────────┐
│  LP Monitor (services/lp_monitor.py)                    │
│  Index ExecutionRecorded events → refresh R_k(t)        │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│  On-chain (contracts/)                                  │
│  LPManager: collateral, slash, events                   │
│  SwapExecutor: HTLC lock / reveal / refund              │
└─────────────────────────────────────────────────────────┘
```

## Four-stage swap lifecycle

| Stage | Actor | On-chain / off-chain |
|-------|-------|----------------------|
| 1 Intent | User → AIOR | Off-chain NL → structured intent |
| 2 Lock | SwapExecutor | `lockSwap` + `reserveCollateral` |
| 3 Reveal | User / LP | `revealPreimage` |
| 4 Arbitration | Arbitrator | `refund` or `arbitrateSlash` |

## Credit model (Eq. 14)

`R_k(t) = 1 - Σ s_j · e^{-λ(t-t_j)} / (ε + Σ e^{-λ(t-t_j)})`

- `s_j = 1` on success, `s_j = 0` on slashing
- Computed in `aicap/lp_manager.py` and mirrored off-chain by LP monitor
- RISK-OPTI edge weight includes `P_risk · R_k`

## Paper ↔ code mapping

| Paper symbol | Code location |
|--------------|---------------|
| `C_max,k` | `LPManager.get_c_max` / `LPManager.sol:getCMax` |
| `R_k(t)` | `LPManager.update_credit_score` |
| `ψ(n)` | `RiskOptiEngine` with `apply_psi=True` |
| `P = (ω_c, ω_t, ω_r)` | `PreferenceVector` / AIOR intent parser |
