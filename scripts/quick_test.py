#!/usr/bin/env python3
"""
Quick test to validate API connections without full setup
"""

import asyncio
import os
import sys
from pathlib import Path
import dotenv
dotenv.load_dotenv()
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

async def quick_connection_test():
    """Quick test for API connections"""
    print("🔍 Quick Connection Test")
    print("=" * 40)
    
    # Check environment variables
    print("📋 Checking environment variables...")
    
    shopify_vars = {
        "SHOPIFY_SHOP_DOMAIN": os.getenv("SHOPIFY_SHOP_DOMAIN"),
        "SHOPIFY_ACCESS_TOKEN": os.getenv("SHOPIFY_ACCESS_TOKEN")
    }
    
    quickbooks_vars = {
        "QUICKBOOKS_CLIENT_ID": os.getenv("QUICKBOOKS_CLIENT_ID"),
        "QUICKBOOKS_CLIENT_SECRET": os.getenv("QUICKBOOKS_CLIENT_SECRET"),
        "QUICKBOOKS_REFRESH_TOKEN": os.getenv("QUICKBOOKS_REFRESH_TOKEN"), 
        "QUICKBOOKS_REALM_ID": os.getenv("QUICKBOOKS_REALM_ID")
    }
    
    print("\n🛍️ Shopify Credentials:")
    for key, value in shopify_vars.items():
        status = "✅ Found" if value else "❌ Missing"
        display_value = value[:20] + "..." if value and len(value) > 20 else value
        print(f"   {key}: {status} - {display_value}")
    
    print("\n📊 QuickBooks Credentials:")
    for key, value in quickbooks_vars.items():
        status = "✅ Found" if value else "❌ Missing"
        display_value = value[:20] + "..." if value and len(value) > 20 else value
        print(f"   {key}: {status} - {display_value}")
    
    # Test basic imports
    print("\n🔧 Testing imports...")
    try:
        from app.services.shopify_service import ShopifyService
        from app.services.quickbooks_service import QuickBooksService
        print("✅ All imports successful")
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return
    
    # Quick Shopify test
    if shopify_vars["SHOPIFY_ACCESS_TOKEN"]:
        print("\n🛍️ Testing Shopify service initialization...")
        try:
            shopify = ShopifyService(
                access_token=shopify_vars["SHOPIFY_ACCESS_TOKEN"],
                shop_domain=shopify_vars["SHOPIFY_SHOP_DOMAIN"]
            )
            print("✅ Shopify service initialized successfully")
        except Exception as e:
            print(f"❌ Shopify service failed: {e}")
    
    # Quick QuickBooks test  
    if quickbooks_vars["QUICKBOOKS_CLIENT_ID"]:
        print("\n📊 Testing QuickBooks service initialization...")
        try:
            qb = QuickBooksService(
                client_id=quickbooks_vars["QUICKBOOKS_CLIENT_ID"],
                client_secret=quickbooks_vars["QUICKBOOKS_CLIENT_SECRET"],
                refresh_token=quickbooks_vars["QUICKBOOKS_REFRESH_TOKEN"],
                realm_id=quickbooks_vars["QUICKBOOKS_REALM_ID"]
            )
            print("✅ QuickBooks service initialized successfully")
        except Exception as e:
            print(f"❌ QuickBooks service failed: {e}")
    
    print("\n" + "=" * 40)
    print("🎯 Next steps:")
    print("1. Run: python scripts/create_test_data.py")
    print("2. Start server: python -m app.main") 
    print("3. Test API endpoints with the generated token")

if __name__ == "__main__":
    asyncio.run(quick_connection_test())