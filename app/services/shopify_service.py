import httpx
import asyncio
from typing import List, Dict, Optional
from app.utils.logger import get_loggers
from app.services.base_http_service import BaseHttpService
import aiohttp
import ssl
import socket
import certifi
logger = get_loggers("ShopifyService")


class ShopifyService(BaseHttpService):
    def __init__(self, access_token: str, shop_domain: str):
        super().__init__("shopify", default_timeout=30.0)
        self.access_token = access_token
        self.shop_domain = shop_domain
        clean_domain = shop_domain.replace('https://', '').replace('http://', '').replace('.myshopify.com', '')
        self.base_url = f"https://{clean_domain}.myshopify.com/admin/api/2023-10"
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        ssl_context.set_ciphers('DEFAULT@SECLEVEL=1')
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        self.connector = aiohttp.TCPConnector(
            ssl=ssl_context,
            family=socket.AF_INET
        )

        self.set_custom_headers({
            "X-Shopify-Access-Token": self.access_token,
            "Content-Type": "application/json"
        })

    async def _shopify_get(self, endpoint: str, params: Optional[Dict] = None) -> List[Dict]:
        try:
            response = await self._make_request("GET", f"{self.base_url}/{endpoint}", params=params)
            data = response.json()

            for key in data:
                if key != 'errors' and isinstance(data[key], list):
                    return data[key]

            return []

        except Exception as e:
            logger.error(f"Shopify API error for {endpoint}: {e}")
            return []

    async def fetch_orders(self, since_id: Optional[str] = None, created_at_min: Optional[str] = None) -> List[Dict]:
        params = {"status": "any", "limit": 250}
        if since_id:
            params["since_id"] = since_id
        if created_at_min:
            params["created_at_min"] = created_at_min

        orders = await self._shopify_get("orders.json", params)
        logger.info(f"Fetched {len(orders)} orders from Shopify")
        return orders

    async def fetch_products(self) -> List[Dict]:
        products = await self._shopify_get("products.json", {"limit": 250})
        logger.info(f"Fetched {len(products)} products from Shopify")
        return products

    async def fetch_customers(self) -> List[Dict]:
        customers = await self._shopify_get("customers.json", {"limit": 250})
        logger.info(f"Fetched {len(customers)} customers from Shopify")
        return customers

    async def fetch_inventory(self) -> List[Dict]:
        inventory = await self._shopify_get("inventory_levels.json", {"limit": 250})
        logger.info(f"Fetched {len(inventory)} inventory items from Shopify")
        return inventory
