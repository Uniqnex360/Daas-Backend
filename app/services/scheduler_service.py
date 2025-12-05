from typing import Optional, Dict, List
from apscheduler.schedulers.asyncio import AsyncIOScheduler,AsyncIOExecutor
from app.services.scheduler_service import __new__
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.triggers.cron import CronTrigger
from app.database import AsyncSessionLocal, get_mongodb
from sqlalchemy import select, update
from app.utils.logger import get_loggers
from app.models.core import Tenant, PlatformIntegration

logger = get_loggers("SchedulerService")

from app.config import settings
class SchedulerService:
    _instance:Optional['SchedulerService']=None
    _scheduler:Optional[AsyncIOScheduler]=None

    def __new__(cls):
        if cls._instance is None:
            cls._instance=super().__new__(cls)
        return cls._instance
    def __init__(self):
        if self._scheduler is None:
            jobstores={
                'default':RedisJobStore(
                    host=settings.REDIS_URL.split('://')[1].split(':')[0],
                    port=int(settings.REDIS_URL.split(':')[-1].split('/')[0]),
                    db=int(settings.REDIS_URL.split('/')[-1]) if '/' in settings.REDIS_URL else 0
                )
            }
            executors={
                'default':AsyncIOExecutor()
            }
            job_defaults={
                'colaesce':True,
                'max_instance':1,
                'misfire_grace_time':3600
            }
            self._scheduler=AsyncIOScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults,
                timezone='UTC'
            )
    @property
    def scheduler(self)->AsyncIOScheduler:
        return self._scheduler
    def start(self):
        if not self._scheduler.running:
            self._register_jobs()
            self._scheduler.start()
            logger.info('Scheduler started successfully!')
    def shutdown(self):
        if self._scheduler.running():
            self._scheduler.shutdown(wait=True)
            logger.info("Scheduler shutdown complete!")
    def _register_jobs(self):
        self._scheduler.add_job(sync_all_tenants_full,trigger=IntervalTrigger(hours=6),id='full_sync_all_tenants',name='Full Data Sync - All Tenants',replace_existing=True)
        self._scheduler.add_job(sync_all_tenant_orders,trigger=IntervalTrigger(hours=1),id='orders_sync_all_tenants',name='Orders Sync - All Tenants',replace_existing=True)
        self._scheduler.add_job(calculate_daily_metrics_all_tenants,trigger=CronTrigger(hours=2,minute=0),id='daily_metrics_calculation',name='Daily Metrics Calculation',replace_existing=True)
        self._scheduler.add_job(sync_all_tenants_inventory,trigger=IntervalTrigger(hours=4),id='inventory_sync_all_tenants',ame='Inventory Sync - All Tenants',replace_existing=True)
        self._scheduler.add_job(sync_all_tenants_quickbooks,trigger=CronTrigger(hour=3,minute=0),id='quickbooks_sync_all_tenants',name='QuickBooks Sync - All Tenants',replace_existing=True)
        logger.info('All scheduled jobs has been registered!')
    def add_tenant_sync_job(self,tenant_id:str,platform:str,schedule:str):
        job_id=f"sync_{tenant_id}_{platform}"
        self._scheduler.add_job(sync_single_tenant_platform,trigger=CronTrigger.from_crontab(schedule),id=job_id,name=f"Sync {platform} for {tenant_id}",kwargs={'tenant_id':tenant_id,'platform':platform },replace_existing=True)
        logger.info(f"Added custom sync job:{job_id}")
    def remove_job(self,job_id:str):
        try:
            self._scheduler.remove_job(job_id)
            logger.info(f"Removed job :{job_id}")
        except Exception as e:
            logger.error(f"Failed to remove job {job_id}:{e}")
    def get_job(self)->List[Dict]:
        jobs=[]
        for job in self._scheduler.get_job():
            jobs.append({
                'id':job.id,'name':job.name,'next_run':job.next_run_time.isoformat() if job.next_run_time else None ,'trigger':str(job.trigger)
            })
        return jobs
    async def sync_all_tenants_full():
        logger.info("Started full sync for all tenants")
        async with AsyncSessionLocal() as db:
            result=await db.execute(select(Tenant))
            tenants=result.scalars().all()
            for tenant in tenants:
                try:
                    await sync_tenant_all_platforms(str(tenant.id),db)
                except Exception as e:
                    logger.error(f"Full sync failed for {tenant.id}:{e}")
                    continue
        logger.info('Full async completed for all tenants')
        
    async  def sync_all_tenants_orders():
        logger.info("Starting orders sync for all tenants")
        async with AsyncSessionLocal() as db:
            result=await db.execute(select(Tenant))
            tenants=result.scalars().all()
            for tenant in tenants:
                try:
                    await sync_tenant_orders_only(str(tenant.id),db)
                except Exception as e:
                    logger.error(f"Orders sync failed for tenant {tenant.id}: {e}")
                    continue
        logger.info("Orders sync completed for all tenants")
    async def sync_all_tenants_inventory():
        logger.info("Starting inventory sync for all tenants")
        async with AsyncSessionLocal() as db:
            result=await db.execute(select(Tenant))
            tenants=result.scalars().all()
            for tenant in tenants:
                try:
                    await sync_tenant_inventory_only(str(tenant.id),db)
                except Exception as e:
                    logger.error(f"Inventory sync failed for tenant {tenant.id}:{e}")
                    
    async def sync_all_tenants_quickbooks():
        logger.info("Starting syncing of all quickbooks")
        async with AsyncSessionLocal() as db:
            result=await db.execute(select(PlatformIntegration).where(PlatformIntegration.platform=='quickbooks',PlatformIntegration.is_active==True))
            integrations=result.scalars().all()
            for intengration in integrations:
                try:
                    await sync_quickbooks_for_tenant(str(intengration.tenant_id),integration,db)
                except Exception as e:
                    logger.error(f"Quickbooks sync failed for tenant{integration.tenant_id}:{e}")
                    continue
        logger.info("Quickbooks sync completed for all tenants!")
    
    async def calculate_daily_metrics_all_tenants():
        logger.info(f"Starting daily calculation for all tenants")
        
            
        
        