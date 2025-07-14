import time
from http.client import HTTPException
import asyncio
import httpx
from fastapi import FastAPI, Request
import uvicorn
from backend.baseagent import BaseAgent
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

agent = BaseAgent(
    name="Charpter1Agent",
    role="assistant",
    system_prompt="你是一个专业的医疗器械注册助手。",
    model_type="qwen"
)

async def background_task(data):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await asyncio.sleep(5)
            logger.info(f"Connecting to {data}")
            response = await client.post(url=data["callback_url"], json={"subtask_id":"1","status":"completed","file_url":"www.111.com"})
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException()
    except Exception as e:
        raise HTTPException()


@app.post("/agent")
async def do_task(request: Request):
    data = await request.json()

    response = {"status": "accepted"}
    asyncio.create_task(background_task(data))
    return response

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
