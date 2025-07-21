from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from enum import Enum

class StartTaskRequest(BaseModel):
    user_id: str
    input_data: Dict[str, Any]
    agent_types: List[str]

class AgentState(str, Enum):
    pending = "pending",
    processing = "running",
    completed = "completed",
    failed = "failed"

class CallbackData(BaseModel):
    subtask_id: str
    status: AgentState
    file_url: Optional[str] = None

class ToolChoice(str, Enum):

    NONE = "none",
    Auto = "auto",
    REQUIRED = "required"

if __name__ == "__main__":
    start_task = StartTaskRequest(user_id="user1", input_data={"1":2},agent_types=["agent1", "agent2"])
    print(start_task.model_dump_json())