# # main_server/app/routes.py
# import os
# import asyncio
# from fastapi import APIRouter, FastAPI, HTTPException,Query, Header, Depends
# from fastapi.responses import StreamingResponse
# import httpx
# import uuid
# from backend.types import StartTaskRequest, CallbackData
# from .task_manager import task_manager
# from typing import AsyncGenerator, Optional
# import orjson
# import json
# import logging
# from .token_manager import create_access_token, verify_token
#
#
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# CONFIG_PATH = os.path.join(BASE_DIR, "agent_url.json")
# CALLBACK_PATH = "http://localhost:8000/api/callback"
#
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)
#
# with open(CONFIG_PATH, "r", encoding="utf-8") as f:
#     AGENT_URLS = json.load(f)
#
# router = APIRouter(prefix="/api")
#
# @router.get("/sse/{user_id}/{task_id}")
# async def sse_endpoint(
#     user_id: str,
#     task_id: str,
#     token: str = Query(...),
#     x_admin_token: Optional[str] = Header(None)
# ):
#
#     if x_admin_token == os.getenv("ADMIN_SECRET_KEY"):
#         logger.info(f"Admin accessed task {task_id}")
#
#         async def stream() -> AsyncGenerator[bytes, None]:
#             async for event in task_manager.listen_for_events(task_id):
#                 yield b'data: ' + orjson.dumps(event) + b'\n\n'
#                 logger.info(json.dumps(event))
#         return StreamingResponse(stream(), media_type="text/event-stream")
#
#     if not verify_token(token, user_id, task_id):
#         raise HTTPException(status_code=403, detail="Invalid token")
#
#     logger.info(f"Admin accessed task {task_id}")
#
#     initial_state = await task_manager.get_initial_state(task_id)
#     logger.info(f"Initial state: {initial_state}")
#     if not initial_state:
#         raise HTTPException(status_code=404, detail="Task not found")
#
#     async def stream() -> AsyncGenerator[bytes, None]:
#         async for event in task_manager.listen_for_events(task_id):
#             yield b'data: ' + orjson.dumps(event) + b'\n\n'
#             logger.info(json.dumps(event))
#
#     return StreamingResponse(stream(), media_type="text/event-stream")
#
#
# @router.post("/reload-config")
# def reload_config():
#     global AGENT_URLS
#     try:
#         with open(CONFIG_PATH, "r", encoding="utf-8") as f:
#             AGENT_URLS = json.load(f)
#         logger.info("Agent URLs reloaded successfully.")
#         return {"status": "ok"}
#
#     except Exception as e:
#
#         logger.error(f"Agent URLs reloaded failed: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Failed to reload config: {e}")
#
#
# @router.post("/start-task")
# async def start_task(req: StartTaskRequest):
#     task_id = str(uuid.uuid4())
#
#     await task_manager.create_task(
#         task_id=task_id,
#         user_id=req.user_id,
#         input_data=req.input_data,
#         agent_types=req.agent_types
#     )
#
#     logger.info(f"user: {req.user_id} created task {task_id}")
#
#     async def send_to_agent(agent_type: str):
#
#         logger.info(f"user: {req.user_id} start sending {agent_type}")
#         url = AGENT_URLS.get(agent_type, None)
#
#         if not url:
#
#             logger.error(f"user: {req.user_id} no such agent type: {agent_type}")
#             raise HTTPException(status_code=400, detail=f"Unsupported or missing agent URL for type: {agent_type}")
#
#         callback_url = f"{CALLBACK_PATH}/{task_id}/{agent_type}"
#
#         payload = {
#             "task_id": task_id,
#             "user_id": req.user_id,
#             "input": req.input_data,
#             "callback_url": callback_url
#         }
#
#         try:
#             async with httpx.AsyncClient(timeout=100.0) as client:
#                 response = await client.post(url, json=payload)
#                 response.raise_for_status()
#             logger.info(f"user: {req.user_id} finished sending {agent_type}")
#
#         except httpx.HTTPStatusError as e:
#
#             logger.error(f"user: {req.user_id} failed to send {agent_type}: {e}")
#             raise HTTPException(
#                 status_code=e.response.status_code,
#                 detail=f"Agent {agent_type} returned error: {e}"
#             )
#
#         except Exception as e:
#
#             logger.error(f"user: {req.user_id} failed to send {agent_type}: {e}")
#             await task_manager.update_subtask_status(task_id, agent_type, "failed")
#             await task_manager.broadcast_event(task_id)
#             raise HTTPException(
#                 status_code=500,
#                 detail=f"Failed to send to agent {agent_type}: {str(e)}"
#             )
#
#     tasks = [send_to_agent(agent_type) for agent_type in req.agent_types]
#
#     try:
#         await asyncio.gather(*tasks)
#     except HTTPException as he:
#         raise he
#
#     logger.info(task_manager.tasks[task_id])
#
#     return {
#         "task_id": task_id,
#         "token": create_access_token(task_id, req.user_id)
#     }
#
#
# @router.post("/callback/{task_id}/{agent_type}")
# async def handle_callback(task_id: str, agent_type: str, data: CallbackData):
#     logger.info(f"Received callback for task {task_id}, agent {agent_type}, status={data.status}")
#     logger.debug(f"Full callback data: {data}")
#
#     valid_statuses = ["pending", "running", "completed", "failed"]
#     if data.status not in valid_statuses:
#         logger.warning(f"Invalid status received: {data.status}")
#         raise HTTPException(status_code=400, detail=f"Invalid status: {data.status}")
#
#     success = await task_manager.update_subtask_status(
#         task_id=task_id,
#         agent_type=agent_type,
#         status=data.status,
#         file_url=data.file_url
#     )
#
#     if not success:
#         logger.warning(f"Callback failed: Task {task_id} or agent {agent_type} not found")
#         raise HTTPException(status_code=404, detail="Task or agent type not found")
#
#     # if task_manager.is_task_completed(task_id):
#     #     logger.info(f"Task {task_id} completed. Cleaning up asynchronously.")
#     #     asyncio.create_task(task_manager.cleanup_task(task_id))
#     logger.info(task_manager.tasks[task_id])
#     return {"status": "ok"}
#
#
# @router.get("/tasks/{user_id}")
# async def get_tasks(user_id: str):
#     return task_manager.get_user_tasks(user_id)
#
# def register_routes(app: FastAPI):
#     app.include_router(router)
#
# @router.get("/health")
# def health_check():
#     return {"status": "ok"}
#
#

import os
import asyncio
from fastapi import APIRouter, FastAPI, HTTPException, Query, Header, Depends
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
from jose.exceptions import ExpiredSignatureError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "agent_url.json")
CALLBACK_PATH = "http://localhost:8000/api/callback"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    AGENT_URLS = json.load(f)

router = APIRouter(prefix="/api")

semaphore = asyncio.Semaphore(5)


def token_verification_dependency(token: str = Query(...), expected_user_id: str = None, expected_task_id: str = None):
    if expected_user_id and expected_task_id:
        if not verify_token(token, expected_user_id, expected_task_id):
            logger.warning(f"Token verification failed for TaskID: {expected_task_id} and UserID: {expected_user_id}")
            raise HTTPException(status_code=403, detail="Invalid or expired token")
    return token


def get_agent_urls_dependency():
    global AGENT_URLS
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            AGENT_URLS = json.load(f)
        logger.info("Agent URLs loaded successfully.")
    except Exception as e:
        logger.error(f"Failed to load Agent URLs: {e}")
        raise HTTPException(status_code=500, detail="Failed to load agent URLs.")
    return AGENT_URLS


async def concurrency_control_dependency():
    async with semaphore:
        return True


@router.get("/sse/{user_id}/{task_id}")
async def sse_endpoint(
    user_id: str,
    task_id: str,
    token: str = Depends(token_verification_dependency),  # 普通用户 token 校验
    x_admin_token: Optional[str] = Header(None)  # 管理员密钥
):
    if x_admin_token == os.getenv("ADMIN_SECRET_KEY"):
        logger.info(f"Admin accessed task {task_id}")

        async def stream() -> AsyncGenerator[bytes, None]:
            async for event in task_manager.listen_for_events(task_id):
                yield b'data: ' + orjson.dumps(event) + b'\n\n'
                logger.info(json.dumps(event))

        return StreamingResponse(stream(), media_type="text/event-stream")

    logger.info(f"User {user_id} accessed task {task_id}")

    initial_state = await task_manager.get_initial_state(task_id)
    if not initial_state:
        logger.error(f"Task {task_id} not found for user {user_id}")
        raise HTTPException(status_code=404, detail="Task not found")

    async def stream() -> AsyncGenerator[bytes, None]:
        async for event in task_manager.listen_for_events(task_id):
            yield b'data: ' + orjson.dumps(event) + b'\n\n'
            logger.info(json.dumps(event))

    return StreamingResponse(stream(), media_type="text/event-stream")



@router.post("/reload-config")
async def reload_config(agent_urls: dict = Depends(get_agent_urls_dependency)):
    return {"status": "ok"}

@router.post("/start-task")
async def start_task(
        req: StartTaskRequest,
        agent_urls: dict = Depends(get_agent_urls_dependency),
        _=Depends(concurrency_control_dependency)
):
    task_id = str(uuid.uuid4())

    await task_manager.create_task(
        task_id=task_id,
        user_id=req.user_id,
        input_data=req.input_data,
        agent_types=req.agent_types
    )
    token = create_access_token(task_id, req.user_id)

    logger.info(f"User: {req.user_id} created task {task_id}")

    async def send_to_agent(agent_type: str):
        logger.info(f"User {req.user_id} is sending task {task_id} to agent {agent_type}")
        url = agent_urls.get(agent_type)
        if not url:
            logger.error(f"Agent type {agent_type} is missing for user {req.user_id}")
            raise HTTPException(status_code=400, detail=f"Missing agent URL for type: {agent_type}")

        callback_url = f"{CALLBACK_PATH}/{req.user_id}/{task_id}/{agent_type}"
        payload = {
            "task_id": task_id,
            "user_id": req.user_id,
            "input": req.input_data,
            "callback_url": callback_url,
            "token": token
        }

        try:
            async with httpx.AsyncClient(timeout=100.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
            logger.info(f"User {req.user_id} successfully sent task {task_id} to agent {agent_type}")

        except httpx.HTTPStatusError as e:
            logger.error(f"User {req.user_id} failed to send task {task_id} to agent {agent_type}: {e}")
            raise HTTPException(status_code=e.response.status_code, detail=f"Agent {agent_type} error: {e}")
        except httpx.RequestError as e:
            logger.error(
                f"Network error for user {req.user_id} while sending task {task_id} to agent {agent_type}: {e}")
            raise HTTPException(status_code=503, detail="Failed to reach agent")

    tasks = [send_to_agent(agent_type) for agent_type in req.agent_types]
    try:
        await asyncio.gather(*tasks)
    except HTTPException as e:
        raise e

    logger.info(f"Task {task_id} created and distributed to agents: {req.agent_types}")

    return {
        "task_id": task_id,
        "token": token
    }


@router.post("/callback/{user_id}/{task_id}/{agent_type}")
async def handle_callback(
        user_id: str,
        task_id: str,
        agent_type: str,
        data: CallbackData,
        token: str = Depends(token_verification_dependency),
        _=Depends(concurrency_control_dependency)
):
    if not token_verification_dependency(token, user_id, task_id):
        return None

    logger.info(f"Received callback for task {task_id}, agent {agent_type}, status={data.status}")
    logger.debug(f"Full callback data: {data}")

    valid_statuses = ["pending", "running", "completed", "failed"]
    if data.status not in valid_statuses:
        logger.warning(f"Invalid status received: {data.status}")
        raise HTTPException(status_code=400, detail=f"Invalid status: {data.status}")

    try:
        success = await task_manager.update_subtask_status(
            task_id=task_id,
            agent_type=agent_type,
            status=data.status,
            file_url=data.file_url
        )

        if not success:
            logger.warning(f"Callback failed: Task {task_id} or agent {agent_type} not found")
            raise HTTPException(status_code=404, detail="Task or agent type not found")

        if data.status == "completed":
            logger.info(f"Task {task_id} completed by agent {agent_type}")

        logger.info(f"Callback processed for task {task_id}. Current status: {data.status}")
        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing callback for task {task_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/tasks/{user_id}")
async def get_tasks(user_id: str):
    return task_manager.get_user_tasks(user_id)


def register_routes(app: FastAPI):
    app.include_router(router)


@router.get("/health")
def health_check():
    return {"status": "ok"}

