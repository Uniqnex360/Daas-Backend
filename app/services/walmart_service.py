import base64
import time
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from asyncio import Lock
from app.utils.logger import get_loggers
from app.services.base_http_service import BaseHttpService
logger = get_loggers("WalmartService")


class WalmartService(BaseHttpService):
    def __init__(self, client_id: str, client_secret: str, consumer_id: str):
        super().__init__("walmart", default_timeout=30.0)
        if not client_id or not client_id.strip():
            raise ValueError("client_id cannot be empty")
        if not client_secret or not client_secret.strip():
            raise ValueError("client_secret cannot be empty")
        if not consumer_id or not consumer_id.strip():
            raise ValueError("consumer_id cannot be empty")
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.consumer_id = consumer_id.strip()
        self.base_url = "https://marketplace.walmartapis.com/v3"
        self.token_url = "https://marketplace.walmartapis.com/v3/token"
        self._access_token = None
        self._token_expiry = None
        self._token_lock = Lock()

    async def _get_access_token(self) -> str:
        if self._access_token and self._token_expiry and datetime.utcnow() < self._token_expiry:
            return self._access_token
        async with self._token_lock:
            if self._access_token and self._token_expiry and datetime.utcnow() < self._token_expiry:
                return self._access_token
            auth_string = f"{self.client_id}:{self.client_secret}"
            encoded_auth = base64.b64encode(auth_string.encode()).decode()
            headers = {
                "Authorization": f"Basic {encoded_auth}",
                "Content-Type": "application/x-www-form-urlencoded",
                "WM_SVC.NAME": "Walmart Marketplace",
                "WM_QOS.CORRELATION_ID": self._generate_correlation_id(),
                "Accept": "application/json"
            }
            data = {"grant_type": "client_credentials"}
            try:
                response = await self._make_request("POST", self.token_url, headers=headers, data=data)
                token_data = response.json()
                self._access_token = token_data["access_token"]
                self._token_expiry = datetime.utcnow(
                ) + timedelta(seconds=token_data["expires_in"] - 300)
                logger.info("Successfully refreshed Walmart access token")
                return self._access_token
            except Exception as e:
                logger.error(f"Failed to get Walmart access token: {e}")
                raise

    def _generate_correlation_id(self) -> str:
        return f"{int(time.time() * 1000)}"

    def _get_walmart_headers(self) -> Dict[str, str]:
        if not self._access_token:
            raise ValueError(
                "Access token not available. Call _get_access_token first")
        return {
            "WM_SVC.NAME": "Walmart Marketplace",
            "Accept": "application/json",
            "WM_QOS.CORRELATION_ID": self._generate_correlation_id(),
            "Content-Type": "application/json",
            "WM_SEC.ACCESS_TOKEN": self._access_token,
            "WM_CONSUMER.CHANNEL.TYPE": self.consumer_id,
        }

    async def _make_walmart_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        await self._get_access_token()
        headers = self._get_walmart_headers()
        if 'headers' in kwargs:
            headers = {**headers, **kwargs.pop('headers')}
        response = await self._make_request(
            method,
            f"{self.base_url}{endpoint}",
            headers=headers,
            **kwargs
        )
        return response.json()

    async def fetch_orders(self, createdStartDate: Optional[str] = None, limit: int = 200) -> List[Dict]:
        if limit <= 0 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        params = {
            "limit": str(limit),
            "productInfo": "true"
        }
        if createdStartDate:
            params["createdStartDate"] = createdStartDate
        data = await self._make_walmart_request("GET", "/orders", params=params)
        orders = data.get("list", {}).get("elements", {}).get("order", [])
        if isinstance(orders, dict):
            orders = [orders]
        logger.info(f"Fetched {len(orders)} orders from Walmart")
        return orders

    async def fetch_inventory(self, skus: Optional[List[str]] = None) -> List[Dict]:
        """Fetch inventory levels from Walmart"""
        endpoint = "/inventory"
        if skus:
            if not skus:
                raise ValueError("skus list cannot be empty")
            params = {"sku": ",".join(skus[:20])}
            data = await self._make_walmart_request("GET", endpoint, params=params)
        else:
            data = await self._make_walmart_request("GET", endpoint)
        inventory = data.get("elements", {}).get("inventory", [])
        logger.info(f"Fetched {len(inventory)} inventory items from Walmart")
        return inventory

    async def fetch_items(self, limit: int = 200, offset: int = 0) -> List[Dict]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if offset < 0:
            raise ValueError("offset cannot be negative")
        params = {
            "limit": str(limit),
            "offset": str(offset)
        }
        data = await self._make_walmart_request("GET", "/items", params=params)
        items = data.get("ItemResponse", [])
        logger.info(f"Fetched {len(items)} items from Walmart Catalog")
        return items

    async def fetch_analytics(self, report_type: str, start_date: str, end_date: str) -> List[Dict]:
        if not report_type or not report_type.strip():
            raise ValueError("report_type cannot be empty")
        if not start_date or not start_date.strip():
            raise ValueError("start_date cannot be empty")
        if not end_date or not end_date.strip():
            raise ValueError("end_date cannot be empty")
        params = {
            "type": report_type,
            "startDate": start_date,
            "endDate": end_date
        }
        data = await self._make_walmart_request("GET", "/reports", params=params)
        reports = data.get("reports", [])
        logger.info(
            f"Fetched {len(reports)} {report_type} reports from Walmart")
        return reports

    async def health_check(self) -> bool:
        try:
            await self._get_access_token()
            logger.info("Walmart API health check passed")
            return True
        except Exception as e:
            logger.error(f"Walmart API health check failed: {e}")
            return False
