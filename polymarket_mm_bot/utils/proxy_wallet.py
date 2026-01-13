"""
Proxy Wallet and Relayer for gas-efficient transactions on Polymarket.
Implements gasless transactions using a relayer service or proxy contracts.
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from eth_account import Account
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
import asyncio
import aiohttp


@dataclass
class TransactionData:
    """Structure for transaction data."""
    to: str
    value: int
    data: str
    gas_limit: Optional[int] = None
    gas_price: Optional[int] = None


class ProxyWallet:
    """
    A proxy wallet implementation for gas-efficient transactions.
    Can work with a relayer service or a deployed proxy contract.
    """
    
    def __init__(self, 
                 private_key: str, 
                 rpc_url: str, 
                 relayer_url: Optional[str] = None,
                 proxy_contract_address: Optional[str] = None):
        """
        Initialize the ProxyWallet.
        
        Args:
            private_key: Private key for the main wallet
            rpc_url: RPC endpoint URL
            relayer_url: Optional URL for a relayer service
            proxy_contract_address: Optional address of a deployed proxy contract
        """
        self.web3 = Web3(Web3.HTTPProvider(rpc_url))
        self.web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        self.account = Account.from_key(private_key)
        self.address = self.account.address
        self.relayer_url = relayer_url
        self.proxy_contract_address = proxy_contract_address
        self.logger = logging.getLogger(__name__)
        
    async def send_transaction_via_relayer(self, tx_data: TransactionData) -> Optional[str]:
        """
        Send a transaction via a relayer service.
        
        Args:
            tx_data: Transaction data to send
            
        Returns:
            Transaction hash if successful, None otherwise
        """
        if not self.relayer_url:
            self.logger.error("Relayer URL not configured")
            return None
            
        try:
            payload = {
                'from': self.address,
                'to': tx_data.to,
                'value': hex(tx_data.value),
                'data': tx_data.data,
                'gasLimit': hex(tx_data.gas_limit) if tx_data.gas_limit else None,
                'gasPrice': hex(tx_data.gas_price) if tx_data.gas_price else None
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.relayer_url, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        tx_hash = result.get('txHash')
                        self.logger.info(f"Transaction sent via relayer: {tx_hash}")
                        return tx_hash
                    else:
                        self.logger.error(f"Relayer error: {response.status}, {await response.text()}")
                        return None
                        
        except Exception as e:
            self.logger.error(f"Error sending transaction via relayer: {str(e)}")
            return None
    
    async def send_transaction_via_proxy(self, target_contract: str, calldata: str) -> Optional[str]:
        """
        Send a transaction via a proxy contract.
        
        Args:
            target_contract: Address of the target contract to call
            calldata: Encoded function call data
            
        Returns:
            Transaction hash if successful, None otherwise
        """
        if not self.proxy_contract_address:
            self.logger.error("Proxy contract address not configured")
            return None
            
        try:
            # Prepare the transaction to the proxy contract
            proxy_abi = [
                {
                    "inputs": [
                        {"name": "target", "type": "address"},
                        {"name": "calldata", "type": "bytes"}
                    ],
                    "name": "execute",
                    "outputs": [],
                    "stateMutability": "nonpayable",
                    "type": "function"
                }
            ]
            
            proxy_contract = self.web3.eth.contract(
                address=self.proxy_contract_address,
                abi=proxy_abi
            )
            
            # Encode the function call to execute on the target contract
            execute_data = proxy_contract.encodeABI(fn_name="execute", args=[target_contract, calldata])
            
            # Create transaction
            tx = {
                'from': self.address,
                'to': self.proxy_contract_address,
                'value': 0,
                'gas': 200000,  # Estimated gas
                'gasPrice': self.web3.eth.gas_price,
                'data': execute_data,
                'nonce': self.web3.eth.get_transaction_count(self.address),
            }
            
            # Sign and send transaction
            signed_tx = self.web3.eth.account.sign_transaction(tx, self.account.key)
            tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            tx_hash_str = tx_hash.hex()
            self.logger.info(f"Transaction sent via proxy: {tx_hash_str}")
            
            # Wait for transaction receipt
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status == 1:
                return tx_hash_str
            else:
                self.logger.error(f"Transaction failed: {tx_hash_str}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error sending transaction via proxy: {str(e)}")
            return None
    
    def estimate_gas_cost(self, tx_data: TransactionData) -> Optional[int]:
        """
        Estimate the gas cost for a transaction.
        
        Args:
            tx_data: Transaction data to estimate gas for
            
        Returns:
            Estimated gas cost in wei, or None if estimation fails
        """
        try:
            estimated_gas = self.web3.eth.estimate_gas({
                'from': self.address,
                'to': tx_data.to,
                'value': tx_data.value,
                'data': tx_data.data,
            })
            return estimated_gas
        except Exception as e:
            self.logger.error(f"Error estimating gas: {str(e)}")
            return None


class RelayerService:
    """
    Service class to manage relayer transactions for multiple wallets.
    """
    
    def __init__(self, relayer_url: str, rpc_url: str):
        """
        Initialize the RelayerService.
        
        Args:
            relayer_url: URL of the relayer service
            rpc_url: RPC endpoint URL
        """
        self.relayer_url = relayer_url
        self.rpc_url = rpc_url
        self.web3 = Web3(Web3.HTTPProvider(rpc_url))
        self.web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self.logger = logging.getLogger(__name__)
        
    async def batch_send_transactions(self, transactions: List[Dict[str, Any]]) -> List[Optional[str]]:
        """
        Send multiple transactions in a batch via the relayer.
        
        Args:
            transactions: List of transaction data dictionaries
            
        Returns:
            List of transaction hashes (None for failed transactions)
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.relayer_url}/batch", json={'transactions': transactions}) as response:
                    if response.status == 200:
                        result = await response.json()
                        tx_hashes = result.get('txHashes', [])
                        self.logger.info(f"Batch transaction sent: {len(tx_hashes)} transactions")
                        return tx_hashes
                    else:
                        self.logger.error(f"Batch relayer error: {response.status}, {await response.text()}")
                        return [None] * len(transactions)
                        
        except Exception as e:
            self.logger.error(f"Error sending batch transactions via relayer: {str(e)}")
            return [None] * len(transactions)