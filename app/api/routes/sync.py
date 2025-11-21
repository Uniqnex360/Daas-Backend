from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.dependencies import get_current_user_tenant
from app.models.core import User
from app.services.data_ingestion_service import DataIngestionService
from app.services.etl_service import ETLService

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/{platform}")
async def sync_platform_data(
    platform: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user_tenant),
    db: AsyncSession = Depends(get_db)
):
    from app.models.core import PlatformIntegration
    result = await db.execute(
        select(PlatformIntegration).where(
            PlatformIntegration.tenant_id == current_user.tenant_id,
            PlatformIntegration.platform == platform,
            PlatformIntegration.is_active == True
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(404, f"No active {platform} integration found")

    background_tasks.add_task(
        run_platform_sync,
        str(current_user.tenant_id),
        platform,
        {
            "access_token": integration.access_token,
            "external_account_id": integration.external_account_id
        }
    )

    return {
        "success": True,
        "message": f"{platform} sync started in background",
        "platform": platform
    }


async def run_platform_sync(tenant_id: str, platform: str, integration_data: Dict):
    ingestion_service = DataIngestionService()
    etl_service = ETLService()

    try:

        if platform == "shopify":
            result = await ingestion_service.ingest_shopify_data(tenant_id, integration_data)
        elif platform == "amazon":
            result = await ingestion_service.ingest_amazon_data(tenant_id, integration_data)
        else:
            return

        if result["success"]:
            await etl_service.process_platform_data(tenant_id, platform)

    except Exception as e:
        print(f"Sync failed for {platform}: {e}")
