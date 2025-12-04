import time
import uuid
from typing import Optional, Dict, Tuple,List
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from app.utils.logger import get_loggers
from app.config import settings
import asyncio
logger = get_loggers("Middleware")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    EXCLUDE_PATHS = {"/health", "/metrics", "/favicon.ico"}
    SENSITIVE_HEADERS = {"authorization",
                         "x-api-key", "cookie", "x-csrf-token"}
    SENSITIVE_PARAMS = {"password", "token", "secret", "api_key"}

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        if request.url.path in self.EXCLUDE_PATHS:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        client_ip = self._get_client_ip(request)
        start_time = time.time()
        self._log_request(request_id, request, client_ip)
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            self._log_response(request_id, request, response, process_time)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{process_time:.3f}"
            return response
        except Exception as exc:
            process_time = time.time() - start_time
            logger.error(
                f"Request failed | "
                f"ID: {request_id} | "
                f"Method: {request.method} | "
                f"Path: {request.url.path} | "
                f"Error: {exc.__class__.__name__}: {str(exc)} | "
                f"Duration: {process_time:.3f}s",
                exc_info=True
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "Internal Server Error",
                    "request_id": request_id,
                    "message": "An unexpected error occurred. Please contact support."
                },
                headers={"X-Request-ID": request_id}
            )

    def _get_client_ip(self, request: Request) -> str:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        return request.client.host if request.client else "unknown"

    def _redact_sensitive_data(self, data: dict) -> dict:
        redacted = {}
        for key, value in data.items():
            if key.lower() in self.SENSITIVE_PARAMS or key.lower() in self.SENSITIVE_HEADERS:
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = value
        return redacted

    def _log_request(self, request_id: str, request: Request, client_ip: str):
        query_params = dict(request.query_params)
        safe_params = self._redact_sensitive_data(query_params)
        logger.info(
            f"→ Request | "
            f"ID: {request_id} | "
            f"Method: {request.method} | "
            f"Path: {request.url.path} | "
            f"Client: {client_ip} | "
            f"Params: {safe_params if safe_params else 'none'} | "
            f"User-Agent: {request.headers.get('user-agent', 'unknown')[:100]}"
        )

    def _log_response(self,request_id: str,request: Request,response: Response,duration: float):
        level = "info" if response.status_code < 400 else "warning" if response.status_code < 500 else "error"
        log_msg = (
            f"← Response | "
            f"ID: {request_id} | "
            f"Method: {request.method} | "
            f"Path: {request.url.path} | "
            f"Status: {response.status_code} | "
            f"Duration: {duration:.3f}s"
        )
        getattr(logger, level)(log_msg)


class RateLimitMiddleware(BaseHTTPMiddleware):
    EXEMPT_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}

    def __init__(
        self,
        app: ASGIApp,
        redis_client=None,
        requests_per_minute: int = 60,
        burst_size: int = 10
    ):
        super().__init__(app)
        self.redis = redis_client
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.window_size = 60

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)
        client_id = self._get_client_identifier(request)
        is_allowed, retry_after = await self._check_rate_limit(client_id)
        if not is_allowed:
            logger.warning(
                f"Rate limit exceeded | "
                f"Client: {client_id} | "
                f"Path: {request.url.path} | "
                f"Retry after: {retry_after}s"
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate Limit Exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retry_after": retry_after
                },
                headers={"Retry-After": str(retry_after)}
            )
        response = await call_next(request)
        return response

    def _get_client_identifier(self, request: Request) -> str:
        ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not ip:
            ip = request.headers.get("X-Real-IP", "")
        if not ip:
            ip = request.client.host if request.client else "unknown"
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return f"user:{user_id}"
        return f"ip:{ip}"

    async def _check_rate_limit(self, client_id: str) -> Tuple[bool, int]:
        if self.redis:
            return await self._check_rate_limit_redis(client_id)
        else:
            logger.warning(
                "Redis not available, using in-memory rate limiting (not distributed)")
            return await self._check_rate_limit_memory(client_id)

    async def _check_rate_limit_redis(self, client_id: str) -> Tuple[bool, int]:
        try:
            key = f"rate_limit:{client_id}"
            now = time.time()
            window_start = now - self.window_size
            pipe = self.redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            pipe.zadd(key, {str(now): now})
            pipe.expire(key, self.window_size)
            results = await pipe.execute()
            request_count = results[1]
            if request_count >= self.requests_per_minute:
                oldest_request = await self.redis.zrange(key, 0, 0, withscores=True)
                if oldest_request:
                    oldest_time = oldest_request[0][1]
                    retry_after = int(self.window_size -
                                      (now - oldest_time)) + 1
                else:
                    retry_after = self.window_size
                return False, retry_after
            return True, 0
        except Exception as e:
            logger.error(f"Redis rate limiting error: {e}")
            return True, 0

    async def _check_rate_limit_memory(self, client_id: str) -> Tuple[bool, int]:
        if not hasattr(self.app.state, "rate_limits"):
            self.app.state.rate_limits = {}
        rate_limits: Dict[str, List] = self.app.state.rate_limits
        now = time.time()
        window_start = now - self.window_size
        if client_id not in rate_limits:
            rate_limits[client_id] = []
        rate_limits[client_id] = [
            t for t in rate_limits[client_id] if t > window_start
        ]
        if len(rate_limits[client_id]) >= self.requests_per_minute:
            oldest = rate_limits[client_id][0]
            retry_after = int(self.window_size - (now - oldest)) + 1
            return False, retry_after
        rate_limits[client_id].append(now)
        if len(rate_limits) > 10000:
            asyncio.create_task(self._cleanup_old_clients())
        return True, 0

    async def _cleanup_old_clients(self):
        if not hasattr(self.app.state, "rate_limits"):
            return
        rate_limits = self.app.state.rate_limits
        now = time.time()
        window_start = now - self.window_size
        keys_to_delete = [
            client_id for client_id, requests in rate_limits.items()
            if not requests or all(t < window_start for t in requests)
        ]
        for key in keys_to_delete:
            del rate_limits[key]
        logger.debug(
            f"Cleaned up {len(keys_to_delete)} old rate limit entries")


class TimeoutMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, timeout_seconds: int = 30):
        super().__init__(app)
        self.timeout = timeout_seconds

    async def dispatch(self, request: Request, call_next):
        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=self.timeout
            )
        except asyncio.TimeoutError:
            logger.error(
                f"Request timeout | "
                f"Path: {request.url.path} | "
                f"Method: {request.method} | "
                f"Timeout: {self.timeout}s"
            )
            return JSONResponse(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                content={
                    "error": "Request Timeout",
                    "message": f"Request exceeded {self.timeout} second timeout"
                }
            )
