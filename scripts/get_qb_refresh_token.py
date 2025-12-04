#!/usr/bin/env python3
"""
Quick script to get ONLY the refresh token since you have Realm ID
"""

import webbrowser
import requests
import base64
from urllib.parse import urlencode

def get_refresh_token_only(client_id: str, client_secret: str):
    """Get refresh token using OAuth flow"""
    
    # OAuth configuration
    redirect_uri = "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"
    auth_url = "https://appcenter.intuit.com/connect/oauth2"
    token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
    
    # Step 1: Generate authorization URL
    params = {
        'client_id': client_id,
        'response_type': 'code',
        'scope': 'com.intuit.quickbooks.accounting',
        'redirect_uri': redirect_uri,
        'state': 'test_state'
    }
    
    full_auth_url = f"{auth_url}?{urlencode(params)}"
    
    print("🚀 QuickBooks OAuth Setup")
    print("=" * 50)
    print(f"✅ Your Realm ID: 9341455727634233")
    print("\n📋 Follow these steps:")
    print("1. We'll open QuickBooks OAuth in your browser")
    print("2. Login with your Intuit credentials")
    print("3. Authorize the application")
    print("4. Copy the authorization code from the URL")
    print("5. Paste it here")
    
    input("\nPress Enter to open QuickBooks OAuth...")
    webbrowser.open(full_auth_url)
    
    print(f"\n🔗 Manual URL (if needed):")
    print(full_auth_url)
    
    # Get authorization code
    auth_code = input("\n📝 Paste the authorization code: ").strip()
    
    if not auth_code:
        print(" Authorization code required!")
        return None
    
    # Step 2: Exchange code for tokens
    print("\n🔄 Getting refresh token...")
    
    # Prepare request
    auth_string = f"{client_id}:{client_secret}"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    
    headers = {
        'Authorization': f'Basic {encoded_auth}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    data = {
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': redirect_uri
    }
    
    response = requests.post(token_url, headers=headers, data=data)
    
    if response.status_code == 200:
        tokens = response.json()
        refresh_token = tokens.get('refresh_token')
        
        print("✅ SUCCESS! Tokens received:")
        print(f"🔄 Refresh Token: {refresh_token}")
        print(f"🔑 Access Token: {tokens.get('access_token')[:50]}...")
        print(f"⏰ Expires In: {tokens.get('expires_in')} seconds")
        
        return refresh_token
    else:
        print(f" Failed to get tokens: {response.text}")
        return None

def main():
    client_id = input("Enter your QuickBooks Client ID: ").strip()
    client_secret = input("Enter your QuickBooks Client Secret: ").strip()
    
    if not client_id or not client_secret:
        print(" Client ID and Client Secret are required!")
        return
    
    refresh_token = get_refresh_token_only(client_id, client_secret)
    
    if refresh_token:
        print("\n" + "=" * 50)
        print("🎉 ADD TO YOUR .env FILE:")
        print(f"QUICKBOOKS_REFRESH_TOKEN={refresh_token}")
        print("QUICKBOOKS_REALM_ID=9341455727634233")
        print("\n✅ Your QuickBooks sandbox is ready!")

if __name__ == "__main__":
    main()