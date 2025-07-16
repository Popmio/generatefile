# # task_manager.py
#
# import asyncio
# from typing import Dict, List, Optional, AsyncGenerator
# from collections import defaultdict
# import logging
#
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)
#
# class TaskManager:
#     def __init__(self):
#         self.lock = asyncio.Lock()
#         self.tasks: Dict[str, dict] = {}
#         self.sse_queues: Dict[str, List[asyncio.Queue]] = defaultdict(list)
#         self.last_event_per_task: Dict[str, dict] = {}
#
#     async def create_task(self, task_id: str, user_id: str, input_data: dict, agent_types: list):
#         async with self.lock:
#             self.tasks[task_id] = {
#                 "user_id": user_id,
#                 "input_data": input_data,
#                 "agents": {agent_type: {"status": "pending", "file_url": ""} for agent_type in agent_types},
#                 "completed": False
#             }
#
#     async def update_subtask_status(self, task_id: str, agent_type: str, status: str, file_url: str = None):
#         async with self.lock:
#             task = self.tasks.get(task_id)
#             if not task:
#                 return False
#             task["agents"][agent_type]["status"] = status
#             if file_url:
#                 task["agents"][agent_type]["file_url"] = file_url
#
#
#             is_completed = self.is_task_completed(task_id)
#             event_data = {
#                 "task_id": task_id,
#                 "status": task["agents"],
#                 "completed": is_completed
#             }
#             self.last_event_per_task[task_id] = event_data
#
#             asyncio.create_task(self.broadcast_event(task_id))
#
#             return True
#
#     async def broadcast_event(self, task_id: str):
#         queues = self.sse_queues.get(task_id, [])
#         if not queues:
#             return
#
#         task = self.tasks.get(task_id)
#         if not task:
#             return
#
#         event_data = self.last_event_per_task.get(task_id)
#         if not event_data:
#             event_data = {
#                 "task_id": task_id,
#                 "status": task["agents"],
#                 "completed": self.is_task_completed(task_id)
#             }
#
#         for queue in queues:
#             await queue.put(event_data)
#         if event_data["completed"] == True:
#             for queue in queues:
#                 await queue.put(None)
#
#
#     def is_task_completed(self, task_id: str) -> bool:
#         task = self.tasks.get(task_id)
#         if not task:
#             return False
#         return all(agent["status"] == "completed" for agent in task["agents"].values())
#
#     async def get_initial_state(self, task_id: str):
#         task = self.tasks.get(task_id)
#         if not task:
#             return None
#         return self.last_event_per_task.get(task_id) or {
#             "task_id": task_id,
#             "status": task["agents"],
#             "completed": self.is_task_completed(task_id)
#         }
#
#     # async def listen_for_events(self, task_id: str) -> AsyncGenerator[dict, None]:
#     #     queue = asyncio.Queue()
#     #     self.sse_queues[task_id].append(queue)
#     #
#     #     initial_state = await self.get_initial_state(task_id)
#     #     if initial_state:
#     #         yield initial_state
#     #
#     #     try:
#     #         while True:
#     #             try:
#     #                 event = await queue.get()
#     #                 if event is None:
#     #                     logger.info(f"SSE connection for {task_id} closed by server.")
#     #                     break
#     #                 yield event
#     #             except asyncio.CancelledError:
#     #                 logger.info(f"SSE connection for {task_id} cancelled (client disconnected).")
#     #                 break
#     #             except Exception as e:
#     #                 logger.error(f"Error in SSE stream for {task_id}: {e}")
#     #                 break
#     #     finally:
#     #         if task_id in self.sse_queues and queue in self.sse_queues[task_id]:
#     #             self.sse_queues[task_id].remove(queue)
#
#         # await self.cleanup_task(task_id)
#     async def listen_for_events(self, task_id: str) -> AsyncGenerator[dict, None]:
#
#         if task_id not in self.sse_queues:
#             self.sse_queues[task_id] = []
#
#         queue = asyncio.Queue()
#         self.sse_queues[task_id].append(queue)
#
#         initial_state = await self.get_initial_state(task_id)
#         if initial_state:
#             yield initial_state
#
#         try:
#             while True:
#                 try:
#                     event = await queue.get()
#                     if event is None:
#                         logger.info(f"SSE connection for {task_id} closed by server.")
#                         break
#                     yield event
#                 except asyncio.CancelledError:
#                     logger.info(f"SSE connection for {task_id} cancelled (client disconnected).")
#                     break
#                 except Exception as e:
#                     logger.error(f"Error in SSE stream for {task_id}: {e}")
#                     break
#         finally:
#             if task_id in self.sse_queues and queue in self.sse_queues[task_id]:
#                 self.sse_queues[task_id].remove(queue)
#
#
#     async def cleanup_task(self, task_id: str):
#         async with self.lock:
#             if task_id in self.tasks:
#                 del self.tasks[task_id]
#
#             if task_id in self.sse_queues:
#                 queues = self.sse_queues.pop(task_id)
#                 for queue in queues:
#                     try:
#                         queue.put_nowait(None)
#                     except asyncio.QueueFull:
#                         pass
#                     except Exception as e:
#                         logger.warning(f"Error putting end signal into queue: {e}")
#
#
#             if task_id in self.last_event_per_task:
#                 del self.last_event_per_task[task_id]
#
#             logger.info(f"Task {task_id} has been cleaned up.")
#
#     def get_user_tasks(self, user_id: str) -> List[dict]:
#
#         result = []
#         for task_id, task in self.tasks.items():
#             if task["user_id"] == user_id:
#                 result.append({
#                     "task_id": task_id,
#                     "status": task["agents"],
#                     "completed": self.is_task_completed(task_id),
#                     "input_data": task["input_data"]
#                 })
#         return result
#
#
#     # async def async_cleanup_task(self, task_id: str):
#     #     await asyncio.get_event_loop().run_in_executor(None, self.cleanup_task, task_id)
#     #
#
#
# task_manager = TaskManager()
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
        self.completed_flags: Dict[str, bool] = {}  # 记录任务是否完成，避免重复计算

    async def create_task(self, task_id: str, user_id: str, input_data: dict, agent_types: list):
        async with self.lock:
            self.tasks[task_id] = {
                "user_id": user_id,
                "input_data": input_data,
                "agents": {agent_type: {"status": "pending", "file_url": ""} for agent_type in agent_types},
                "completed": False  # 初始状态为未完成
            }
            self.completed_flags[task_id] = False  # 初始化完成标志

    async def update_subtask_status(self, task_id: str, agent_type: str, status: str, file_url: str = None):
        async with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                logger.error(f"Task {task_id} not found during status update.")
                return False

            # 更新任务的子任务状态
            task["agents"][agent_type]["status"] = status
            if file_url:
                task["agents"][agent_type]["file_url"] = file_url

            # 如果任务已完成，更新任务完成状态
            if status == "completed" and self.is_task_completed(task_id):
                task["completed"] = True
                self.completed_flags[task_id] = True  # 更新完成标志

            # 创建事件数据
            event_data = {
                "task_id": task_id,
                "status": task["agents"],
                "completed": task["completed"]
            }
            self.last_event_per_task[task_id] = event_data

            # 触发广播事件
            asyncio.create_task(self.broadcast_event(task_id))

            return True

    async def broadcast_event(self, task_id: str):

        queues = self.sse_queues.get(task_id, [])
        if not queues:
            # 如果没有任何监听的客户端，直接返回
            return

        task = self.tasks.get(task_id)
        if not task:
            return

        event_data = self.last_event_per_task.get(task_id) or {
            "task_id": task_id,
            "status": task["agents"],
            "completed": task["completed"]
        }

        # 广播事件给所有连接的客户端
        for queue in queues:
            await queue.put(event_data)

        # 如果任务完成后，所有连接的客户端都需要接收到 None，作为关闭信号
        if task["completed"]:
            for queue in queues:
                await queue.put(None)  # 任务完成后通知所有连接关闭

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
            "completed": task["completed"]
        }

    async def listen_for_events(self, task_id: str) -> AsyncGenerator[dict, None]:
        if task_id not in self.sse_queues:
            self.sse_queues[task_id] = []

        queue = asyncio.Queue()
        self.sse_queues[task_id].append(queue)

        # 如果任务已经完成，直接返回最终状态
        initial_state = await self.get_initial_state(task_id)
        if initial_state:
            yield initial_state

        try:
            while True:
                event = await queue.get()
                if event is None:
                    logger.info(f"SSE connection for {task_id} closed.")
                    break
                yield event
        except asyncio.CancelledError:
            logger.info(f"SSE connection for {task_id} cancelled (client disconnected).")
        except Exception as e:
            logger.error(f"Error in SSE stream for {task_id}: {e}")
        finally:
            if queue in self.sse_queues[task_id]:
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

            if task_id in self.completed_flags:
                del self.completed_flags[task_id]

            logger.info(f"Task {task_id} has been cleaned up.")

    def get_user_tasks(self, user_id: str) -> List[dict]:
        result = []
        for task_id, task in self.tasks.items():
            if task["user_id"] == user_id:
                result.append({
                    "task_id": task_id,
                    "status": task["agents"],
                    "completed": task["completed"],
                    "input_data": task["input_data"]
                })
        return result

task_manager = TaskManager()
