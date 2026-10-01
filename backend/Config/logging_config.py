"""Logging estruturado com envio para Redis Streams.

Cada registro de log vira uma entrada no stream ``LOG_STREAM_KEY`` (XADD com MAXLEN
aproximado), o que permite consultar os logs pelo painel do administrador ou com
``redis-cli XREVRANGE ideaagenda:logs + - COUNT 20``.

A escrita no Redis acontece numa thread separada (QueueHandler/QueueListener)
para não bloquear o event loop do FastAPI. Se o Redis estiver fora do ar, os logs
continuam saindo no stdout.
"""

import json
import logging
import queue
import sys
from datetime import datetime, timezone
from logging.handlers import QueueHandler, QueueListener

from Config.redis_client import get_sync_redis
from Config.settings import get_settings

_STANDARD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}

_listener: QueueListener | None = None


def _extra_fields(record: logging.LogRecord) -> dict:
    return {k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS and not k.startswith("_")}


def record_to_dict(record: logging.LogRecord) -> dict:
    data = {
        "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
        "level": record.levelname,
        "logger": record.name,
        "message": record.getMessage(),
    }
    extra = _extra_fields(record)
    if extra:
        data["extra"] = extra
    if record.exc_info:
        data["exception"] = logging.Formatter().formatException(record.exc_info)
    return data


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(record_to_dict(record), ensure_ascii=False, default=str)


class RedisStreamHandler(logging.Handler):
    """Envia cada log para um Redis Stream com tamanho limitado."""

    def __init__(self, stream_key: str, max_entries: int, client_factory=get_sync_redis):
        super().__init__()
        self.stream_key = stream_key
        self.max_entries = max_entries
        self._client_factory = client_factory
        self._warned = False

    def emit(self, record: logging.LogRecord) -> None:
        try:
            data = record_to_dict(record)
            fields = {
                "ts": data["ts"],
                "level": data["level"],
                "logger": data["logger"],
                "message": data["message"],
                "data": json.dumps(data, ensure_ascii=False, default=str),
            }
            self._client_factory().xadd(self.stream_key, fields, maxlen=self.max_entries, approximate=True)
            self._warned = False
        except Exception as exc:  # pragma: no cover - depende de infraestrutura
            if not self._warned:
                sys.stderr.write(f"[logging] não foi possível gravar log no Redis: {exc}\n")
                self._warned = True


def setup_logging() -> None:
    """Configura o logger raiz: stdout (JSON) + Redis Stream (assíncrono via fila)."""
    global _listener
    settings = get_settings()

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    for h in list(root.handlers):
        root.removeHandler(h)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(JsonFormatter())
    root.addHandler(stdout_handler)

    log_queue: queue.Queue = queue.Queue(-1)
    redis_handler = RedisStreamHandler(settings.log_stream_key, settings.log_max_entries)
    if _listener is not None:
        _listener.stop()
    _listener = QueueListener(log_queue, redis_handler, respect_handler_level=True)
    _listener.start()
    root.addHandler(QueueHandler(log_queue))

    # Evita duplicar logs de acesso do uvicorn (o middleware já registra cada request).
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def shutdown_logging() -> None:
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None
