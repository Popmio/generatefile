from datetime import datetime, timedelta
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError
from dotenv import load_dotenv
import os
import logging

# 加载环境变量
load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 一周有效期

# 设置日志
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# 创建访问令牌
def create_access_token(task_id: str, user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "task_id": task_id,
        "user_id": user_id,
        "exp": expire
    }
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    logger.debug(f"Generated token for task {task_id} and user {user_id}")
    return encoded_jwt


# 验证访问令牌
def verify_token(token: str, expected_user_id: str, expected_task_id: str) -> bool:
    try:
        # 解码 JWT 并验证有效期等
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id")
        task_id: str = payload.get("task_id")

        # 如果用户ID或任务ID不匹配，返回校验失败
        if user_id != expected_user_id or task_id != expected_task_id:
            logger.warning(f"Token verification failed: UserID or TaskID mismatch.")
            return False

        logger.info(f"Token verified successfully for TaskID: {task_id} and UserID: {user_id}")
        return True

    except ExpiredSignatureError:
        logger.error("Token has expired.")
        return False

    except JWTError as e:
        logger.error(f"Token validation error: {str(e)}")
        return False


# 自定义Token异常类型
class TokenVerificationError(Exception):
    pass
