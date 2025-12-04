from typing import Dict, Any, List
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.config import settings
from app.services.shopify_service import ShopifyService
import asyncio
from app.services.amazon_service import AmazonService
from app.services.walmart_service import WalmartService
from app.services.quickbooks_service import QuickBooksService
from app.utils.logger import get_loggers
from app.utils.retry_decorators import http_retry
from datetime import timedelta
logger = get_loggers("DataIngestionService")


class DataIngestionService:
    def __init__(self):
        self.mongo_client = AsyncIOMotorClient(settings.MONGODB_URL)
        self.db = self.mongo_client[settings.MONGODB_DB]
        self.batch_size = settings.DATA_INGESTION_BATCH_SIZE or 1000

    async def ingest_shopify_data(self, tenant_id: str, integration_data: Dict) -> Dict[str, Any]:
        shopify_service = None
        try:
            shopify_service = ShopifyService(
                access_token=integration_data['access_token'], shop_domain=integration_data['external_account_id'])
            logger.info(
                f"Starting shopify data ingestion for tenant{tenant_id}")
            orders = await self._fetch_with_retry(shopify_service.fetch_orders, 'orders')
            await asyncio.sleep(1)
            products = await self._fetch_with_retry(shopify_service.fetch_products, 'products')
            await asyncio.sleep(1)
            customers = await self._fetch_with_retry(shopify_service.fetch_customers, 'customers')
            await asyncio.sleep(1)
            inventory = await self._fetch_with_retry(shopify_service.fetch_inventory, 'inventory')
            results = await asyncio.gather(
                self._store_raw_data_batched(
                    tenant_id, 'shopify', 'orders', orders),
                self._store_raw_data_batched(
                    tenant_id, 'shopify', 'products', products),
                self._store_raw_data_batched(
                    tenant_id, 'shopify', 'customers', customers),
                self._store_raw_data_batched(
                    tenant_id, 'shopify', 'inventory', inventory),
                return_exceptions=True
            )
            storage_errors = [r for r in results if isinstance(r, Exception)]
            if storage_errors:
                logger.error(f"Storage errors :{storage_errors}")
                raise storage_errors[0]
            logger.info(
                f"Successfully  ingested Shopify data  for tenant{tenant_id}")
            return {
                'success': True,
                'orders_ingested': len(orders),
                'products_ingested': len(products),
                'customers_ingested': len(customers),
                'inventory_ingested': len(inventory)
            }
        except Exception as e:
            logger.error(
                f"Shopify data ingestion failed for tenant{tenant_id}:{e}")
            return {'success': False, "error": str(e)}
        finally:
            if shopify_service:
                await self._safe_close_service(shopify_service)

    async def ingest_amazon_data(self, tenant_id: str, integration_data: Dict) -> Dict[str, Any]:
        amazon_service = None
        try:
            amazon_service = AmazonService(
                access_key=integration_data['access_token'],
                secret_key=integration_data.get('secret_key', ""),
                seller_id=integration_data['external_account_id']
            )
            logger.info(
                f"Starting amazon data ingestion for tenant{tenant_id}")
            orders = await self._fetch_with_retry(amazon_service.fetch_orders, 'orders')
            await asyncio.sleep(1)
            inventory = await self._fetch_with_retry(amazon_service.fetch_inventory, 'inventory')
            await asyncio.gather(self._store_raw_data_batched(tenant_id, 'amazon', 'orders', orders),
                                 self._store_raw_data_batched(tenant_id, 'amazon', 'inventory', inventory))
            logger.info(
                f"Successfully ingested Amazon data for tenant{tenant_id}")
            return {
                'success': True,
                'orders_ingested': len(orders),
                'inventory_ingested': len(inventory)
            }
        except Exception as e:
            logger.error(
                f"Amazon data ingested failed for tenant {tenant_id}:{e}")
            return {'success': False, 'error': str(e)}
        finally:
            if amazon_service:
                await self._safe_close_service(amazon_service)

    @http_retry(max_attempts=3, min_wait=4, max_wait=10)
    async def _fetch_with_retry(self, fetch_method, data_type: str):
        try:
            return await fetch_method()
        except Exception as e:
            logger.warning(f"Retrying error fetching {data_type}:{e}")
            raise

    async def _store_raw_data_batched(self, tenant_id: str, platform: str, data_type: str, data: List[Dict]):
        if not data:
            logger.info(f"No {data_type} to store for {platform}")
            return
        collection = self.db[f'raw_{platform}']
        for i in range(0, len(data), self.batch_size):
            batch = data[i:i+self.batch_size]
            documents = []
            for item in batch:
                document = {
                    'tenant_id': tenant_id,
                    'platform': platform,
                    'data_type': data_type,
                    'payload': item,
                    'fetched_at': datetime.utcnow(),
                    'processed': False
                }
                documents.append(document)
            try:
                await collection.insert_many(documents, ordered=False)
                logger.debug(
                    f"Stored batch of {len(documents)} {data_type} records for {platform}")
            except Exception as e:
                logger.error(f"Failed to store batch of {data_type}:{e}")
                continue

    async def ingest_walmart_data(self, tenant_id: str, integration_date: Dict) -> Dict[str, Any]:
        walmart_service = None
        try:
            walmart_service = WalmartService(
                client_id=integration_date['client_id'],
                client_secret=integration_date['client_secret'],
                consumer_id=integration_date.get('consumer_id', '')
            )
            orders = await walmart_service.fetch_orders()
            inventory = await walmart_service.fetch_inventory()
            items = await walmart_service.fetch_items(limit=50)
            analytics = await walmart_service.fetch_analytics()
            end_date = datetime.utcnow().strftime("%Y-%m-%d")
            start_date = (datetime.utcnow() - timedelta(days=30)
                          ).strftime("%Y-%m-%d")
            analytics = await walmart_service.fetch_analytics(
                report_type="ITEM_PERFORMANCE",
                start_date=start_date,
                end_date=end_date
            )
            await asyncio.gather(
                self._store_raw_data_batched(
                    tenant_id, 'walmart', 'orders', orders),
                self._store_raw_data_batched(
                    tenant_id, 'walmart', 'inventory', inventory),
                self._store_raw_data_batched(
                    tenant_id, 'walmart', "items", items),
                self._store_raw_data_batched(
                    tenant_id, 'walmart', 'analytics', analytics)
            )
            logger.info(
                f"Successfully ingested Walmart data for tenant {tenant_id}")
            return {
                'success': True,
                'orders_ingested': len(orders),
                'inventory_ingested': len(inventory),
                'items_ingested': len(items),
                'analytics_ingested': len(analytics)
            }
        except Exception as e:
            logger.error(f"Walmart data ingestion failed: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if walmart_service:
                await self._safe_close_service(walmart_service)

    async def ingest_quickbooks_data(self, tenant_id: str, integration_data: Dict) -> Dict[str, Any]:
        quickbooks_service=None
        try:
            end_date = datetime.utcnow().strftime("%Y-%m-%d")
            start_date = (datetime.utcnow()-timedelta(days=90)).strftime("%Y-%m-%d")
            quickbooks_service = QuickBooksService(
                client_id=integration_data['client_id'],
                client_secret=integration_data['client_secret'],
                refresh_token=integration_data['refresh_token'],
                realm_id=integration_data['realm_id']
            )
            invoices = await quickbooks_service.fetch_invoices(start_date, end_date)
            customers = await quickbooks_service.fetch_customers()
            payments = await quickbooks_service.fetch_payments(start_date, end_date)
            items = await quickbooks_service.fetch_items()
            balance_sheet = await quickbooks_service.fetch_balance_sheet(start_date, end_date)
            profit_and_loss = await quickbooks_service.fetch_profit_and_loss(start_date, end_date)
            await self._store_raw_data_batched(tenant_id, 'quickbooks', 'invoices', invoices)
            await self._store_raw_data_batched(tenant_id, 'quickbooks', 'customers', customers)
            await self._store_raw_data_batched(tenant_id, 'quickbooks', 'payments', payments)
            await self._store_raw_data_batched(tenant_id, 'quickbooks', 'items', items)
            await self._store_raw_data_batched(tenant_id, 'quickbooks', 'balance_sheet', balance_sheet)
            await self._store_raw_data_batched(tenant_id, 'quickbooks', 'profit_and_loss', profit_and_loss)
            return {
                'success': True,
                'invoices_ingested': len(invoices),
                'customers_ingested': len(customers),
                'payments_ingested': len(payments),
                'items_ingested': len(items),
                "balance_sheet_ingested": 1,
                "profit_and_loss_ingested": 1 
            }
        except Exception as e:
            logger.error(f'Quickbooks data ingestion failed:{e}')
            raise
        finally:
            if quickbooks_service:
                await self._safe_close_service(quickbooks_service)

    async def _safe_close_service(self, service):
        try:
            if hasattr(service, 'close_client'):
                await service.close_client()
            elif hasattr(service, 'close'):
                await service.close()
            elif hasattr(service, '__aexit__'):
                await service.__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"Error closing service :{e}")

    async def close(self):
        await self.mongo_client.close()


class DataIngestionContext:
    def __init__(self):
        self.service = DataIngestionService()

    async def __aenter__(self):
        return self.service

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.service.close()

