from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from uuid import UUID
from decimal import Decimal


class TenantCreate(BaseModel):
    name: str


class TenantResponse(BaseModel):
    id: UUID
    name: str
    # api_key: str
    created_at: datetime

    class Config:
        from_attributes = True


class PlatformIntegrationCreate(BaseModel):
    connection_name: str
    access_token: str
    external_account_id: str
    refresh_token: Optional[str] = None


class OrderResponse(BaseModel):
    id: UUID
    platform: str
    external_order_id: str
    order_number: Optional[str]
    order_date: Optional[datetime]
    financial_status: Optional[str]
    gross_sales: Optional[Decimal]
    net_sales: Optional[Decimal]
    currency: str
    class Config:
         from_attributes = True