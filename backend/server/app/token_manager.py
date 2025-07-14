from datetime import datetime, timedelta
from jose import jwt, JWTError
from dotenv import load_dotenv
load_dotenv()
import os

SECRET_KEY = os.getenv('SECRET_KEY')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 一周有效期


def create_access_token(task_id: str, user_id: str):
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "task_id": task_id,
        "user_id": user_id,
        "exp": expire
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str, expected_user_id: str, expected_task_id: str) -> bool:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id")
        task_id: str = payload.get("task_id")
        if user_id != expected_user_id or task_id != expected_task_id:
            return False
        return True
    except JWTError:
        return False