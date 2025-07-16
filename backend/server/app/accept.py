import os
import logging
from fastapi import FastAPI, Request, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type, before_sleep_log
import httpx
from backend.types import StartTaskRequest, CallbackData

BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000/api/start-task")
MAX_TIMEOUT = float(os.getenv("FORWARD_TIMEOUT", "30.0"))
RETRY_WAIT_SECONDS = int(os.getenv("RETRY_WAIT_SECONDS", "10"))
RETRY_MAX_ATTEMPTS = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
API_KEYS = os.getenv("ALLOWED_API_KEYS", "secret123").split(",")

def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    if api_key not in API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid or missing API Key")
    return api_key

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

retry_decorator = retry(
    stop=stop_after_attempt(RETRY_MAX_ATTEMPTS),
    wait=wait_fixed(RETRY_WAIT_SECONDS),
    retry=retry_if_exception_type((httpx.RequestError,)),
    before_sleep=before_sleep_log(logger, logging.WARNING)
)

@app.post("/accept")
@limiter.limit("100/minute")
@retry_decorator
async def send_task(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    logger.info(f"Received request from {request.client.host} with API Key: {api_key}")

    try:
        # 尝试解析 JSON 数据并使用 Pydantic 验证
        data = await request.json()
        payload = StartTaskRequest(
            user_id=data["user_id"],
            input_data=data["input_data"],
            agent_types=data["agent_types"]
        )

        logger.info(f"Validated task for user_id: {payload.user_id}")

    except KeyError as e:
        # 处理字段缺失的情况
        logger.error(f"Missing expected field: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Missing expected field: {str(e)}"
        )
    except json.JSONDecodeError as e:
        # 处理 JSON 解码错误
        logger.error(f"Failed to decode JSON: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON format: {str(e)}"
        )
    except Exception as e:
        # 其他未知错误
        logger.error(f"Failed to parse request data: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid request data: {str(e)}"
        )

    headers = {"Content-Type": "application/json"}

    # 向后端发送请求
    async with httpx.AsyncClient(timeout=MAX_TIMEOUT) as client:
        try:
            logger.info(f"Forwarding task to {BACKEND_API_URL}")
            response = await client.post(
                BACKEND_API_URL,
                json=payload.model_dump(),
                headers=headers
            )
            response.raise_for_status()
            logger.info(f"Successfully forwarded task. Status code: {response.status_code}")

        except httpx.HTTPStatusError as exc:
            if 500 <= exc.response.status_code < 600:
                logger.warning(f"Server error: {exc}, will retry...")
                raise
            else:
                logger.error(f"Remote service error: {exc.response.status_code} - {exc.response.text}")
                raise HTTPException(
                    status_code=exc.response.status_code,
                    detail=f"Remote service returned error: {exc}"
                )

        except httpx.RequestError as exc:
            logger.error(f"Network error: Failed to reach remote service: {exc}")
            raise HTTPException(
                status_code=503,
                detail=f"Failed to reach remote service: {exc}"
            )

    data = response.json()
    logger.info(f"Received response from backend, task_id: {data.get('task_id')}, token: {data.get('token')}")
    return {
        "status_code": response.status_code,
        "task_id": data.get("task_id"),
        "token": data.get("token")
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7999)
