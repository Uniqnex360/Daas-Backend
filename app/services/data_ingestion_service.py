from typing import Dict,Any,List
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.config import settings
from app.services.shopify_service import ShopifyService
import asyncio
from app.services.amazon_service import AmazonService
from app.utils.logger import get_loggers
import httpx
logger = get_loggers("DataIngestionService")

class DataIngestionService:
    def __init__(self):
        self.mongo_client=AsyncIOMotorClient(settings.MONGODB_URL)
        self.db=self.mongo_client[settings.MONGODB_DB]
        self.batch_size=settings.DATA_INGESTION_BATCH_SIZE or 1000
    async def ingest_shopify_data(self,tenant_id:str,integration_data:Dict)->Dict[str,Any]:
        shopify_service=None
        try:
            shopify_service=ShopifyService(access_token=integration_data['access_token'],shop_domain=integration_data['external_account_id'])
            logger.info(f"Starting shopify data ingestion for tenant{tenant_id}")
            orders=await self._fetch_with_retry(shopify_service.fetch_orders,'orders')
            await asyncio.sleep(1)
            products=await self._fetch_with_retry(shopify_service.fetch_products,'products')
            await asyncio.sleep(1)
            customers=await self._fetch_with_retry(shopify_service.fetch_customers,'customers')
            await asyncio.sleep(1)
            inventory=await self._fetch_with_retry(shopify_service.fetch_inventory,'inventory')
            
            results=await asyncio.gather(
                self._store_raw_data_batched(tenant_id,'shopify','orders',orders),
                self._store_raw_data_batched(tenant_id,'shopify','products',products),
                self._store_raw_data_batched(tenant_id,'shopify','customers',customers),
                self._store_raw_data_batched(tenant_id,'shopify','inventory',inventory),
                return_exceptions=True
            )
            storage_errors=[r for r in results if isinstance(r,Exception)]
            if storage_errors:
                logger.error(f"Storage errors :{storage_errors}")
                raise storage_errors[0]
            logger.info(f"Successfully  ingested Shopify data  for tenant{tenant_id}")
            return {
                'success':True,
                'orders_ingested':len(orders),
                'products_ingested':len(products),
                'customers_ingested':len(customers),
                'inventory_ingested':len(inventory)
            }
            
            
        except Exception as e:
            logger.error(f"Shopify data ingestion failed for tenant{tenant_id}:{e}")
            return {'success':False,"error":str(e)}
        finally:
            if shopify_service:
                await self._safe_close_service(shopify_service)
                
    async def ingest_amazon_data(self,tenant_id:str,integration_data:Dict)->Dict[str,Any]:
        amazon_service=None
        try:
            amazon_service=AmazonService(
                access_key=integration_data['access_token'],
                secret_key=integration_data.get('secret_key',""),
                seller_id=integration_data['external_account_id']
                
            )
            logger.info(f"Starting amazon data ingestion for tenant{tenant_id}")
            orders=await self._fetch_with_retry(amazon_service.fetch_orders,'orders')
            await asyncio.sleep(1)
            inventory=await self._fetch_with_retry(amazon_service.fetch_inventory,'inventory'),
            await asyncio.gather(self._store_raw_data_batched(tenant_id,'amazon','orders',orders),
                                 self._store_raw_data_batched(tenant_id,'amazon','inventory',inventory))
            logger.info(f"Successfully ingested Amazon data for tenant{tenant_id}")
            return {
                'success':True,
                'orders_ingested':len(orders),
                'inventory_ingested':len(inventory)
            }
            
        except Exception as e:
            logger.error(f"Amazon data ingested failed for tenant {tenant_id}:{e}")
            return {'success':False,'error':str(e)}
        finally:
            if amazon_service:
                await self._safe_close_service(amazon_service)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1,min=4,max=10),
        retry=retry_if_exception_type((httpx.HTTPError, ConnectionError))) 
    async def _fetch_with_retry(self,fetch_method,data_type:str):
        try:
            return await fetch_method()
        except Exception as e:
            logger.warning(f"Retrying error fetching {data_type}:{e}")
            raise 
    async def _store_raw_data_batched(self,tenant_id:str,platform:str,data_type:str,data:List[Dict]):
        if not data:
            logger.info(f"No {data_type} to store for {platform}")
            return
        collection=self.db[f'raw_{platform}']
        for i in range(0,len(data),self.batch_size):
            batch=data[i:i+self.batch_size]
            documents=[]
            for item in batch:
                document={
                    'tenant_id':tenant_id,
                    'platform':platform,
                    'data_type':data_type,
                    'payload':item,
                    'fetched_at':datetime.utcnow(),
                    'processed':False
                }
                documents.append(document)
            try:
                await collection.insert_many(documents,ordered=False)
                logger.debug(f"Stored batch of {len(documents)} {data_type} records for {platform}")
            except Exception as e:
                logger.error(f"Failed to store batch of {data_type}:{e}")
                continue
    async def _safe_close_service(self,service):
        try:
            if hasattr(service,'close_client'):
                await service.close_client()
            elif hasattr(service,'close'):
                await service.close()
            elif hasattr(service,'__aexit__'):
                await service.__aexit__(None,None,None)
        except Exception as e:
            logger.warning(f"Error closing service :{e}")
    async def close(self):
        await self.mongo_client.close()
        
class DataIngestionContext:
    def __init__(self):
        self.service=DataIngestionService()
        
    async def __aenter__(self):
        return self.service
     
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.service.close()