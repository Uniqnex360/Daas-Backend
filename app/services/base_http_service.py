import httpx
import asyncio
from typing import Optional, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.utils.retry_decorators import http_retry
from app.utils.logger import get_loggers
logger = get_loggers("BaseHttpService")

class BaseHttpService:
    def __init__(self, service_name: str, default_timeout: float = 30.0):
        self.service_name = service_name
        self.default_timeout = default_timeout
        self.client: Optional[httpx.AsyncClient] = None
        self._custom_headers: Dict[str, str] = {}

    async def init_client(self, **client_kwargs):
        if not self.client:
            kwargs = {
                "timeout": self.default_timeout,
                **client_kwargs
            }
            self.client = httpx.AsyncClient(**kwargs)
            logger.debug(f"Initialized HTTP client for {self.service_name}")

    async def close_client(self):
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.debug(f"Closed HTTP client for {self.service_name}")

    def set_custom_headers(self, headers: Dict[str, str]):
        self._custom_headers.update(headers)

    @http_retry(max_attempts=3, min_wait=4, max_wait=10)
    async def _make_request(self, method: str, url: str, **kwargs) -> httpx.Response:
        await self.init_client()
        headers = {**self._custom_headers, **kwargs.pop('headers', {})}
        try:
            logger.debug(
                f"Making {method} request to {url} for {self.service_name}")
            response = await self.client.request(method, url, headers=headers, **kwargs)
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                logger.warning(
                    f"Rate limited by {self.service_name}. Retrying after {retry_after}s")
                await asyncio.sleep(retry_after)
                raise httpx.HTTPStatusError(
                    "Rate limited", request=response.request, response=response)
            response.raise_for_status()
            logger.debug(f"Successfully completed {method} request to {url}")
            return response
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error for {self.service_name}: {e.response.status_code} - {e}")
            if e.response.status_code >= 500:
                raise
            raise
        except Exception as e:
            logger.error(f"Unexpected error for {self.service_name}: {e}")
            raise

    async def __aenter__(self):
        await self.init_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_client()
