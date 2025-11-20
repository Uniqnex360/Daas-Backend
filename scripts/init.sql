CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    api_key VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'user' CHECK (role IN ('super_admin', 'tenant_admin', 'user', 'viewer')),
    tenant_id UUID REFERENCES tenants(id),
    is_active BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMP WITH TIME ZONE,
    email_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS platform_integrations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    platform VARCHAR(50) NOT NULL CHECK (platform IN ('shopify', 'amazon', 'walmart', 'quickbooks', 'netsuite')),
    connection_name VARCHAR(255),
    external_account_id VARCHAR(255),
    access_token TEXT,
    refresh_token TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS unified_orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    platform VARCHAR(50) NOT NULL,
    external_order_id VARCHAR(255) NOT NULL,
    customer_external_id VARCHAR(255),
    order_number VARCHAR(255),
    order_date TIMESTAMP WITH TIME ZONE,
    financial_status VARCHAR(50),
    fulfillment_status VARCHAR(50),
    channel VARCHAR(100),
    gross_sales NUMERIC(15,2),
    net_sales NUMERIC(15,2),
    total_tax NUMERIC(15,2),
    discount_amount NUMERIC(15,2),
    shipping_amount NUMERIC(15,2),
    refund_amount NUMERIC(15,2),
    total_fees NUMERIC(15,2),
    net_payout NUMERIC(15,2),
    currency VARCHAR(3) DEFAULT 'USD',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS unified_order_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    order_id UUID NOT NULL REFERENCES unified_orders(id) ON DELETE CASCADE,
    platform VARCHAR(50),
    external_line_id VARCHAR(255),
    product_external_id VARCHAR(255),
    sku VARCHAR(255),
    quantity NUMERIC(10,2),
    price NUMERIC(15,2),
    total NUMERIC(15,2),
    discount NUMERIC(15,2),
    tax NUMERIC(15,2)
);

CREATE TABLE IF NOT EXISTS unified_products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    platform VARCHAR(50),
    external_product_id VARCHAR(255),
    sku VARCHAR(255),
    title TEXT,
    brand VARCHAR(255),
    category VARCHAR(255),
    price NUMERIC(15,2),
    cost NUMERIC(15,2),
    is_suppressed BOOLEAN DEFAULT FALSE,
    buy_box_percent NUMERIC(5,2),
    conversion_rate NUMERIC(5,4),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS unified_inventory (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    platform VARCHAR(50),
    product_external_id VARCHAR(255),
    sku VARCHAR(255),
    location VARCHAR(255),
    on_hand NUMERIC(15,2),
    available NUMERIC(15,2),
    reserved NUMERIC(15,2),
    inbound NUMERIC(15,2),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_platform_integrations_tenant ON platform_integrations(tenant_id, platform);
CREATE INDEX IF NOT EXISTS idx_unified_orders_tenant_date ON unified_orders(tenant_id, order_date);
CREATE INDEX IF NOT EXISTS idx_unified_orders_platform ON unified_orders(platform, order_date);
CREATE INDEX IF NOT EXISTS idx_unified_products_tenant_sku ON unified_products(tenant_id, sku);
CREATE INDEX IF NOT EXISTS idx_unified_inventory_tenant_sku ON unified_inventory(tenant_id, sku);

INSERT INTO users (id, email, password_hash, first_name, last_name, role, email_verified) 
VALUES (
    '11111111-1111-1111-1111-111111111111',
    'admin@ecommerce.com',
    '$2b$12$LQv3c1yqBWVHxkd0L6kPPu/0a2J7lRcXqRZJZzX8QY8Wm1VcX6XZa', -
    'System',
    'Administrator',
    'super_admin',
    true
) ON CONFLICT (email) DO NOTHING;

INSERT INTO tenants (id, name, api_key) 
VALUES (
    '22222222-2222-2222-2222-222222222222',
    'Demo Store Inc.',
    'demo_tenant_abc123'
) ON CONFLICT (api_key) DO NOTHING;