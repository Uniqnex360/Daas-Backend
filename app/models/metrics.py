from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, Text, JSON, Numeric, Boolean, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from sqlalchemy import UniqueConstraint
from app.database import Base


class UnifiedMetricsDaily(Base):
    __tablename__ = 'unified_metrics_daily'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey(
        'tenants.id', ondelete='CASCADE'), nullable=False)
    date = Column(Date, nullable=False)
    platform = Column(String(50), nullable=False)
    total_orders = Column(Integer, default=0)
    total_sales = Column(Numeric(15, 2), default=0)
    net_sales = Column(Numeric(15, 2), default=0)
    discounts = Column(Numeric(15, 2), default=0)
    taxes = Column(Numeric(15, 2), default=0)
    refunds = Column(Numeric(15, 2), default=0)
    units_sold = Column(Integer, default=0)
    ad_spend = Column(Numeric(15, 2), default=0)
    inventory_value = Column(Numeric(15, 2), default=0)
    gross_profit = Column(Numeric(15, 2), default=0)
    net_profit = Column(Numeric(15, 2), default=0)
    aov = Column(Numeric(10, 2), default=0)
    fulfillment_rate = Column(Numeric(5, 4), default=0)
    refund_rate = Column(Numeric(5, 4), default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint('tenant_id', 'date',
                      'platform', name='uq_metrics_daily'),)


class ProductMetrics(Base):
    __tablename__ = 'product_metrics'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey(
        'tenants.id', ondelete='CASCADE'), nullable=False)
    product_external_id = Column(String(255), nullable=False)
    sku = Column(String(255), nullable=False)
    date = Column(Date, nullable=False)
    revenue = Column(Numeric(15, 2), default=0)
    units_sold = Column(Integer, default=0)
    conversion_rate = Column(Numeric(5, 4), default=0)
    buy_box_percent = Column(Numeric(5, 4), default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True),
                        server_default=func.now(), onupdate=func.now())
