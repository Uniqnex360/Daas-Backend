from __future__ import annotations
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis, ConnectionPool
from app.config import settings
from app.utils.logger import get_loggers
logger = get_loggers("Database")


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ECHO_SQL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=settings.DB_POOL_RECYCLE,
)
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")


class MongoDBClient:
    client: Optional[AsyncIOMotorClient] = None
    db = None

    @classmethod
    def get_client(cls) -> AsyncIOMotorClient:
        if cls.client is None:
            cls.client = AsyncIOMotorClient(
                settings.MONGODB_URL,
                maxPoolSize=settings.MONGODB_MAX_POOL_SIZE,
                minPoolSize=settings.MONGODB_MIN_POOL_SIZE,
                serverSelectionTimeoutMS=5000,
            )
            cls.db = cls.client[settings.MONGODB_DB]
            logger.info("MongoDB client initialized")
        return cls.client

    @classmethod
    def get_database(cls):
        if cls.db is None:
            cls.get_client()
        return cls.db

    @classmethod
    async def close(cls):
        if cls.client:
            cls.client.close()
            cls.client = None
            cls.db = None
            logger.info("MongoDB client closed")


async def get_mongodb():
    return MongoDBClient.get_database()


class RedisClient:
    pool: Optional[ConnectionPool] = None
    client: Optional[Redis] = None

    @classmethod
    def get_pool(cls) -> ConnectionPool:
        if cls.pool is None:
            cls.pool = ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                decode_responses=True,
                encoding="utf-8",
            )
            logger.info("Redis connection pool initialized")
        return cls.pool

    @classmethod
    def get_client(cls) -> Redis:
        if cls.client is None:
            pool = cls.get_pool()
            cls.client = Redis(connection_pool=pool)
            logger.info("Redis client initialized")
        return cls.client

    @classmethod
    async def close(cls):
        if cls.client:
            await cls.client.aclose()
            cls.client = None
        if cls.pool:
            await cls.pool.aclose()
            cls.pool = None
            logger.info("Redis connection closed")


async def get_redis() -> Redis:
    return RedisClient.get_client()


async def get_redis_session() -> AsyncGenerator[Redis, None]:
    redis = Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        encoding="utf-8",
    )
    try:
        yield redis
    finally:
        await redis.aclose()


async def check_postgres_health() -> bool:
    try:
        async with engine.begin() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {e}")
        return False


async def check_mongodb_health() -> bool:
    try:
        client = MongoDBClient.get_client()
        await client.admin.command("ping")
        return True
    except Exception as e:
        logger.error(f"MongoDB health check failed: {e}")
        return False


async def check_redis_health() -> bool:
    try:
        redis = RedisClient.get_client()
        await redis.ping()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False


async def check_all_databases() -> dict:
    return {
        "postgres": await check_postgres_health(),
        "mongodb": await check_mongodb_health(),
        "redis": await check_redis_health(),
    }


async def startup_databases():
    logger.info("Initializing database connections...")
    if await check_postgres_health():
        logger.info("PostgreSQL connected")
    else:
        logger.error("PostgreSQL connection failed")
    if await check_mongodb_health():
        logger.info("MongoDB connected")
    else:
        logger.error("MongoDB connection failed")
    if await check_redis_health():
        logger.info("Redis connected")
    else:
        logger.error("Redis connection failed")


async def shutdown_databases():
    logger.info("Closing database connections...")
    await RedisClient.close()
    await MongoDBClient.close()
    await engine.dispose()
    logger.info("All database connections closed")
