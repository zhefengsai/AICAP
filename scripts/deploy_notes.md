# Contract deployment notes

## Prerequisites

- Solidity compiler ^0.8.20 (Foundry or Hardhat)
- Testnet ETH on Sepolia / BSC Testnet / Base Sepolia

## Deploy order

```bash
# 1. LPManager — alphaHedge = 1.25 * 1e18, arbitrator = deployer or multisig
forge create contracts/LPManager.sol:LPManager \
  --constructor-args 1250000000000000000 $ARBITRATOR

# 2. SwapExecutor per chain — timelockBlocks ≈ 720 (~2h on Sepolia)
forge create contracts/SwapExecutor.sol:SwapExecutor \
  --constructor-args $LPMANAGER 720 $ARBITRATOR
```

Record addresses in `.env`:

```
LPMANAGER_ADDRESS_SEPOLIA=0x...
SWAP_EXECUTOR_ADDRESS_SEPOLIA=0x...
```

## LP onboarding

1. LP calls `registerLP(lpId)` with collateral deposit.
2. Arbitrator (AIOR backend) calls `reserveCollateral` before Stage-2 lock.
3. User calls `SwapExecutor.lockSwap` with hashlock.
4. On success: `revealPreimage`; on timeout: `refund`; on withhold: `arbitrateSlash`.

## LP monitor

```bash
python -m services.lp_monitor \
  --contract $LPMANAGER_ADDRESS_SEPOLIA \
  --rpc $SEPOLIA_RPC_URL
```

Updated `R_k` values are written to `data/monitor_state.json` and consumed by `LPManager.sync_from_chain_events`.
