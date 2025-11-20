CREATE TABLE IF NOT EXISTS unified_metrics_daily (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    platform VARCHAR(50),
    
    total_orders INTEGER DEFAULT 0,
    total_sales NUMERIC(15,2) DEFAULT 0,
    net_sales NUMERIC(15,2) DEFAULT 0,
    discounts NUMERIC(15,2) DEFAULT 0,
    taxes NUMERIC(15,2) DEFAULT 0,
    refunds NUMERIC(15,2) DEFAULT 0,
    units_sold INTEGER DEFAULT 0,
    
    ad_spend NUMERIC(15,2) DEFAULT 0,
    inventory_value NUMERIC(15,2) DEFAULT 0,
    gross_profit NUMERIC(15,2) DEFAULT 0,
    net_profit NUMERIC(15,2) DEFAULT 0,
    
    aov NUMERIC(10,2) DEFAULT 0,
    fulfillment_rate NUMERIC(5,4) DEFAULT 0,
    refund_rate NUMERIC(5,4) DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(tenant_id, date, platform)
);

CREATE INDEX IF NOT EXISTS idx_metrics_daily_tenant_date ON unified_metrics_daily(tenant_id, date);
CREATE INDEX IF NOT EXISTS idx_metrics_daily_platform ON unified_metrics_daily(platform, date);

CREATE TABLE IF NOT EXISTS product_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    product_external_id VARCHAR(255),
    sku VARCHAR(255),
    date DATE NOT NULL,
    
    revenue NUMERIC(15,2) DEFAULT 0,
    units_sold INTEGER DEFAULT 0,
    conversion_rate NUMERIC(5,4) DEFAULT 0,
    buy_box_percent NUMERIC(5,4) DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(tenant_id, product_external_id, date)
);