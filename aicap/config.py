"""Protocol constants aligned with aicap_exp/simulation.py."""

from typing import Any, Dict

CHAINS: Dict[str, Dict[str, Any]] = {
    "Chain_1": {"name": "Ethereum Sepolia", "confirm_delay_s": 12.0, "base_gas_multiplier": 3.0},
    "Chain_2": {"name": "BSC Testnet", "confirm_delay_s": 3.0, "base_gas_multiplier": 1.2},
    "Chain_3": {"name": "Base Sepolia", "confirm_delay_s": 1.0, "base_gas_multiplier": 0.6},
}

CHAIN_IDS = list(CHAINS.keys())

ALPHA_HEDGE = 1.25
LAMBDA_DECAY = 0.02
CREDIT_EPSILON = 1e-6
K_MIN_COLLATERAL = 5.0

LP_TYPE_RATIOS = {"Type-I": 0.70, "Type-II": 0.15, "Type-III": 0.15}

MACRO_ORDER_BTC = 10.0
GAMMA_GAS = 1.0
N_MAX_SPLITS = 6
BETA_EXEC = 1.2
T_BUFFER_S = 5.0
GAMMA_RISK_COLL = 0.15
P_PROCESSING_S = 0.5

NUM_LP_EDGES = 500
RNG_SEED = 42
LP_INVENTORY_BTC_MIN = MACRO_ORDER_BTC
LP_INVENTORY_BTC_MAX = MACRO_ORDER_BTC * 1.5
