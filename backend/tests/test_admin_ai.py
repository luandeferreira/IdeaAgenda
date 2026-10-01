import asyncio

from Service.ai import providers
from tests.conftest import login


async def test_owner_switches_ai_provider(client):
    owner, owner_user = await login(client, "dono@ideaagenda.dev", "Dono")
    other, _ = await login(client, "user@ideaagenda.dev")
    assert owner_user["is_admin"] is True

    assert (await client.get("/api/admin/settings/ai", headers=other)).status_code == 403

    resp = await client.get("/api/admin/settings/ai", headers=owner)
    assert resp.json()["provider"] == "openai"
    assert resp.json()["openai_configured"] and resp.json()["gemini_configured"]

    resp = await client.put("/api/admin/settings/ai", headers=owner, json={"provider": "gemini", "gemini_model": "gemini-2.5-pro"})
    assert resp.status_code == 200
    assert resp.json()["provider"] == "gemini" and resp.json()["gemini_model"] == "gemini-2.5-pro"

    resp = await client.get("/api/ai/provider", headers=other)
    assert resp.json() == {"provider": "gemini", "model": "gemini-2.5-pro", "available": True}


async def test_ai_suggestions_and_apply(client, monkeypatch):
    headers, _ = await login(client)
    t1 = (await client.post("/api/tasks", headers=headers, json={"title": "Relatório", "priority": "low"})).json()
    t2 = (await client.post("/api/tasks", headers=headers, json={"title": "Academia"})).json()

    calls = {}

    async def fake_generate(self, system, prompt):
        calls["provider"] = self.name
        calls["prompt"] = prompt
        return {
            "summary": "Organizei sua semana.",
            "suggestions": [
                {"task_id": t1["id"], "start_at": "2030-02-01T09:00:00-03:00", "end_at": "2030-02-01T10:00:00-03:00", "priority": "high", "reason": "prazo"},
                {"task_id": 99999, "start_at": "2030-02-01T11:00:00-03:00"},  # id inválido é descartado
                {"task_id": t2["id"], "start_at": "bobagem"},
            ],
            "tips": ["Faça pausas"],
        }

    monkeypatch.setattr(providers.OpenAIProvider, "generate_json", fake_generate)
    resp = await client.post("/api/ai/suggestions", headers=headers, json={"horizon_days": 7})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert calls["provider"] == "openai"
    assert "Relatório" in calls["prompt"]
    assert [s["task_id"] for s in data["suggestions"]] == [t1["id"], t2["id"]]
    assert data["suggestions"][1]["start_at"] is None
    assert data["tips"] == ["Faça pausas"]

    s = data["suggestions"][0]
    resp = await client.post(
        "/api/ai/suggestions/apply",
        headers=headers,
        json={"items": [{"task_id": s["task_id"], "start_at": s["start_at"], "end_at": s["end_at"], "priority": s["priority"]}]},
    )
    assert resp.status_code == 200
    applied = resp.json()[0]
    assert applied["priority"] == "high"
    assert applied["start_at"].startswith("2030-02-01T12:00:00")


async def test_ai_parse_with_gemini(client, monkeypatch):
    owner, _ = await login(client, "dono@ideaagenda.dev")
    await client.put("/api/admin/settings/ai", headers=owner, json={"provider": "gemini"})

    async def fake_generate(self, system, prompt):
        assert self.name == "gemini"
        return {"title": "Dentista", "priority": "high", "start_at": "2030-03-01T15:00:00", "estimated_minutes": 45}

    monkeypatch.setattr(providers.GeminiProvider, "generate_json", fake_generate)
    resp = await client.post("/api/ai/parse", headers=owner, json={"text": "dentista dia 1 de março às 15h"})
    assert resp.status_code == 200, resp.text
    task = resp.json()["task"]
    assert resp.json()["provider"] == "gemini"
    assert task["title"] == "Dentista" and task["estimated_minutes"] == 45
    assert task["start_at"] == "2030-03-01T15:00:00-03:00"


async def test_ai_rate_limit(client, monkeypatch):
    from Config.settings import get_settings

    monkeypatch.setattr(get_settings(), "ai_rate_limit_per_hour", 1)
    headers, _ = await login(client)
    await client.post("/api/tasks", headers=headers, json={"title": "x"})

    async def fake_generate(self, system, prompt):
        return {"summary": "ok", "suggestions": []}

    monkeypatch.setattr(providers.OpenAIProvider, "generate_json", fake_generate)
    assert (await client.post("/api/ai/suggestions", headers=headers, json={})).status_code == 200
    assert (await client.post("/api/ai/suggestions", headers=headers, json={})).status_code == 429


def test_extract_json_tolerates_fences():
    assert providers.extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert providers.extract_json('Aqui está: {"a": 2} fim') == {"a": 2}


async def test_logs_are_stored_in_redis(client):
    owner, _ = await login(client, "dono@ideaagenda.dev")
    other, _ = await login(client, "user@ideaagenda.dev")
    await client.post("/api/tasks", headers=other, json={"title": "logada"})
    await asyncio.sleep(0.3)  # QueueListener grava em outra thread

    assert (await client.get("/api/admin/logs", headers=other)).status_code == 403
    logs = (await client.get("/api/admin/logs?limit=50", headers=owner)).json()
    events = [entry["extra"].get("event") for entry in logs if entry.get("extra")]
    assert "task_created" in events
    assert "http_request" in events

    warn = (await client.get("/api/admin/logs?level=WARNING", headers=owner)).json()
    assert all(entry["level"] in ("WARNING", "ERROR", "CRITICAL") for entry in warn)
    assert any(e["extra"].get("status") == 403 for e in warn if e.get("extra"))

    stats = (await client.get("/api/admin/logs/stats", headers=owner)).json()
    assert stats["entries"] > 0
