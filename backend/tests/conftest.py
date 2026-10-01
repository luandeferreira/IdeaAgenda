import os

os.environ.update(
    {
        "DATABASE_URL": "sqlite+aiosqlite:///./test.db",
        "ALLOW_DEV_LOGIN": "true",
        "ADMIN_EMAILS": "dono@ideaagenda.dev",
        "SECRET_KEY": "test-secret-key-with-at-least-32-bytes!!",
        "OPENAI_API_KEY": "sk-test",
        "GEMINI_API_KEY": "gm-test",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "AI_RATE_LIMIT_PER_HOUR": "100",
    }
)

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from Config import redis_client  # noqa: E402
from Config.database import Base, engine, init_db  # noqa: E402
from Config.logging_config import setup_logging, shutdown_logging  # noqa: E402


@pytest.fixture
async def app():
    server = fakeredis.FakeServer()
    redis_client.set_redis_clients(
        fakeredis.FakeAsyncRedis(server=server, decode_responses=True),
        fakeredis.FakeRedis(server=server, decode_responses=True),
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    setup_logging()
    from main import app as fastapi_app

    yield fastapi_app
    shutdown_logging()
    redis_client.set_redis_clients(None, None)


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def login(client, email="user@ideaagenda.dev", name="Usuário"):
    resp = await client.post("/api/auth/dev-login", json={"email": email, "name": name})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return {"Authorization": f"Bearer {data['access_token']}"}, data["user"]
