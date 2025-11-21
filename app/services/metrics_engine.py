import os
import argparse
import json
import logging
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.utils.logger import get_loggers
from app.database import AsyncSessionLocal 
from app.config import settings
from app.models.commerce import UnifiedOrder, UnifiedOrderItem
from app.models.metrics import UnifiedMetricsDaily
from app.database import engine

logger = get_loggers("MetricsEngine")



class MetricsEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def safe_number(self, x) -> float:
        if x is None:
            return 0.0
        if isinstance(x, (int, float, Decimal)):
            return float(x)
        s = str(x).strip()
        if s == '':
            return 0.0
        remove = ['$', '₹', '€', ',', 'USD', 'INR']
        for r in remove:
            s = s.replace(r, '')
        if s.startswith('(') and s.endswith(')'):
            s = '-'+s[1:-1]
        try:
            return float(Decimal(s))
        except Exception:
            digits = ''.join(ch for ch in s if (ch.isdigit() or ch in '.-'))
            try:
                return float(digits) if digits else 0.0
            except Exception:
                return 0.0

    async def calculate_metrics_daily(self, tenant_id: str, target_date: date) -> Dict[str, Any]:
        logger.info(
            f"Calculating metrics for tenant {tenant_id} on {target_date}")
        result = await self.db.execute(select(UnifiedOrder).where(and_(UnifiedOrder.tenant_id == tenant_id, UnifiedOrder.order_date >= target_date, UnifiedOrder.order_date < target_date+timedelta(days=1))))
        orders = result.scalars().all()
        metrics = await self.aggregate_orders(orders)
        platform_metrics = await self.calculate_platform_breakdown(tenant_id, target_date)
        product_metrics = await self.calculate_product_metrics(tenant_id, target_date)
        return {
            "date": target_date,
            'tenant_id': tenant_id,
            'overall': metrics,
            'platforms': platform_metrics,
            'products': product_metrics
        }

    async def aggregate_orders(self, orders: List[UnifiedOrder]) -> Dict[str, Any]:
        total_orders = len(orders)
        gross_sales = sum(order.gross_sales or 0 for order in orders)
        net_sales = sum(order.net_sales or 0 for order in orders)
        discounts = sum(order.discount_amount or 0 for order in orders)
        taxes = sum(order.total_tax or 0 for order in orders)
        refunds = sum(order.refund_amount or 0 for order in orders)
        units_sold = 0
        if orders:
            order_ids=[o.id for o in orders]
            item_result = await self.db.execute(select(UnifiedOrderItem).where(UnifiedOrderItem.order_id.in_(order_ids)))
            items = item_result.scalars().all()
            units_sold += sum(item.quantity or 0 for item in items)
        aov = (net_sales/total_orders) if total_orders else 0
        return {
            'total_orders': total_orders,
            'gross_sales': float(gross_sales),
            'net_sales': float(net_sales),
            'discounts': float(discounts),
            'taxes': float(taxes),
            'refunds': float(refunds),
            'units_sold': int(units_sold),
            'aov': float(aov)
        }

    async def calculate_platform_breakdown(self, tenant_id: str, target_date: date) -> Dict[str, Any]:
        result = await self.db.execute(
            select(UnifiedOrder.platform, UnifiedOrder).where(and_(
                UnifiedOrder.tenant_id == tenant_id,
                UnifiedOrder.order_date >= target_date,
                UnifiedOrder.order_date < target_date+timedelta(days=1)
            ))
        )
        orders = result.scalars().all()
        platforms = {}
        for order in orders:
            platform = order.platform
            if platform not in platforms:
                platforms[platform] = []
            platforms[platform].append(order)
        platform_metrics = {}
        for platform, platform_orders in platforms.items():
            platform_metrics[platform] = await self.aggregate_orders(platform_orders)
        return platform_metrics

    async def save_metrics(self, metrics_data: Dict[str, any]):
        tenant_id = metrics_data['tenant_id']
        target_date = metrics_data['date']
        overall_metrics = metrics_data['overall']
        metric_record = UnifiedMetricsDaily(tenant_id=tenant_id, date=target_date, platform=None,
                                            total_orders=overall_metrics['total_orders'], total_sales=overall_metrics['gross_sales'], net_sales=overall_metrics['net_sales'],discounts=overall_metrics['discounts'],taxes=overall_metrics['taxes'],refunds=overall_metrics['refunds'],units_sold=overall_metrics['units_sold'],aov=overall_metrics['aov'])
        self.db.add(metric_record)
        for platform,platform_data in metrics_data['platforms'].items():
            platform_metric=UnifiedMetricsDaily(
                tenant_id=tenant_id,
                date=target_date,
                platform=platform,
                total_orders=platform_data['total_orders'],
                total_sales=platform_data['gross_sales'],
                net_sales=platform_data['net_sales'],
                discounts=platform_data['discounts'],
                taxes=platform_data['taxes'],
                refunds=platform_data['refunds'],
                units_sold=platform_data['units_sold'],
                aov=platform_data['aov'],
                
            )
            self.db.add(platform_metric)
        await self.db.commit()
        logger.info(f"Metrics saved for {target_date}")
    
    async def backfill_metrics(self,tenant_id:str,start_date:date,end_date:date):
        current_date=start_date
        while(current_date<=end_date):
            try:
                metrics=await self.calculate_metrics_daily(tenant_id,current_date)
                await self.save_metrics(metrics)
                logger.info(f"Backfilled metrics for {current_date}")
            except Exception as e:
                logger.error(f'Error backfilling {current_date}:{e}')
            current_date+=timedelta(days=1)
            

async def main():
    parser=argparse.ArgumentParser(description='Calculate daily metrics')
    parser.add_argument('--date',type=str,help='Target date("YYYY-MM-DD")')
    parser.add_argument('--backfill', action='store_true')
    parser.add_argument('--start',type=str,help="Start date for backfill")
    parser.add_argument('--end',type=str,help='End date for backfill')
    parser.add_argument('--tenant',type=str,default=1,help='Tenant ID')
    args=parser.parse_args()
    async with AsyncSessionLocal() as db:
        engine_instance=MetricsEngine(db)
        if args.backfill:
            if not args.start or not args.end:
                logger.info("Backfill requires start and end date")
                return
            start_date=datetime.strptime(args.start,'%Y-%m-%d').date()
            end_date=datetime.strptime(args.end,'%Y-%m-%d').date()
            await engine_instance.backfill_metrics(args.tenant,start_date,end_date)
        else:
            if not args.date:
                target_date=(datetime.now()-timedelta(days=1)).date()
            else:
                target_date=datetime.strptime(args.date,'%Y-%m-%d').date()
            metrics=await engine_instance.calculate_metrics_daily(args.tenant,target_date)
            await engine_instance.save_metrics(metrics)
            logger.info(f"Metrics calculated  for {target_date}")
if __name__=='__main__':
    import asyncio
    asyncio.run(main())
            
        
