import asyncio
import datetime
import os
import time

import orjson
import pytest
from httpx import AsyncClient, ASGITransport
from backend.server.app.accept import app as accept_app
from backend.server.app.router import register_routes
import logging
import httpx
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
register_routes(accept_app)

@pytest.mark.asyncio
async def test_accept():
    payload = {
        "user_id": "test_user",
        "input_data": {"foo": "bar"},
        "agent_types": ["1","2"]
    }
    headers = {"X-API-Key": os.getenv("ALLOWED_API_KEYS", "secret123").split(",")[0]}

    transport = ASGITransport(app=accept_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/accept", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        print("ACCEPT接口返回:", data)
        logging.warning(f"ACCEPT接口返回: {data}")
        assert set(data.keys()) == {"status_code", "task_id", "token"}
        assert data["status_code"] == 200
        assert isinstance(data["task_id"], str)
        assert isinstance(data["token"], str)

    async def listen_sse(user_id: str, task_id: str, token: str):
        url = f"http://localhost:8000/api/sse/{user_id}/{task_id}?token={token}"
        print(f"🔌 Connecting to SSE: {url}")

        async with httpx.AsyncClient(timeout=1000) as client:
            async with client.stream("GET", url) as response:
                print(f"🌐 Status Code: {response.status_code}")
                print(f"-Headers: {response.headers}")

                if response.status_code != 200:
                    print("❌ Failed to connect")
                    return

                print("🟢 SSE connected, waiting for messages...")

                async for line in response.aiter_lines():
                    if line.strip() == "":
                        continue
                    print(f"{time.time() - start_time}📨 收到消息：{line}")

    start_time = time.time()
    await listen_sse("test_user", data["task_id"], data["token"])