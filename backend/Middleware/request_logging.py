import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from Service.security import decode_token

logger = logging.getLogger("ideaagenda.http")

SKIP_PATHS = {"/api/health"}


def _user_id_from_request(request: Request) -> int | None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    try:
        return int(decode_token(auth[7:])["sub"])
    except Exception:
        return None


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Registra cada requisição (método, rota, status, duração, usuário) nos logs/Redis."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            logger.exception("Erro não tratado", extra={"request_id": request_id, "path": request.url.path})
            raise
        finally:
            if request.url.path not in SKIP_PATHS:
                duration_ms = round((time.perf_counter() - start) * 1000, 1)
                level = logging.ERROR if status_code >= 500 else logging.WARNING if status_code >= 400 else logging.INFO
                logger.log(
                    level,
                    f"{request.method} {request.url.path} {status_code} {duration_ms}ms",
                    extra={
                        "event": "http_request",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status": status_code,
                        "duration_ms": duration_ms,
                        "user_id": _user_id_from_request(request),
                        "client_ip": request.client.host if request.client else None,
                    },
                )
