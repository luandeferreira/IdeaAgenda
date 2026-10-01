from tests.conftest import login


async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["database"] is True
    assert resp.json()["redis"] is True


async def test_requires_auth(client):
    assert (await client.get("/api/tasks")).status_code == 401


async def test_crud_flow(client):
    headers, user = await login(client)
    assert user["is_admin"] is False

    resp = await client.post(
        "/api/tasks",
        headers=headers,
        json={"title": "Estudar FastAPI", "priority": "high", "start_at": "2030-01-10T09:00:00-03:00", "estimated_minutes": 90},
    )
    assert resp.status_code == 201, resp.text
    task = resp.json()
    assert task["start_at"].startswith("2030-01-10T12:00:00")
    assert task["source"] == "app"

    await client.post("/api/tasks", headers=headers, json={"title": "Sem data"})
    tasks = (await client.get("/api/tasks", headers=headers)).json()
    assert [t["title"] for t in tasks] == ["Estudar FastAPI", "Sem data"]

    resp = await client.patch(f"/api/tasks/{task['id']}", headers=headers, json={"status": "done"})
    assert resp.json()["status"] == "done"
    assert len((await client.get("/api/tasks?status=done", headers=headers)).json()) == 1
    assert len((await client.get("/api/tasks?q=fastapi", headers=headers)).json()) == 1

    resp = await client.patch(f"/api/tasks/{task['id']}", headers=headers, json={"start_at": None})
    assert resp.json()["start_at"] is None and resp.json()["end_at"] is None

    assert (await client.delete(f"/api/tasks/{task['id']}", headers=headers)).status_code == 204
    assert (await client.get(f"/api/tasks/{task['id']}", headers=headers)).status_code == 404


async def test_invalid_dates(client):
    headers, _ = await login(client)
    resp = await client.post(
        "/api/tasks",
        headers=headers,
        json={"title": "x", "start_at": "2030-01-10T10:00:00Z", "end_at": "2030-01-10T09:00:00Z"},
    )
    assert resp.status_code == 422


async def test_tasks_are_isolated_per_user(client):
    h1, _ = await login(client, "a@x.dev")
    h2, _ = await login(client, "b@x.dev")
    task = (await client.post("/api/tasks", headers=h1, json={"title": "privada"})).json()
    assert (await client.get(f"/api/tasks/{task['id']}", headers=h2)).status_code == 404
    assert (await client.get("/api/tasks", headers=h2)).json() == []
