from web3 import Web3
from solcx import compile_source, install_solc
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# 安装Solidity编译器
install_solc('0.8.0')

# 连接到Ganache
ganache_url = "http://127.0.0.1:7545"
web3 = Web3(Web3.HTTPProvider(ganache_url))
if not web3.is_connected():
    raise Exception("无法连接到Ganache区块链")

# 全局变量
contract_address = None
contract_abi = None


def compile_contract():
    with open('VotingContract.sol', 'r') as file:
        contract_source_code = file.read()

    print("=== 编译合约 ===")
    compiled_sol = compile_source(
        contract_source_code,
        output_values=['abi', 'bin'],
        solc_version='0.8.0'
    )
    contract_id, contract_interface = compiled_sol.popitem()
    return contract_interface['bin'], contract_interface['abi']


def deploy_contract(candidate_names, duration_minutes):
    global contract_address, contract_abi
    bytecode, abi = compile_contract()
    contract_abi = abi

    web3.eth.default_account = web3.eth.accounts[0]
    Voting = web3.eth.contract(abi=abi, bytecode=bytecode)

    # 准备前10个账户
    initial_accounts = web3.eth.accounts[:10]
    print(f"正在部署合约，候选人: {candidate_names}, 持续时间: {duration_minutes}分钟, 初始账户: {initial_accounts}")
    tx_hash = Voting.constructor(candidate_names, duration_minutes, initial_accounts).transact({
        'gas': 3000000,  # 增加 Gas 以支持更多初始化
        'gasPrice': web3.to_wei('20', 'gwei')
    })

    tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    contract_address = tx_receipt.contractAddress
    print(f"合约部署成功！地址: {contract_address}")
    return contract_address


def get_contract_instance():
    if not contract_address or not contract_abi:
        raise Exception("合约未部署")
    return web3.eth.contract(address=contract_address, abi=contract_abi)


@app.route('/vote', methods=['POST'])
def vote():
    if not contract_address:
        return jsonify({'success': False, 'message': '合约未部署'})

    data = request.get_json()
    try:
        account_index = int(data.get('account_index'))
        candidate = str(data.get('candidate'))
        weight = int(data.get('weight', 1))
    except (TypeError, ValueError) as e:
        return jsonify({'success': False, 'message': f'参数类型错误: {str(e)}'})

    try:
        voting = get_contract_instance()
        account = web3.eth.accounts[account_index]

        token_balance = voting.functions.getTokenBalance(account).call()
        if token_balance < weight:
            return jsonify({'success': False, 'message': f'代币不足 (当前: {token_balance}, 需要: {weight})'})

        tx = voting.functions.vote(candidate, weight).build_transaction({
            'from': account,
            'nonce': web3.eth.get_transaction_count(account),
            'gas': 300000,
            'gasPrice': web3.to_wei('20', 'gwei')
        })

        tx_hash = web3.eth.send_transaction(tx)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status != 1:
            return jsonify({'success': False, 'message': '交易执行失败'})

        new_votes = voting.functions.getVotesForCandidate(candidate).call()
        new_balance = voting.functions.getTokenBalance(account).call()

        return jsonify({
            'success': True,
            'tx_hash': tx_hash.hex(),
            'block_number': receipt.blockNumber,
            'new_votes': new_votes,
            'new_balance': new_balance
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'投票失败: {str(e)}'})


@app.route('/setup', methods=['GET', 'POST'])
def setup():
    if request.method == 'POST':
        candidates = request.form.get('candidates', '').split(',')
        candidates = [c.strip() for c in candidates if c.strip()]
        duration = int(request.form.get('duration', 10))

        if len(candidates) < 2:
            return render_template('setup.html', error="至少需要2个候选人")

        try:
            deploy_contract(candidates, duration)
            return redirect(url_for('index'))
        except Exception as e:
            return render_template('setup.html', error=str(e))

    return render_template('setup.html')


@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not contract_address:
        return redirect(url_for('setup'))

    voting = get_contract_instance()
    owner = voting.functions.owner().call()
    if web3.eth.accounts[0].lower() != owner.lower():
        return render_template('error.html', error="只有合约所有者可以访问管理页面")

    error = None
    success = None

    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'distribute':
                recipient_index = int(request.form.get('recipient'))
                amount = int(request.form.get('amount'))
                recipient = web3.eth.accounts[recipient_index]

                tx = voting.functions.distributeTokens(recipient, amount).build_transaction({
                    'from': web3.eth.accounts[0],
                    'nonce': web3.eth.get_transaction_count(web3.eth.accounts[0]),
                    'gas': 200000,
                    'gasPrice': web3.to_wei('20', 'gwei')
                })
                tx_hash = web3.eth.send_transaction(tx)
                receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
                if receipt.status == 1:
                    success = "代币分配成功"
                else:
                    error = "代币分配失败"

            elif action == 'close':
                tx = voting.functions.closeVoting().build_transaction({
                    'from': web3.eth.accounts[0],
                    'nonce': web3.eth.get_transaction_count(web3.eth.accounts[0]),
                    'gas': 200000,
                    'gasPrice': web3.to_wei('20', 'gwei')
                })
                tx_hash = web3.eth.send_transaction(tx)
                receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
                if receipt.status == 1:
                    success = "投票已结束"
                else:
                    error = "结束投票失败"

            elif action == 'reset':
                duration = int(request.form.get('reset_duration', 10))
                tx = voting.functions.resetVoting(duration).build_transaction({
                    'from': web3.eth.accounts[0],
                    'nonce': web3.eth.get_transaction_count(web3.eth.accounts[0]),
                    'gas': 300000,
                    'gasPrice': web3.to_wei('20', 'gwei')
                })
                tx_hash = web3.eth.send_transaction(tx)
                receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
                if receipt.status == 1:
                    success = "投票已重置"
                else:
                    error = "重置投票失败"

        except Exception as e:
            error = f"操作失败: {str(e)}"

    accounts = []
    for i, address in enumerate(web3.eth.accounts):
        token_balance = voting.functions.getTokenBalance(address).call()
        voted = voting.functions.hasVoted(address).call()
        accounts.append({
            'index': i,
            'address': address,
            'tokens': token_balance,
            'voted': voted
        })

    voting_closed = voting.functions.votingClosed().call()
    time_remaining = voting.functions.getTimeRemaining().call()

    return render_template('admin.html',
                           accounts=accounts,
                           voting_closed=voting_closed,
                           time_remaining=time_remaining,
                           error=error,
                           success=success)


@app.route('/')
def index():
    if not contract_address:
        return redirect(url_for('setup'))

    voting = get_contract_instance()
    candidates = voting.functions.getCandidateList().call()
    votes = {candidate: voting.functions.getVotesForCandidate(candidate).call() for candidate in candidates}
    voting_closed = voting.functions.votingClosed().call()
    time_remaining = voting.functions.getTimeRemaining().call()
    current_block = web3.eth.block_number

    # 获取最高得票者
    top_candidates, max_votes = voting.functions.getTopCandidates().call()

    accounts = []
    for i, address in enumerate(web3.eth.accounts):
        token_balance = voting.functions.getTokenBalance(address).call()
        voted = voting.functions.hasVoted(address).call()
        balance = web3.eth.get_balance(address) / 10**18
        accounts.append({
            'index': i,
            'address': address,
            'balance': balance,
            'tokens': token_balance,
            'voted': voted
        })

    return render_template('index.html',
                           contract_address=contract_address,
                           candidates=candidates,
                           votes=votes,
                           voting_closed=voting_closed,
                           time_remaining=time_remaining,
                           current_block=current_block,
                           accounts=accounts,
                           top_candidates=top_candidates,
                           max_votes=max_votes)


if __name__ == '__main__':
    app.run(debug=True, port=5001)