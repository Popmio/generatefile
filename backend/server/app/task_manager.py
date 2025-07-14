# task_manager.py

import asyncio
from typing import Dict, List, Optional, AsyncGenerator
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaskManager:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.tasks: Dict[str, dict] = {}
        self.sse_queues: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        self.last_event_per_task: Dict[str, dict] = {}

    async def create_task(self, task_id: str, user_id: str, input_data: dict, agent_types: list):
        async with self.lock:
            self.tasks[task_id] = {
                "user_id": user_id,
                "input_data": input_data,
                "agents": {agent_type: {"status": "pending", "file_url": ""} for agent_type in agent_types},
                "completed": False
            }

    async def update_subtask_status(self, task_id: str, agent_type: str, status: str, file_url: str = None):
        async with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return False
            task["agents"][agent_type]["status"] = status
            if file_url:
                task["agents"][agent_type]["file_url"] = file_url


            is_completed = self.is_task_completed(task_id)
            event_data = {
                "task_id": task_id,
                "status": task["agents"],
                "completed": is_completed
            }
            self.last_event_per_task[task_id] = event_data

            asyncio.create_task(self.broadcast_event(task_id))

            return True

    async def broadcast_event(self, task_id: str):
        queues = self.sse_queues.get(task_id, [])
        if not queues:
            return

        task = self.tasks.get(task_id)
        if not task:
            return

        event_data = self.last_event_per_task.get(task_id)
        if not event_data:
            event_data = {
                "task_id": task_id,
                "status": task["agents"],
                "completed": self.is_task_completed(task_id)
            }

        for queue in queues:
            await queue.put(event_data)
        if event_data["completed"] == True:
            for queue in queues:
                await queue.put(None)


    def is_task_completed(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if not task:
            return False
        return all(agent["status"] == "completed" for agent in task["agents"].values())

    async def get_initial_state(self, task_id: str):
        task = self.tasks.get(task_id)
        if not task:
            return None
        return self.last_event_per_task.get(task_id) or {
            "task_id": task_id,
            "status": task["agents"],
            "completed": self.is_task_completed(task_id)
        }

    # async def listen_for_events(self, task_id: str) -> AsyncGenerator[dict, None]:
    #     queue = asyncio.Queue()
    #     self.sse_queues[task_id].append(queue)
    #
    #     initial_state = await self.get_initial_state(task_id)
    #     if initial_state:
    #         yield initial_state
    #
    #     try:
    #         while True:
    #             try:
    #                 event = await queue.get()
    #                 if event is None:
    #                     logger.info(f"SSE connection for {task_id} closed by server.")
    #                     break
    #                 yield event
    #             except asyncio.CancelledError:
    #                 logger.info(f"SSE connection for {task_id} cancelled (client disconnected).")
    #                 break
    #             except Exception as e:
    #                 logger.error(f"Error in SSE stream for {task_id}: {e}")
    #                 break
    #     finally:
    #         if task_id in self.sse_queues and queue in self.sse_queues[task_id]:
    #             self.sse_queues[task_id].remove(queue)

        # await self.cleanup_task(task_id)
    async def listen_for_events(self, task_id: str) -> AsyncGenerator[dict, None]:

        if task_id not in self.sse_queues:
            self.sse_queues[task_id] = []

        queue = asyncio.Queue()
        self.sse_queues[task_id].append(queue)

        initial_state = await self.get_initial_state(task_id)
        if initial_state:
            yield initial_state

        try:
            while True:
                try:
                    event = await queue.get()
                    if event is None:
                        logger.info(f"SSE connection for {task_id} closed by server.")
                        break
                    yield event
                except asyncio.CancelledError:
                    logger.info(f"SSE connection for {task_id} cancelled (client disconnected).")
                    break
                except Exception as e:
                    logger.error(f"Error in SSE stream for {task_id}: {e}")
                    break
        finally:
            if task_id in self.sse_queues and queue in self.sse_queues[task_id]:
                self.sse_queues[task_id].remove(queue)


    async def cleanup_task(self, task_id: str):
        async with self.lock:
            if task_id in self.tasks:
                del self.tasks[task_id]

            if task_id in self.sse_queues:
                queues = self.sse_queues.pop(task_id)
                for queue in queues:
                    try:
                        queue.put_nowait(None)
                    except asyncio.QueueFull:
                        pass
                    except Exception as e:
                        logger.warning(f"Error putting end signal into queue: {e}")


            if task_id in self.last_event_per_task:
                del self.last_event_per_task[task_id]

            logger.info(f"Task {task_id} has been cleaned up.")

    def get_user_tasks(self, user_id: str) -> List[dict]:

        result = []
        for task_id, task in self.tasks.items():
            if task["user_id"] == user_id:
                result.append({
                    "task_id": task_id,
                    "status": task["agents"],
                    "completed": self.is_task_completed(task_id),
                    "input_data": task["input_data"]
                })
        return result


    # async def async_cleanup_task(self, task_id: str):
    #     await asyncio.get_event_loop().run_in_executor(None, self.cleanup_task, task_id)
    #


task_manager = TaskManager()