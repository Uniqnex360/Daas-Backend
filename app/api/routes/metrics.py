from fastapi import APIRouter, Depends, Query, HTTPException
from datetime import datetime, date
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database import get_db
from app.api.dependencies import get_current_user_tenant
from app.models.core import User
from app.models.metrics import UnifiedMetricsDaily
from app.services.metrics_engine import MetricsEngine

router=APIRouter(prefix='/metrics',tags=['metrics'])
@router.get('/daily')
async def get_daily_metrics(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    platform: Optional[str] = Query(None, description="Filter by platform"),
    current_user: User = Depends(get_current_user_tenant),
    db: AsyncSession = Depends(get_db)
):
    query=select(UnifiedMetricsDaily).where(and_(
        UnifiedMetricsDaily.tenant_id==current_user.tenant_id,
        UnifiedMetricsDaily.date>=start_date,
        UnifiedMetricsDaily.date<=end_date
    ))
    if platform:
        query=query.where(UnifiedMetricsDaily.platform==platform)
    else:
        query = query.where(UnifiedMetricsDaily.platform.is_(None)) 
        
    result=await db.execute(query)
    metrics=result.scalars().all()
    return {
        "success":True,
        "data":{
            "period":{'start_date':start_date,'end_date':end_date},
            'metrics':[
                {
                    'date':metric.date.isoformat(),
                    'platform':metric.platform,
                    "total_orders":float(metric.total_orders),
                    'gross_sales':float(metric.gross_sales),
                    'net_sales':float(metric.net_sales),
                    'discounts':float(metric.discounts),
                    'taxes':float(metric.taxes),
                    'refunds':float(metric.refunds),
                    'units_sold':metric.units_sold,
                    'aov':float(metric.aov)
                }
                for metric in metrics
            ]
        },
        "message":'Daily metrics retrieved successfully!'
    }
    
@router.post('/calculate')
async def calculate_metrics(
    target_date: Optional[date] = Query(None, description="Date to calculate (default: yesterday)"),
    current_user: User = Depends(get_current_user_tenant),
    db: AsyncSession = Depends(get_db)
):
    if target_date is None:
        target_date=(datetime.now()-timedelta(days=1)).date()
    engine=MetricsEngine(db)
    metrics=await engine.calculate_metrics_daily(str(current_user.tenant_id),target_date)
    await engine.save_metrics(metrics)
    return {
        'success':True,
        'data':{
            "date":target_date.isoformat(),
            'metrics_calculated':True
        },
        'message':f"Metrics calculated for {target_date}"
    }
    
@router.post('/kpis')
async def get_key_metrics(current_user:User=Depends(get_current_user_tenant),db: AsyncSession=Depends(get_db)):
    end_date=datetime.now().date()
    start_date = end_date - timedelta(days=30)
    result=await db.execute(select(UnifiedMetricsDaily).where(and_(
        UnifiedMetricsDaily.tenant_id==current_user.tenant_id,
        UnifiedMetricsDaily.date>=start_date,
        UnifiedMetricsDaily.platform.is_(None)
    )))
    daily_metrics=result.scalars().all()
    total_gross_sales=sum(metric.total_sales or 0 for metric in daily_metrics)
    total_net_sales=sum(metric.net_sales or 0 for metric in daily_metrics)
    total_orders=sum(metric.total_orders or 0  for metric in daily_metrics)
    total_units=sum(metric.units_sold or 0 for metric in daily_metrics)
    aov=total_net_sales/total_orders if total_orders else 0
    return {
        'success':True,
        'data':{
            'period':{'start_date':start_date,'end_date':end_date},
            "kpis":{
                'gross_sales':float(total_gross_sales),
                'net_sales':float(total_net_sales),
                'total_orders':total_orders,
                'units_sold':total_units,
                'aov':float(aov),
                'refund_rate':0.025,
                'fulfillment_rate':0.95
            }
        },
        "message":"KPIs retrieved successfully"
    }
    
    
    