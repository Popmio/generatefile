import requests
import time
import json
import os
import logging
import pytest
from requests.exceptions import RequestException

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 配置常量
BASE_URL = "http://localhost:8000"
ACCEPT_URL = f"http://localhost:7999/accept"
SSE_BASE_URL = f"{BASE_URL}/api/sse"

# 模拟请求头中的 API Key
API_KEY = os.getenv("ALLOWED_API_KEYS", "secret123").split(",")[0]

# 最大重试次数和重试间隔（秒）
MAX_RETRIES = 3
RETRY_DELAY = 5  # 重试间隔时间

# @pytest.mark.parametrize("run_id", range(10))
# def test_accept(run_id):
def test_accept():
    """
    测试 /accept 接口，获取 task_id 和 token
    """
    payload = {
        "user_id": "test_user",
        "input_data": {"foo": "bar"},
        "agent_types": ["1", "2"]
    }
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }

    logger.info("Sending request to /accept")
    response = requests.post(ACCEPT_URL, json=payload, headers=headers)

    assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"

    data = response.json()
    logger.info(f"Received from /accept: {data}")

    expected_keys = {"status_code", "task_id", "token"}
    assert set(data.keys()) == expected_keys, f"Missing keys in response: {set(data.keys())}"
    assert data["status_code"] == 200
    assert isinstance(data["task_id"], str)
    assert isinstance(data["token"], str)

    print(json.dumps(data, indent=4))

    task_id = data["task_id"]
    token = data["token"]

    """
    使用 requests 流式监听 SSE 接口
    """
    user_id = "test_user"
    sse_url = f"{SSE_BASE_URL}/{user_id}/{task_id}?token={token}"
    logger.info(f"🔌 Connecting to SSE stream at {sse_url}")
    time.sleep(3)

    retries = 0
    while retries < MAX_RETRIES:
        try:
            with requests.get(sse_url, stream=True, timeout=10000, headers={"Accept": "text/event-stream"}) as r:
                print(f"🌐 Status Code: {r.status_code}")
                print(f"- Headers: {r.headers}")

                if r.status_code != 200:
                    logger.error("❌ Failed to connect to SSE endpoint.")
                    retries += 1
                    logger.info(f"Retrying in {RETRY_DELAY} seconds... (Attempt {retries}/{MAX_RETRIES})")
                    time.sleep(RETRY_DELAY)
                    continue

                logger.info("🟢 SSE connected. Waiting for messages...")

                start_time = time.time()

                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    try:
                        line = line[5:].strip()
                        line = json.loads(line)
                        print(f"- Line: {line}")
                        logger.info(f"[{time.time() - start_time:.2f}s] 📨 收到消息：{line}")
                    except Exception as e:
                        logger.warning(f"⚠️ 解码失败: {e}")
                break  # 连接成功后退出重试循环

        except RequestException as e:
            logger.error(f"❌ 请求失败: {e}")
            retries += 1
            if retries < MAX_RETRIES:
                logger.info(f"Retrying in {RETRY_DELAY} seconds... (Attempt {retries}/{MAX_RETRIES})")
                time.sleep(RETRY_DELAY)
            else:
                logger.error("❌ Max retries reached. Could not establish SSE connection.")
                break  # 超过最大重试次数后跳出循环
