import httpx
from typing import List, Dict, Optional
import asyncio
import time
from datetime import datetime
from app.utils.logger import get_loggers
from aws_requests_auth.aws_auth import AWSRequestsAuth
from app.services.base_http_service import BaseHttpService
logger = get_loggers("AmazonService")


class AmazonService(BaseHttpService):
    def __init__(self, access_key: str, secret_key: str, seller_id: str, region: str = 'NA'):
        super().__init__("amazon", default_timeout=45.0)
        self.access_key = access_key
        self.secret_key = secret_key
        self.seller_id = seller_id
        self.region = region
        self.base_url = f"https://sellingpartnerapi-{region}.amazon.com"

    async def _make_amazon_request(self, method: str, endpoint: str, params: dict = None) -> Dict:
        headers = self._generate_signature(method, endpoint, params)
        response = await self._make_request(
            method,
            f"{self.base_url}{endpoint}",
            headers=headers,
            params=params
        )
        return response.json()

    def _generate_signature(self, method: str, endpoint: str, params: dict = None) -> Dict[str, str]:
        auth = AWSRequestsAuth(
            aws_access_key=self.access_key,
            aws_secret_access_key=self.secret_key,
            aws_host=f"sellingpartnerapi-{self.region}.amazon.com",
            aws_region=self.region,
            aws_service='execute-api'
        )
        full_url = f"{self.base_url}{endpoint}"
        auth_header = auth.get_auth_header(method, full_url)
        headers = {
            "Authorization": auth_header,
            "x-amz-date": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
            "Content-Type": "application/json"
        }
        return headers

    async def fetch_orders(self, created_after: str = None) -> List[Dict]:
        orders: List[Dict] = []
        next_token: Optional[str] = None
        page_count = 0
        while True:
            params = {}
            if created_after and next_token is None:
                params['CreatedAfter'] = created_after
            if next_token:
                params['NextToken'] = next_token
            try:
                data = await self._make_amazon_request("GET", '/orders/v0/orders', params)
                payload_orders = data.get('payload', {}).get('Orders', [])
                if payload_orders:
                    orders.extend(payload_orders)
                    page_count += 1
                    logger.debug(
                        f"Fetched {len(payload_orders)} orders on page {page_count}")
                next_token = data.get('payload', {}).get("NextToken")
                if not next_token:
                    break
            except Exception as e:
                logger.error(
                    f"Failed to fetch orders page {page_count + 1}: {e}")
                break
        logger.info(
            f"Fetched {len(orders)} total orders for seller {self.seller_id} across {page_count} pages")
        return orders

    async def fetch_inventory(self) -> List[Dict]:
        inventory: List[Dict] = []
        next_token: Optional[str] = None
        page_count = 0
        while True:
            params = {"NextToken": next_token} if next_token else {}
            try:
                data = await self._make_amazon_request("GET", '/fba/inventory/v1/summary', params)
                inventory_summary = data.get(
                    'payload', {}).get('inventorySummaries', [])
                if inventory_summary:
                    inventory.extend(inventory_summary)
                    page_count += 1
                    logger.debug(
                        f"Fetched {len(inventory_summary)} inventory items on page {page_count}")
                next_token = data.get('payload', {}).get('NextToken')
                if not next_token:
                    break
            except Exception as e:
                logger.error(
                    f"Failed to fetch inventory page {page_count + 1}: {e}")
                break
        logger.info(
            f"Fetched {len(inventory)} inventory items for seller {self.seller_id} across {page_count} pages")
        return inventory
