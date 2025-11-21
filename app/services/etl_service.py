from typing import List, Dict, Any
from datetime import datetime
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.logger import get_loggers
from app.models.commerce import UnifiedOrder, UnifiedOrderItem, UnifiedProduct, UnifiedInventory
from app.services.data_ingestion_service import DataIngestionService
from sqlalchemy import select, and_ 
logger = get_loggers("ETLService")


class ETLService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.data_ingestion = DataIngestionService()
        self.batch_size = 100

    async def process_platform_data(self, tenant_id: str, platform: str) -> Dict[str, Any]:
        try:
            raw_data = await self.data_ingestion.get_unprocessed_data(platform, tenant_id)
            if not raw_data:
                logger.info(
                    f"No unprocessed data found for {platform} tenant{tenant_id}")
                return {'success': True, 'processed': 0}
            processed_count = 0
            processed_ids = []
            for i in range(0, len(raw_data), self.batch_size):
                batch = raw_data[i:i+self.batch_size]
                try:
                    batch_processed = await self._process_batch(tenant_id, platform, batch)
                    processed_count += batch_processed
                    processed_ids.extend(doc['_id'] for doc in batch)
                    logger.info(
                        f"Processed batch {i//self.batch_size+1} for {platform}")

                except Exception as e:
                    logger.error(f'Batch processing failed:{e}')
                    continue
            if processed_ids:
                await self.data_ingestion.mark_as_processed(platform, processed_ids)
                logger.info(
                    f"Marked {len(processed_ids)} documents as processed for {platform}")
            return {
                "success": True,
                'processed': processed_count,
                'total_available': len(raw_data)
            }
        except Exception as e:
            logger.error(
                f"ETL processing failed for {platform} tenant {tenant_id}:{e}")
            return {'success': False, 'error': str(e)}

    async def _process_batch(self, tenant_id: str, platform: str, batch: List[Dict]) -> int:
        processed_count = 0
        try:
            for doc in batch:
                success = await self._process_document(tenant_id, platform, doc)
                if success:
                    processed_count += 1
            await self.db.commit()
            return processed_count
        except Exception as e:
            await self.db.rollback()
            logger.error(f'Batch processing failed,rolled back:{e}')
            raise

    async def _process_document(self, tenant_id: str, platform: str, doc: Dict) -> bool:
        try:
            data_type = doc['data_type']
            payload = doc['payload']
            if data_type == 'orders':
                await self._process_orders(tenant_id, platform, payload)
            elif data_type == 'products':
                await self._process_products(tenant_id, platform, payload)
            elif data_type == 'inventory':
                await self._process_inventory(tenant_id, platform, payload)
            else:
                logger.warning(f"Unknown datatype:{data_type}")
                return False
            return True
        except Exception as e:
            logger.error(
                f"Failed to process {doc.get('data_type', 'unknown')} document:{e}")
            return False

    async def _process_orders(self, tenant_id: str, platform: str, orders_data: List[Dict]):
        unified_orders = []
        
        for order_data in orders_data:
            try:
                unified_order = await self._transform_order(tenant_id, platform, order_data)
                if unified_order:
                    unified_orders.append(unified_order)
            except Exception as e:
                logger.error(f"Failed to transform order: {e}")
                continue
        
        if unified_orders:
            external_ids = [order.external_order_id for order in unified_orders]
            existing_orders = await self.db.execute(
                select(UnifiedOrder.external_order_id).where(
                    and_(
                        UnifiedOrder.tenant_id == tenant_id,
                        UnifiedOrder.platform == platform,
                        UnifiedOrder.external_order_id.in_(external_ids)
                    )
                )
            )
            existing_ids = {row[0] for row in existing_orders}
            
            new_orders = [order for order in unified_orders if order.external_order_id not in existing_ids]
            
            if new_orders:
                self.db.add_all(new_orders)
                logger.info(f"Adding {len(new_orders)} new orders for {platform}")

    async def _transform_order(self, tenant_id: str, platform: str, order_data: Dict) -> UnifiedOrder:
        if platform == "shopify":
            return UnifiedOrder(
                tenant_id=tenant_id,
                platform=platform,
                external_order_id=str(order_data["id"]),
                order_number=order_data.get("order_number"),
                order_date=datetime.fromisoformat(order_data["created_at"].replace("Z", "+00:00")),
                financial_status=order_data.get("financial_status"),
                fulfillment_status=order_data.get("fulfillment_status"),
                gross_sales=float(order_data.get("total_line_items_price", 0)),
                net_sales=float(order_data.get("total_price", 0)),
                discount_amount=float(order_data.get("total_discounts", 0)),
                total_tax=float(order_data.get("total_tax", 0)),
                shipping_amount=float(order_data["shipping_lines"][0]["price"] if order_data.get("shipping_lines") else 0),
                currency=order_data.get("currency", "USD")
            )
        elif platform == "amazon":
            return UnifiedOrder(
                tenant_id=tenant_id,
                platform=platform,
                external_order_id=order_data.get("AmazonOrderId"),
                order_date=datetime.fromisoformat(order_data.get("PurchaseDate", "")),
                gross_sales=float(order_data.get("OrderTotal", {}).get("Amount", 0)),
                net_sales=float(order_data.get("OrderTotal", {}).get("Amount", 0)),
                currency=order_data.get("OrderTotal", {}).get("CurrencyCode", "USD")
            )