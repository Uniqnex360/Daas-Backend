#!/usr/bin/env python3
"""
Script to create test users and validate API connections
"""

import asyncio
import os
import sys
from pathlib import Path
import dotenv
# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
dotenv.load_dotenv()

from app.services.auth_service import AuthService
from app.services.shopify_service import ShopifyService
from app.services.quickbooks_service import QuickBooksService
from app.services.data_ingestion_service import DataIngestionService
from app.database import get_db
from app.utils.logger import get_loggers
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_loggers("TestDataSetup")

class TestDataCreator:
    def __init__(self, db: AsyncSession):
        # Initialize AuthService with SQLAlchemy session
        self.db = db
        self.auth_service = AuthService(db)
        self.ingestion_service = DataIngestionService()
    
    async def create_test_user(self):
        """Create a test user with authentication token"""
        try:
            # Create test user data
            test_user_data = {
                "user_id": "test_user_001",
                "tenant_id": "test_tenant_001", 
                "email": "test@ecommerce-analytics.com",
                "scopes": ["read", "write", "admin"]
            }
            
            # Create access token directly (bypass user creation for testing)
            access_token = self.auth_service.create_access_token(data=test_user_data)
            
            print("✅ Test User Created Successfully!")
            print(f"📧 Email: {test_user_data['email']}")
            print(f"🔑 User ID: {test_user_data['user_id']}")
            print(f"🏢 Tenant ID: {test_user_data['tenant_id']}")
            print(f"🔐 Access Token: {access_token}")
            print(f"📋 Scopes: {test_user_data['scopes']}")
            
            return test_user_data, access_token
            
        except Exception as e:
            print(f"❌ Failed to create test user: {e}")
            return None, None
    
    async def test_shopify_connection(self, shopify_domain: str, access_token: str):
        """Test Shopify API connection"""
        try:
            print(f"\n🛍️ Testing Shopify Connection...")
            print(f"   Store: {shopify_domain}")
            print(f"   Token: {access_token[:20]}...")
            
            shopify_service = ShopifyService(
                access_token=access_token,
                shop_domain=shopify_domain
            )
            
            # Test with a simple API call
            async with shopify_service:
                orders = await shopify_service.fetch_orders()
                products = await shopify_service.fetch_products()
                
                print("✅ Shopify Connection Successful!")
                print(f"   📦 Orders found: {len(orders)}")
                print(f"   🏷️ Products found: {len(products)}")
                
                if orders:
                    print(f"   📋 Sample order: #{orders[0].get('name', 'N/A')}")
                if products:
                    print(f"   📋 Sample product: {products[0].get('title', 'N/A')}")
                
                return True
                
        except Exception as e:
            print(f"❌ Shopify Connection Failed: {e}")
            return False
    
    async def test_quickbooks_connection(self, client_id: str, client_secret: str, refresh_token: str, realm_id: str):
        """Test QuickBooks API connection"""
        try:
            print(f"\n📊 Testing QuickBooks Connection...")
            print(f"   Client ID: {client_id}")
            print(f"   Realm ID: {realm_id}")
            
            quickbooks_service = QuickBooksService(
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
                realm_id=realm_id
            )
            
            # Test with a simple API call
            async with quickbooks_service:
                # Test token refresh first
                access_token = await quickbooks_service._refresh_access_token()
                print(f"   🔑 Access Token: {access_token[:20]}...")
                
                # Test customers endpoint
                customers = await quickbooks_service.fetch_customers()
                invoices = await quickbooks_service.fetch_invoices()
                
                print("✅ QuickBooks Connection Successful!")
                print(f"   👥 Customers found: {len(customers)}")
                print(f"   🧾 Invoices found: {len(invoices)}")
                
                if customers:
                    print(f"   📋 Sample customer: {customers[0].get('DisplayName', 'N/A')}")
                if invoices:
                    print(f"   📋 Sample invoice: #{invoices[0].get('DocNumber', 'N/A')}")
                
                return True
                
        except Exception as e:
            print(f"❌ QuickBooks Connection Failed: {e}")
            return False
    
    async def test_data_ingestion(self, tenant_id: str, platform: str, integration_data: dict):
        """Test data ingestion for a platform"""
        try:
            print(f"\n📥 Testing {platform.upper()} Data Ingestion...")
            
            if platform == "shopify":
                result = await self.ingestion_service.ingest_shopify_data(tenant_id, integration_data)
            elif platform == "quickbooks":
                result = await self.ingestion_service.ingest_quickbooks_data(tenant_id, integration_data)
            else:
                print(f"❌ Unsupported platform: {platform}")
                return False
            
            if result.get('success'):
                print(f"✅ {platform.upper()} Data Ingestion Successful!")
                for key, value in result.items():
                    if key != 'success' and 'ingested' in key:
                        print(f"   {key.replace('_', ' ').title()}: {value}")
                return True
            else:
                print(f"❌ {platform.upper()} Data Ingestion Failed: {result.get('error')}")
                return False
                
        except Exception as e:
            print(f"❌ {platform.upper()} Data Ingestion Error: {e}")
            return False

async def main():
    """Main test function"""
    print("🚀 E-Commerce Analytics - API Connection Test")
    print("=" * 50)
    
    # Get database session
    db_gen = get_db()
    db = await db_gen.__anext__()
    
    try:
        creator = TestDataCreator(db)
        
        # 1. Create test user
        test_user, access_token = await creator.create_test_user()
        if not test_user:
            return
        
        # 2. Test Shopify connection (if credentials provided)
        shopify_domain = os.getenv("SHOPIFY_SHOP_DOMAIN")
        shopify_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
        
        if shopify_domain and shopify_token:
            shopify_success = await creator.test_shopify_connection(shopify_domain, shopify_token)
            
            if shopify_success:
                # Test data ingestion
                shopify_integration = {
                    "access_token": shopify_token,
                    "external_account_id": shopify_domain
                }
                await creator.test_data_ingestion(
                    test_user["tenant_id"], 
                    "shopify", 
                    shopify_integration
                )
        else:
            print("\n⚠️ Shopify credentials not found in environment")
            print("   Set SHOPIFY_SHOP_DOMAIN and SHOPIFY_ACCESS_TOKEN environment variables")
        
        # 3. Test QuickBooks connection (if credentials provided)
        qb_client_id = os.getenv("QUICKBOOKS_CLIENT_ID")
        qb_client_secret = os.getenv("QUICKBOOKS_CLIENT_SECRET") 
        qb_refresh_token = os.getenv("QUICKBOOKS_REFRESH_TOKEN")
        qb_realm_id = os.getenv("QUICKBOOKS_REALM_ID")
        
        if all([qb_client_id, qb_client_secret, qb_refresh_token, qb_realm_id]):
            qb_success = await creator.test_quickbooks_connection(
                qb_client_id, qb_client_secret, qb_refresh_token, qb_realm_id
            )
            
            if qb_success:
                # Test data ingestion
                qb_integration = {
                    "client_id": qb_client_id,
                    "client_secret": qb_client_secret,
                    "refresh_token": qb_refresh_token,
                    "realm_id": qb_realm_id
                }
                await creator.test_data_ingestion(
                    test_user["tenant_id"],
                    "quickbooks", 
                    qb_integration
                )
        else:
            print("\n⚠️ QuickBooks credentials not found in environment")
            print("   Set QUICKBOOKS_CLIENT_ID, QUICKBOOKS_CLIENT_SECRET, QUICKBOOKS_REFRESH_TOKEN, QUICKBOOKS_REALM_ID")
        
        print("\n" + "=" * 50)
        print("🎉 Test completed! Use this token for API requests:")
        print(f"Authorization: Bearer {access_token}")
        
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())