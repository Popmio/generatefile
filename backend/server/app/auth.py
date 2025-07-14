# auth.py
from fastapi import Depends, HTTPException, Header
from typing import Optional
from token_manager import verify_token

async def get_user_from_token(token: str) -> str:
    """
    解析 token 获取 user_id
    """
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id

async def get_current_user(token: str = Depends(get_user_from_token)) -> str:
    """
    FastAPI 依赖项，获取当前登录用户 ID
    """
    return token

async def require_task_access(task_id: str, user_id: str = Depends(get_current_user)) -> str:
    """
    验证用户是否有权访问该任务
    """
    from task_manager import task_manager
    initial_state = await task_manager.get_initial_state(task_id)
    if not initial_state:
        raise HTTPException(status_code=404, detail="Task not found")
    if initial_state.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="You do not have access to this task")
    return user_id

async def require_admin(x_admin_token: Optional[str] = Header(None)):
    """
    管理员权限校验
    """
    admin_secret = os.getenv("ADMIN_SECRET_KEY")
    if x_admin_token != admin_secret:
        raise HTTPException(status_code=403, detail="Admin access required")
    return True