# backend/app/main.py
from fastapi import FastAPI, Request, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
from starlette_exporter import PrometheusMiddleware, handle_metrics

import sentry_sdk
import uuid
import logging
import hmac

from .core.config import settings
from .core.logging import configure_logging, correlation_id_ctx
from .core.rate_limit import limiter

from .routers import health, auth, webhooks, tenants, metrics
from .routers import contacts, message_logs, failed_events, dashboard, reports

configure_logging(settings.log_level)
logger = logging.getLogger("app")

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=getattr(settings, "sentry_traces_sample_rate", 0.1),
        profiles_sample_rate=getattr(settings, "sentry_profiles_sample_rate", 0.0),
    )

openapi_url = "/openapi.json" if settings.env != "production" else None
docs_url = "/docs" if settings.env != "production" else None
redoc_url = "/redoc" if settings.env != "production" else None

app = FastAPI(
    title="Multi-Tenant Webhook API",
    version="0.4.0",
    openapi_url=openapi_url,
    docs_url=docs_url,
    redoc_url=redoc_url,
)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def ratelimit_handler(request: Request, exc: RateLimitExceeded):
    rid = request.headers.get("X-Request-ID") or ""
    return JSONResponse(status_code=429, content={"detail": "Too Many Requests", "request_id": rid}, headers={"Retry-After": "30"})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    rid = request.headers.get("X-Request-ID") or ""
    return JSONResponse(status_code=422, content={"detail": exc.errors(), "request_id": rid})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    rid = request.headers.get("X-Request-ID") or ""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "request_id": rid})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    rid = request.headers.get("X-Request-ID") or ""
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error", "request_id": rid})


app.add_middleware(ProxyHeadersMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts_list)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=settings.allowed_headers_list,
    expose_headers=["X-Request-ID"],
    max_age=600,
)

if settings.sentry_dsn:
    app.add_middleware(SentryAsgiMiddleware)


def require_metrics_token(x_metrics_token: str = Header(default="", alias="X-Metrics-Token")):
    if settings.env != "production":
        return
    expected = settings.metrics_token
    if not expected:
        raise HTTPException(status_code=500, detail="Metrics token not configured")
    if not hmac.compare_digest(x_metrics_token, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


app.add_middleware(PrometheusMiddleware, app_name="webhook-api", group_paths=True)


@app.get("/metrics", include_in_schema=False)
async def metrics_endpoint(request: Request, _=Depends(require_metrics_token)):
    return handle_metrics(request)


@app.middleware("http")
async def correlation_and_security(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = correlation_id_ctx.set(rid)
    try:
        resp = await call_next(request)
    finally:
        correlation_id_ctx.reset(token)

    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Frame-Options"] = "DENY"

    if settings.env == "production":
        resp.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none';"
        )
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Request-ID"] = rid
    return resp


@app.on_event("startup")
async def on_startup():
    logger.info("API starting up")
    if settings.env == "production":
        try:
            from .core.redis import get_redis
            redis_client = await get_redis()
            await redis_client.ping()
            logger.info("Redis connection verified")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("API shutting down")
    try:
        from .core.redis import close_redis
        await close_redis()
    except Exception as e:
        logger.error(f"Error closing Redis: {e}")

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(webhooks.router)
app.include_router(tenants.router)
app.include_router(metrics.router)
app.include_router(contacts.router)
app.include_router(message_logs.router)
app.include_router(failed_events.router)
app.include_router(dashboard.router)
app.include_router(reports.router)
