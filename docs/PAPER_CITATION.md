# Citing AICAP in your paper

## LaTeX artifact paths

```latex
% Reference implementation (GitHub)
We open-source the AICAP prototype at
\texttt{github.com/YOUR\_ORG/AICAP}, including the
\texttt{LPManager} and \texttt{SwapExecutor} Solidity contracts,
the \texttt{RISK-OPTI} router (\texttt{aicap/risk\_opti.py}),
and the \texttt{AIOR} intent agent (\texttt{agent/aior\_agent.py}).

% Experiment reproduction (separate repo)
Simulation results are reproduced via
\texttt{github.com/YOUR\_ORG/aicap\_exp} (\texttt{python simulation.py --mode figures}).
```

## Component table for evaluation section

| Artifact | Path | Role |
|----------|------|------|
| LPManager contract | `contracts/LPManager.sol` | Collateral arbitration pool |
| SwapExecutor contract | `contracts/SwapExecutor.sol` | Per-chain HTLC vault |
| RISK-OPTI | `aicap/risk_opti.py` | Risk-aware multi-split router |
| AIOR agent | `agent/aior_agent.py` | Offline intent → routing plan |
| LP monitor | `services/lp_monitor.py` | On-chain `R_k` synchronization |
| Interactive demo | `agent/interact.py` | DeepSeek-powered CLI |

## BibTeX

```bibtex
@software{aicap_impl_2026,
  title   = {{AICAP}: Reference Implementation},
  author  = {AICAP Authors},
  year    = {2026},
  url     = {https://github.com/YOUR_ORG/AICAP},
  note    = {Solidity contracts, RISK-OPTI router, AIOR agent}
}
```

Replace `YOUR_ORG` with your GitHub username or organization before upload.
