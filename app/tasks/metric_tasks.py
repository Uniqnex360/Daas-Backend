from app.services.metrics_engine import MetricsEngine
from app.database import get_db
import asyncio
from datetime import datetime, timedelta, date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.logger import get_loggers
logger = get_loggers("metrics_engine")


async def calculate_daily_metrics_task(tenant_id: str, target_date: date = None):
    if target_date is None:
        target_date = (datetime.now()-timedelta(days=1)).date()
    async for db in get_db():
        try:
            engine = MetricsEngine(db)
            metrics = await engine.calculate_metrics_daily(tenant_id, target_date)
            await engine.save_metrics(metrics)
            logger.info(f"Daily metrics calculated for {target_date}")
            return True
        except Exception as e:
            logger.error(f"Error calculating metrics:{e}")
            return False

async def backfill_metrics_task(tenant_id: str, start_date: date, end_date: date):
    async for db in get_db():
        try:
            engine = MetricsEngine(db)
            await engine.backfill_metrics(tenant_id, start_date, end_date)
            logger.info(
                    f"Backfill completed from {start_date} to {end_date}")
            return True
        except Exception as e:
            logger.error(f"Error during backfill :{e}")
            return False

async def scheduled_daily_metrics():
    from app.models.core import Tenant
    async for db in get_db():
        try:
            result = await db.execute(select(Tenant))
            tenants = result.scalars().all()
            target_date = (datetime.utcnow()-timedelta(days=1)).date()
            for tenant in tenants:
                await calculate_daily_metrics_task(str(tenant.id), target_date)
        except Exception as e:
            logger.error(f"Scheduled metrics failed: {e}") 
