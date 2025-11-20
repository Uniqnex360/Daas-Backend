from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, Text, JSON, Numeric, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base


class UnifiedOrder(Base):
    __tablename__ = "unified_orders"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)
    platform = Column(String(50), nullable=False)
    external_order_id = Column(String(255), nullable=False)
    customer_external_id = Column(String(255))
    order_number = Column(String(255))
    order_date = Column(DateTime(timezone=True))
    financial_status = Column(String(50))
    fulfillment_status = Column(String(50))
    channel = Column(String(100))
    gross_sales = Column(Numeric(15, 2))
    net_sales = Column(Numeric(15, 2))
    total_tax = Column(Numeric(15, 2))
    discount_amount = Column(Numeric(15, 2))
    shipping_amount = Column(Numeric(15, 2))
    refund_amount = Column(Numeric(15, 2))
    total_fees = Column(Numeric(15, 2))
    net_payout = Column(Numeric(15, 2))
    currency = Column(String(3), default='USD')
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UnifiedOrderItem(Base):
    __tablename__ = "unified_order_items"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)
    order_id = Column(UUID(as_uuid=True), ForeignKey('unified_orders.id', ondelete='CASCADE'), nullable=False)
    platform = Column(String(50))
    external_line_id = Column(String(255))
    product_external_id = Column(String(255))
    sku = Column(String(255))
    quantity = Column(Numeric(10, 2))
    price = Column(Numeric(15, 2))
    total = Column(Numeric(15, 2))
    discount = Column(Numeric(15, 2))
    tax = Column(Numeric(15, 2))


class UnifiedProduct(Base):
    __tablename__ = "unified_products"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)
    platform = Column(String(50))
    external_product_id = Column(String(255))
    sku = Column(String(255))
    title = Column(Text)
    brand = Column(String(255))
    category = Column(String(255))
    price = Column(Numeric(15, 2))
    cost = Column(Numeric(15, 2))
    is_suppressed = Column(Boolean, default=False)
    buy_box_percent = Column(Numeric(5, 2))
    conversion_rate = Column(Numeric(5, 4))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UnifiedInventory(Base):
    __tablename__ = "unified_inventory"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)
    platform = Column(String(50))
    product_external_id = Column(String(255))
    sku = Column(String(255))
    location = Column(String(255))
    on_hand = Column(Numeric(15, 2))
    available = Column(Numeric(15, 2))
    reserved = Column(Numeric(15, 2))
    inbound = Column(Numeric(15, 2))
    updated_at = Column(DateTime(timezone=True), server_default=func.now())