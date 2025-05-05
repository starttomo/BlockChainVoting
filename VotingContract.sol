// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract Voting {
    mapping(address => bool) public hasVoted;
    mapping(string => uint256) public votesReceived;
    mapping(address => uint256) public tokenBalances;
    string[] public candidateList;
    address[] public voters; // 存储投票者地址
    address public owner;
    uint256 public votingEndTime;
    bool public votingClosed;

    event Voted(address indexed voter, string candidate, uint256 weight);
    event TokensDistributed(address indexed recipient, uint256 amount);
    event VotingClosed();
    event VotingReset(uint256 newDuration);

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can perform this action");
        _;
    }

    constructor(string[] memory candidateNames, uint256 durationInMinutes, address[] memory initialAccounts) {
        require(initialAccounts.length >= 10, "At least 10 accounts required");
        candidateList = candidateNames;
        owner = msg.sender;
        votingEndTime = block.timestamp + durationInMinutes * 1 minutes;
        votingClosed = false;

        // 给前10个账户各分配1000代币
        for (uint i = 0; i < 10; i++) {
            tokenBalances[initialAccounts[i]] = 1000;
            emit TokensDistributed(initialAccounts[i], 1000);
        }
    }

    function vote(string memory candidate, uint256 weight) public {
        require(!votingClosed, "Voting is closed");
        require(block.timestamp <= votingEndTime, "Voting period has ended");
        require(!hasVoted[msg.sender], "You have already voted");
        require(validCandidate(candidate), "Not a valid candidate");
        require(tokenBalances[msg.sender] >= weight, "Insufficient token balance");

        votesReceived[candidate] += weight;
        hasVoted[msg.sender] = true;
        tokenBalances[msg.sender] -= weight;
        voters.push(msg.sender);

        emit Voted(msg.sender, candidate, weight);
    }

    function distributeTokens(address recipient, uint256 amount) public onlyOwner {
        tokenBalances[recipient] += amount;
        emit TokensDistributed(recipient, amount);
    }

    function closeVoting() public onlyOwner {
        require(!votingClosed, "Voting is already closed");
        votingClosed = true;
        emit VotingClosed();
    }

    function resetVoting(uint256 durationInMinutes) public onlyOwner {
        for (uint i = 0; i < candidateList.length; i++) {
            votesReceived[candidateList[i]] = 0;
        }
        for (uint i = 0; i < voters.length; i++) {
            hasVoted[voters[i]] = false;
        }
        delete voters;

        votingClosed = false;
        votingEndTime = block.timestamp + durationInMinutes * 1 minutes;
        emit VotingReset(durationInMinutes);
    }

    function validCandidate(string memory candidate) private view returns (bool) {
        for (uint i = 0; i < candidateList.length; i++) {
            if (keccak256(bytes(candidateList[i])) == keccak256(bytes(candidate))) {
                return true;
            }
        }
        return false;
    }

    function getVotesForCandidate(string memory candidate) public view returns (uint256) {
        return votesReceived[candidate];
    }

    function getCandidateList() public view returns (string[] memory) {
        return candidateList;
    }

    function getTimeRemaining() public view returns (uint256) {
        if (block.timestamp >= votingEndTime) {
            return 0;
        }
        return votingEndTime - block.timestamp;
    }

    function getTokenBalance(address user) public view returns (uint256) {
        return tokenBalances[user];
    }

    function getTopCandidates() public view returns (string[] memory, uint256) {
        uint256 maxVotes = 0;
        uint256 topCount = 0;

        // 第一次遍历：找到最大票数
        for (uint i = 0; i < candidateList.length; i++) {
            if (votesReceived[candidateList[i]] > maxVotes) {
                maxVotes = votesReceived[candidateList[i]];
                topCount = 1;
            } else if (votesReceived[candidateList[i]] == maxVotes && maxVotes > 0) {
                topCount++;
            }
        }

        // 第二次遍历：收集所有得票最高的候选人
        string[] memory topCandidates = new string[](topCount);
        uint256 index = 0;
        for (uint i = 0; i < candidateList.length; i++) {
            if (votesReceived[candidateList[i]] == maxVotes && maxVotes > 0) {
                topCandidates[index] = candidateList[i];
                index++;
            }
        }

        return (topCandidates, maxVotes);
    }
}