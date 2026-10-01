from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from Config.settings import get_settings

_async_client: AsyncRedis | None = None
_sync_client: Redis | None = None


def get_async_redis() -> AsyncRedis:
    """Cliente assíncrono compartilhado (endpoints, rate limit, leitura de logs)."""
    global _async_client
    if _async_client is None:
        _async_client = AsyncRedis.from_url(get_settings().redis_url, decode_responses=True)
    return _async_client


def get_sync_redis() -> Redis:
    """Cliente síncrono usado pelo handler de logging (roda em thread separada)."""
    global _sync_client
    if _sync_client is None:
        _sync_client = Redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _sync_client


def set_redis_clients(async_client: AsyncRedis | None, sync_client: Redis | None) -> None:
    """Permite injetar clientes (ex.: fakeredis nos testes)."""
    global _async_client, _sync_client
    _async_client = async_client
    _sync_client = sync_client


async def close_redis() -> None:
    global _async_client
    if _async_client is not None:
        await _async_client.aclose()
        _async_client = None
