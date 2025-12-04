import httpx
import base64
from typing import List, Any, Dict, Optional
from datetime import datetime, timedelta
from app.services.base_http_service import BaseHttpService
from app.utils.logger import get_loggers


class QuickBooksService(BaseHttpService):
    def __init__(self, client_id: str, client_secret: str, refresh_token: str, realm_id: str):
        super().__init__("quickbooks", default_timeout=60.0)
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.realm_id = realm_id
        self.base_url = f"https://quickbooks.api.intuit.com/v3/company/{realm_id}"
        self.token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
        self._access_token = None
        self.logger = get_loggers("QuickBooksService")
        self._token_expiry = None
        self.set_custom_headers({
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

    async def _refresh_access_token(self) -> str:
        if self._access_token and self._token_expiry and datetime.utcnow() < self._token_expiry:
            return self._access_token
        auth_string = f"{self.client_id}:{self.client_secret}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()
        headers = {
            "Authorization": f"Basic {encoded_auth}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        }
        try:
            response = await self._make_request("POST", self.token_url, headers=headers, data=data)
            token_data = response.json()
            self._access_token = token_data["access_token"]
            self._token_expiry = datetime.utcnow(
            ) + timedelta(seconds=token_data["expires_in"] - 300)
            self.set_custom_headers({
                **self._custom_headers,
                "Authorization": f"Bearer {self._access_token}"
            })
            return self._access_token
        except Exception as e:
            self.logger.error(
                f"Failed to refresh QuickBooks access token: {e}")
            raise

    async def _make_quickbooks_request(self, method: str, endpoint: str, **kwargs) -> Any:
        await self._refresh_access_token()
        response = await self._make_request(
            method,
            f"{self.base_url}{endpoint}",
            **kwargs
        )
        return response.json()

    async def _execute_query(self, query: str) -> List[Dict]:
        data = {
            "query": query,
            "minorversion": "65"
        }
        response = await self._make_quickbooks_request("POST", "/query", json=data)
        entities = response.get("QueryResponse", {})
        for key in entities:
            if key not in ["maxResults", "startPosition"]:
                return entities[key] or []
        return []

    async def fetch_invoices(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict]:
        try:
            query = "SELECT * FROM Invoice"
            if start_date and end_date:
                query += f" WHERE TxnDate >= '{start_date}' AND TxnDate <= '{end_date}'"
            elif start_date:
                query += f" WHERE TxnDate >= '{start_date}'"
            query += " ORDER BY TxnDate DESC MAXRESULTS 1000"
            invoices = await self._execute_query(query)
            self.logger.info(
                f"Fetched {len(invoices)} invoices from QuickBooks")
            return invoices
        except Exception as e:
            self.logger.error(f"Failed to fetch QuickBooks invoices: {e}")
            return []

    async def fetch_customers(self) -> List[Dict]:
        try:
            query = "SELECT * FROM Customer MAXRESULTS 1000"
            customers = await self._execute_query(query)
            self.logger.info(
                f"Fetched {len(customers)} customers from QuickBooks")
            return customers
        except Exception as e:
            self.logger.error(f"Failed to fetch QuickBooks customers: {e}")
            return []

    async def fetch_payments(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict]:
        try:
            query = "SELECT * FROM Payment"
            if start_date and end_date:
                query += f" WHERE TxnDate >= '{start_date}' AND TxnDate <= '{end_date}'"
            elif start_date:
                query += f" WHERE TxnDate >= '{start_date}'"
            query += " ORDER BY TxnDate DESC MAXRESULTS 1000"
            payments = await self._execute_query(query)
            self.logger.info(
                f"Fetched {len(payments)} payments from QuickBooks")
            return payments
        except Exception as e:
            self.logger.error(f"Failed to fetch QuickBooks payments: {e}")
            return []

    async def fetch_items(self) -> List[Dict]:
        try:
            query = "SELECT * FROM Item WHERE Active = true MAXRESULTS 1000"
            items = await self._execute_query(query)
            self.logger.info(f"Fetched {len(items)} items from QuickBooks")
            return items
        except Exception as e:
            self.logger.error(f"Failed to fetch QuickBooks items: {e}")
            return []

    async def fetch_profit_and_loss(self, start_date: str, end_date: str) -> Dict[str, Any]:
        try:
            params = {
                "start_date": start_date,
                "end_date": end_date,
                "minorversion": "65"
            }
            report = await self._make_quickbooks_request("GET", "/reports/ProfitAndLoss", params=params)
            self.logger.info("Fetched Profit & Loss report from QuickBooks")
            return report
        except Exception as e:
            self.logger.error(f"Failed to fetch QuickBooks P&L report: {e}")
            return {}

    async def fetch_balance_sheet(self, start_date: str, end_date: str) -> Dict[str, Any]:
        try:
            params = {
                "start_date": start_date,
                "end_date": end_date,
                "minorversion": "65"
            }
            report = await self._make_quickbooks_request("GET", "/reports/BalanceSheet", params=params)
            self.logger.info("Fetched Balance Sheet report from QuickBooks")
            return report
        except Exception as e:
            self.logger.error(f"Failed to fetch QuickBooks Balance Sheet: {e}")
            return {}
