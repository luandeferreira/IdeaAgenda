"""Consulta dos logs gravados no Redis Stream."""

import json

from Config.redis_client import get_async_redis
from Config.settings import get_settings
from Dto.dto import LogEntryOut

LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


async def read_logs(
    limit: int = 100,
    level: str | None = None,
    search: str | None = None,
    user_id: int | None = None,
    before: str | None = None,
) -> list[LogEntryOut]:
    """Lê os logs mais recentes (XREVRANGE), aplicando filtros em memória."""
    redis = get_async_redis()
    key = get_settings().log_stream_key
    min_level = LEVELS.index(level.upper()) if level and level.upper() in LEVELS else 0
    needle = search.lower() if search else None

    results: list[LogEntryOut] = []
    max_id = f"({before}" if before else "+"
    batch = max(limit * 3, 200)
    scanned = 0
    while len(results) < limit and scanned < 20000:
        entries = await redis.xrevrange(key, max=max_id, min="-", count=batch)
        if not entries:
            break
        for entry_id, fields in entries:
            scanned += 1
            max_id = f"({entry_id}"
            lvl = fields.get("level", "INFO")
            if lvl in LEVELS and LEVELS.index(lvl) < min_level:
                continue
            try:
                data = json.loads(fields.get("data", "{}"))
            except json.JSONDecodeError:
                data = {}
            extra = data.get("extra")
            if user_id is not None and (not extra or extra.get("user_id") != user_id):
                continue
            if needle and needle not in fields.get("data", fields.get("message", "")).lower():
                continue
            results.append(
                LogEntryOut(
                    id=entry_id,
                    ts=fields.get("ts", ""),
                    level=lvl,
                    logger=fields.get("logger", ""),
                    message=fields.get("message", ""),
                    extra=extra,
                    exception=data.get("exception"),
                )
            )
            if len(results) >= limit:
                break
        if len(entries) < batch:
            break
    return results


async def log_stats() -> dict:
    redis = get_async_redis()
    key = get_settings().log_stream_key
    length = await redis.xlen(key)
    return {"stream": key, "entries": length, "max_entries": get_settings().log_max_entries}
