// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title LPManager
 * @notice On-chain arbitration pool for AICAP liquidity providers.
 *         Implements collateral bonding, capacity reservation, and slashing (Eq. 1, 13–14).
 * @dev Credit score R_k is emitted via events; off-chain RISK-OPTI reads updated R_k from LP monitor.
 */
contract LPManager {
    enum Outcome {
        Success,
        TimeoutRefund,
        SlashingArbitration
    }

    struct LPRecord {
        address lpAddress;
        uint256 collateral;       // bonded collateral (wei units / abstract)
        uint256 lockedCollateral; // Σ L_k,i reserved for active sub-paths
        bool active;
    }

    uint256 public immutable alphaHedge; // fixed-point 1e18 = 1.0; default 1.25e18
    address public arbitrator;

    mapping(bytes32 => LPRecord) public lps;
    mapping(bytes32 => mapping(bytes32 => uint256)) public subpathLocks; // lpId => subpathId => amount

    event LPRegistered(bytes32 indexed lpId, address indexed lpAddress, uint256 collateral);
    event CollateralReserved(bytes32 indexed lpId, bytes32 indexed subpathId, uint256 amount);
    event CollateralReleased(bytes32 indexed lpId, bytes32 indexed subpathId);
    event ExecutionRecorded(bytes32 indexed lpId, Outcome outcome, uint256 timestamp, uint8 sJ);
    event CollateralSlashed(bytes32 indexed lpId, bytes32 indexed subpathId, uint256 amount, address beneficiary);

    modifier onlyArbitrator() {
        require(msg.sender == arbitrator, "LPManager: not arbitrator");
        _;
    }

    constructor(uint256 _alphaHedge, address _arbitrator) {
        require(_alphaHedge > 0, "LPManager: invalid alpha");
        alphaHedge = _alphaHedge;
        arbitrator = _arbitrator;
    }

    /// @notice Eq. (1): C_max = (V_coll - locked) / alpha_hedge
    function getCMax(bytes32 lpId) public view returns (uint256) {
        LPRecord storage rec = lps[lpId];
        if (!rec.active) return 0;
        uint256 unreserved = rec.collateral > rec.lockedCollateral
            ? rec.collateral - rec.lockedCollateral
            : 0;
        return (unreserved * 1e18) / alphaHedge;
    }

    function registerLP(bytes32 lpId) external payable {
        require(!lps[lpId].active, "LPManager: already registered");
        require(msg.value > 0, "LPManager: zero collateral");
        lps[lpId] = LPRecord({
            lpAddress: msg.sender,
            collateral: msg.value,
            lockedCollateral: 0,
            active: true
        });
        emit LPRegistered(lpId, msg.sender, msg.value);
    }

    function addCollateral(bytes32 lpId) external payable {
        LPRecord storage rec = lps[lpId];
        require(rec.active && rec.lpAddress == msg.sender, "LPManager: not LP");
        rec.collateral += msg.value;
    }

    /// @notice Stage 2: reserve routing allocation against LP collateral
    function reserveCollateral(bytes32 lpId, bytes32 subpathId, uint256 amount) external onlyArbitrator returns (bool) {
        if (amount == 0 || amount > getCMax(lpId)) return false;
        LPRecord storage rec = lps[lpId];
        subpathLocks[lpId][subpathId] += amount;
        rec.lockedCollateral += amount;
        emit CollateralReserved(lpId, subpathId, amount);
        return true;
    }

    function releaseCollateral(bytes32 lpId, bytes32 subpathId) external onlyArbitrator {
        uint256 locked = subpathLocks[lpId][subpathId];
        if (locked == 0) return;
        delete subpathLocks[lpId][subpathId];
        lps[lpId].lockedCollateral -= locked;
        emit CollateralReleased(lpId, subpathId);
    }

    /// @notice Record execution outcome; sJ=1 success, sJ=0 slash (Eq. 13)
    function recordExecution(bytes32 lpId, Outcome outcome) external onlyArbitrator {
        uint8 sJ = outcome == Outcome.SlashingArbitration ? 0 : 1;
        emit ExecutionRecorded(lpId, outcome, block.timestamp, sJ);
    }

    /// @notice Stage 4: SPV arbitration transfers bonded collateral to user
    function slashCollateral(
        bytes32 lpId,
        bytes32 subpathId,
        uint256 amount,
        address beneficiary
    ) external onlyArbitrator returns (uint256) {
        LPRecord storage rec = lps[lpId];
        require(rec.active, "LPManager: unknown LP");
        uint256 slashAmt = amount > rec.collateral ? rec.collateral : amount;
        rec.collateral -= slashAmt;

        uint256 locked = subpathLocks[lpId][subpathId];
        if (locked > 0) {
            delete subpathLocks[lpId][subpathId];
            rec.lockedCollateral -= locked;
            emit CollateralReleased(lpId, subpathId);
        }

        emit ExecutionRecorded(lpId, Outcome.SlashingArbitration, block.timestamp, 0);
        emit CollateralSlashed(lpId, subpathId, slashAmt, beneficiary);

        if (slashAmt > 0 && beneficiary != address(0)) {
            (bool ok, ) = beneficiary.call{value: slashAmt}("");
            require(ok, "LPManager: slash transfer failed");
        }
        return slashAmt;
    }
}
