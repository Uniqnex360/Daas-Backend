import httpx
from typing import List, Dict, Optional
import asyncio
import time
from datetime import datetime
from app.utils.logger import get_loggers
from aws_requests_auth.aws_auth import AWSRequestsAuth
logger = get_loggers("AmazonService")


class AmazonService:
    def __init__(self, access_key: str, secret_key: str, seller_id: str, region: str = 'NA'):
        self.access_key = access_key
        self.secret_key = secret_key
        self.seller_id = seller_id
        self.region = region
        self.base_url = f"https://sellingpartnerapi-{region}.amazon.com"
        self.client: Optional[httpx.AsyncClient] = None

    async def init_client(self):
        if not self.client:
            self.client = httpx.AsyncClient(timeout=30)

    async def close_client(self):
        if self.client:
            await self.client.aclose()
            self.client = None

    async def _request(self, method: str, endpoint: str, params: dict = None, retries: int = 3):
        await self.init_client()
        for attempt in range(retries):
            headers = self._generate_signature(method, endpoint, params)
            try:
                response = await self.client.request(method, f"{self.base_url}{endpoint}", headers=headers, params=params)
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 2))
                    logger.warning(
                        f"Rate limited.Retrying after {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if 500 <= e.response.status_code < 600:
                    logger.warning(
                        f"Server error {e.response.status_code},retrying...")
                    await asyncio.sleep(2 ** attempt)  
                    continue
                raise
        raise Exception(
            f"Failed to fetch from Amazon after {retries} retries.")

    def _generate_signature(self, method: str, endpoint: str, params: dict = None) -> Dict[str, str]:
        auth = AWSRequestsAuth(
            aws_access_key=self.access_key,
            aws_secret_access_key=self.secret_key,
            aws_host=f"sellingpartnerapi-{self.region}.amazon.com",
            aws_region=self.region,
            aws_service='execute-api'
        )
        headers = {
            "Authorization": auth.get_auth_header(method, f"{self.base_url}{endpoint}"),
            "x-amz-date": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
            "Content-Type": "application/json"
        }
        return headers

    async def fetch_orders(self, created_after: str = None) -> List[Dict]:
        orders: List[Dict] = []
        next_token: Optional[str] = None
        while True:
            params = {'CreatedAfter': created_after, "NextToken": next_token} if next_token else {
                "CreatedAfter": created_after}
            data = await self._request("GET", '/orders/v0/orders', params)
            payload_orders = data.get('payload', {}).get('Orders', [])
            orders.extend(payload_orders)
            next_token = data.get('payload', {}).get("NextToken")
            if not next_token:
                break
            logger.info(
                f"Fetched{len(orders)} orders for seller {self.seller_id}")
        return orders

    async def fetch_inventory(self) -> List[Dict]:
        inventory: List[Dict] = []
        next_token: Optional[str] = None
        while True:
            params = {"NextToken": next_token} if next_token else {}
            data = await self._request("GET", '/fba/inventory/v1/summary', params)
            inventory_summary = data.get(
                'payload', {}).get('inventorySummaries', [])
            inventory.extend(inventory_summary)
            next_token = data.get('payload', {}).get('NextToken')
            if not next_token:
                break
        logger.info(
            f"Fetched {len(inventory)} inventory items for seller {self.seller_id}")
        return inventory
