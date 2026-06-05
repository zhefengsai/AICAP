// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./LPManager.sol";

/**
 * @title SwapExecutor
 * @notice Per-chain HTLC vault for AICAP four-stage atomic swaps.
 *         lock → reveal preimage → release | timeout refund.
 */
contract SwapExecutor {
    enum SwapStatus { None, Locked, Released, Refunded, Slashed }

    struct Swap {
        bytes32 lpId;
        address sender;
        address receiver;
        uint256 amount;
        bytes32 hashLock;
        uint256 timelock;
        SwapStatus status;
    }

    LPManager public immutable lpManager;
    uint256 public immutable timelockBlocks;
    address public arbitrator;

    mapping(bytes32 => Swap) public swaps;

    event SwapLocked(bytes32 indexed swapId, bytes32 indexed lpId, address sender, uint256 amount, bytes32 hashLock);
    event SwapReleased(bytes32 indexed swapId, bytes32 preimage);
    event SwapRefunded(bytes32 indexed swapId);

    modifier onlyArbitrator() {
        require(msg.sender == arbitrator, "SwapExecutor: not arbitrator");
        _;
    }

    constructor(address _lpManager, uint256 _timelockBlocks, address _arbitrator) {
        lpManager = LPManager(payable(_lpManager));
        timelockBlocks = _timelockBlocks;
        arbitrator = _arbitrator;
    }

    /// @notice Stage 2: lock assets with hashlock + timelock; reserve LP collateral
    function lockSwap(
        bytes32 swapId,
        bytes32 lpId,
        address receiver,
        bytes32 hashLock,
        uint256 collateralReserve
    ) external payable {
        require(swaps[swapId].status == SwapStatus.None, "SwapExecutor: exists");
        require(msg.value > 0, "SwapExecutor: zero amount");
        require(
            lpManager.reserveCollateral(lpId, swapId, collateralReserve),
            "SwapExecutor: collateral reserve failed"
        );

        swaps[swapId] = Swap({
            lpId: lpId,
            sender: msg.sender,
            receiver: receiver,
            amount: msg.value,
            hashLock: hashLock,
            timelock: block.number + timelockBlocks,
            status: SwapStatus.Locked
        });

        emit SwapLocked(swapId, lpId, msg.sender, msg.value, hashLock);
    }

    /// @notice Stage 3: reveal preimage and release to receiver
    function revealPreimage(bytes32 swapId, bytes32 preimage) external {
        Swap storage s = swaps[swapId];
        require(s.status == SwapStatus.Locked, "SwapExecutor: not locked");
        require(sha256(abi.encodePacked(preimage)) == s.hashLock, "SwapExecutor: bad preimage");

        s.status = SwapStatus.Released;
        lpManager.recordExecution(s.lpId, LPManager.Outcome.Success);
        lpManager.releaseCollateral(s.lpId, swapId);

        (bool ok, ) = s.receiver.call{value: s.amount}("");
        require(ok, "SwapExecutor: release failed");
        emit SwapReleased(swapId, preimage);
    }

    /// @notice Stage 4: refund sender after timelock expires
    function refund(bytes32 swapId) external {
        Swap storage s = swaps[swapId];
        require(s.status == SwapStatus.Locked, "SwapExecutor: not locked");
        require(block.number >= s.timelock, "SwapExecutor: timelock active");

        s.status = SwapStatus.Refunded;
        lpManager.recordExecution(s.lpId, LPManager.Outcome.TimeoutRefund);
        lpManager.releaseCollateral(s.lpId, swapId);

        (bool ok, ) = s.sender.call{value: s.amount}("");
        require(ok, "SwapExecutor: refund failed");
        emit SwapRefunded(swapId);
    }

    /// @notice Arbitration path: slash LP collateral to user on withhold
    function arbitrateSlash(bytes32 swapId, address beneficiary, uint256 slashAmount) external onlyArbitrator {
        Swap storage s = swaps[swapId];
        require(s.status == SwapStatus.Locked, "SwapExecutor: not locked");
        s.status = SwapStatus.Slashed;
        lpManager.slashCollateral(s.lpId, swapId, slashAmount, beneficiary);
    }
}
