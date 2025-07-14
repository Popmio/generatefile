# main_server/app/routes.py
import os
import asyncio
from fastapi import APIRouter, FastAPI, HTTPException,Query, Header, Depends
from fastapi.responses import StreamingResponse
import httpx
import uuid
from backend.types import StartTaskRequest, CallbackData
from .task_manager import task_manager
from typing import AsyncGenerator, Optional
import orjson
import json
import logging
from .token_manager import create_access_token, verify_token


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "agent_url.json")
CALLBACK_PATH = "http://localhost:8000/api/callback"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    AGENT_URLS = json.load(f)

router = APIRouter(prefix="/api")

@router.get("/sse/{user_id}/{task_id}")
async def sse_endpoint(
    user_id: str,
    task_id: str,
    token: str = Query(...),
    x_admin_token: Optional[str] = Header(None)
):

    if x_admin_token == os.getenv("ADMIN_SECRET_KEY"):
        logger.info(f"Admin accessed task {task_id}")

        async def stream() -> AsyncGenerator[bytes, None]:
            async for event in task_manager.listen_for_events(task_id):
                yield b'data: ' + orjson.dumps(event) + b'\n\n'
                logger.info(json.dumps(event))
        return StreamingResponse(stream(), media_type="text/event-stream")

    if not verify_token(token, user_id, task_id):
        raise HTTPException(status_code=403, detail="Invalid token")

    logger.info(f"Admin accessed task {task_id}")

    initial_state = await task_manager.get_initial_state(task_id)
    logger.info(f"Initial state: {initial_state}")
    if not initial_state:
        raise HTTPException(status_code=404, detail="Task not found")

    async def stream() -> AsyncGenerator[bytes, None]:
        async for event in task_manager.listen_for_events(task_id):
            yield b'data: ' + orjson.dumps(event) + b'\n\n'
            logger.info(json.dumps(event))

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/reload-config")
def reload_config():
    global AGENT_URLS
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            AGENT_URLS = json.load(f)
        logger.info("Agent URLs reloaded successfully.")
        return {"status": "ok"}

    except Exception as e:

        logger.error(f"Agent URLs reloaded failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to reload config: {e}")


@router.post("/start-task")
async def start_task(req: StartTaskRequest):
    task_id = str(uuid.uuid4())

    await task_manager.create_task(
        task_id=task_id,
        user_id=req.user_id,
        input_data=req.input_data,
        agent_types=req.agent_types
    )

    logger.info(f"user: {req.user_id} created task {task_id}")

    async def send_to_agent(agent_type: str):

        logger.info(f"user: {req.user_id} start sending {agent_type}")
        url = AGENT_URLS.get(agent_type, None)

        if not url:

            logger.error(f"user: {req.user_id} no such agent type: {agent_type}")
            raise HTTPException(status_code=400, detail=f"Unsupported or missing agent URL for type: {agent_type}")

        callback_url = f"{CALLBACK_PATH}/{task_id}/{agent_type}"

        payload = {
            "task_id": task_id,
            "user_id": req.user_id,
            "input": req.input_data,
            "callback_url": callback_url
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
            logger.info(f"user: {req.user_id} finished sending {agent_type}")

        except httpx.HTTPStatusError as e:

            logger.error(f"user: {req.user_id} failed to send {agent_type}: {e}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Agent {agent_type} returned error: {e}"
            )

        except Exception as e:

            logger.error(f"user: {req.user_id} failed to send {agent_type}: {e}")
            await task_manager.update_subtask_status(task_id, agent_type, "failed")
            await task_manager.broadcast_event(task_id)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to send to agent {agent_type}: {str(e)}"
            )

    tasks = [send_to_agent(agent_type) for agent_type in req.agent_types]

    try:
        await asyncio.gather(*tasks)
    except HTTPException as he:
        raise he

    logger.info(task_manager.tasks[task_id])

    return {
        "task_id": task_id,
        "token": create_access_token(task_id, req.user_id)
    }


@router.post("/callback/{task_id}/{agent_type}")
async def handle_callback(task_id: str, agent_type: str, data: CallbackData):
    logger.info(f"Received callback for task {task_id}, agent {agent_type}, status={data.status}")
    logger.debug(f"Full callback data: {data}")

    valid_statuses = ["pending", "running", "completed", "failed"]
    if data.status not in valid_statuses:
        logger.warning(f"Invalid status received: {data.status}")
        raise HTTPException(status_code=400, detail=f"Invalid status: {data.status}")

    success = await task_manager.update_subtask_status(
        task_id=task_id,
        agent_type=agent_type,
        status=data.status,
        file_url=data.file_url
    )

    if not success:
        logger.warning(f"Callback failed: Task {task_id} or agent {agent_type} not found")
        raise HTTPException(status_code=404, detail="Task or agent type not found")

    # if task_manager.is_task_completed(task_id):
    #     logger.info(f"Task {task_id} completed. Cleaning up asynchronously.")
    #     asyncio.create_task(task_manager.cleanup_task(task_id))
    logger.info(task_manager.tasks[task_id])
    return {"status": "ok"}


@router.get("/tasks/{user_id}")
async def get_tasks(user_id: str):
    return task_manager.get_user_tasks(user_id)

def register_routes(app: FastAPI):
    app.include_router(router)

@router.get("/health")
def health_check():
    return {"status": "ok"}

























