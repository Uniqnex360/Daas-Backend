import httpx
import asyncio
from typing import List, Dict, Optional
from app.utils.logger import get_loggers
logger = get_loggers("ShopifyService")


class ShopifyService:
    def __init__(self, access_token: str, shop_domain: str):
        self.access_token = access_token
        self.shop_domain = shop_domain
        self.base_url = f"https://{shop_domain}/admin/api/2024-01"
        self.headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json"
        }
        self.timeout = 30

    async def _get(self, endpoint: str, params: dict = None) -> List[Dict]:
        all_items = []
        url = f"{self.base_url}/{endpoint}"
        params = params or {}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while True:
                try:
                    response = await client.get(url, headers=self.headers, params=params)
                    if response.status_code == 429:
                        retry_after = int(
                            response.headers.get("Retry-After", 2))
                        logger.warning(
                            f"Rate limit hit, retrying after {retry_after}s...")
                        await asyncio.sleep(retry_after)
                        continue
                    response.raise_for_status()
                    data = response.json()
                    items = data.get(endpoint.split(".")[0], [])
                    all_items.extend(items)
                    link = response.headers.get("Link")
                    if link and 'rel="next"' in link:
                        next_url = link.split("<")[1].split(">")[0]
                        url = next_url
                        params = {}
                    else:
                        break
                except httpx.HTTPError as e:
                    logger.error(f"HTTP error fetching {endpoint}: {e}")
                    raise
        return all_items

    async def fetch_orders(self, since_id: Optional[str] = None, created_at_min: Optional[str] = None) -> List[Dict]:
        params = {"status": "any", "limit": 250}
        if since_id:
            params["since_id"] = since_id
        if created_at_min:
            params["created_at_min"] = created_at_min
        return await self._get("orders.json", params)

    async def fetch_products(self) -> List[Dict]:
        return await self._get("products.json", {"limit": 250})

    async def fetch_customers(self) -> List[Dict]:
        return await self._get("customers.json", {"limit": 250})

    async def fetch_inventory(self) -> List[Dict]:
        return await self._get("inventory_levels.json", {"limit": 250})
