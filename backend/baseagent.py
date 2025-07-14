import asyncio
from abc import abstractmethod
from fastapi import HTTPException
from typing import List, Dict, Optional, Callable
from backend.llm import LLM
import time
import logging
from pydantic import BaseModel, Field
import httpx
# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BaseAgent:
    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: str,
        memory_size: int = 5,
        model_type: str = "openai",
        enable_tool: bool = False
    ):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.memory_size = memory_size
        self.enable_tool = enable_tool
        self.llm = LLM(model_type=model_type)
        self.memory: List[Dict[str, str]] = []
        self.tools: Dict[str, Callable] = {}
        self.last_response_time = 0.0

    def get_system_message(self) -> dict:
        return {"role": "system", "content": self.system_prompt}

    def add_to_memory(self, message: dict):
        self.memory.append(message)
        if len(self.memory) > self.memory_size:
            self.memory.pop(0)

    def clear_memory(self):
        self.memory.clear()

    def build_messages(self, user_input: str) -> List[Dict[str, str]]:
        messages = [self.get_system_message()]
        messages.extend(self.memory)
        messages.append({"role": "user", "content": user_input})
        return messages

    def should_respond(self, user_input: str) -> bool:
        """智能判断是否需要响应"""
        if not user_input.strip():
            logger.info("空输入，跳过响应")
            return False
        if len(user_input) > 1000:
            logger.warning("输入内容过长，可能需过滤")
            return True
        return True

    def register_tool(self, name: str, func: Callable):
        """注册一个工具函数"""
        self.tools[name] = func

    def call_tool(self, tool_name: str, *args, **kwargs):
        """调用已注册的工具"""
        if tool_name not in self.tools:
            logger.error(f"未注册的工具: {tool_name}")
            return None
        return self.tools[tool_name](*args, **kwargs)

    async def ask(self, user_input: str) -> str:
        """主响应方法"""
        start_time = time.time()
        logger.info(f"{self.name} 接收到用户输入: {user_input[:50]}...")

        if not self.should_respond(user_input):
            return ""

        messages = self.build_messages(user_input)

        response = await self.llm.ask(messages)

        self.add_to_memory({"role": "user", "content": user_input})
        self.add_to_memory({"role": "assistant", "content": response})

        elapsed = time.time() - start_time
        self.last_response_time = elapsed
        logger.info(f"{self.name} 响应完成，耗时: {elapsed:.2f}s")

        return response

    async def ask_multi_agent(self, urls: List[str], data):

        for url in urls:
            async with httpx.AsyncClient(timeout=60) as client:
                try:
                    response = await client.post(
                        url=url,
                        json=data.model_dump(),
                    )

                except httpx.RequestError as exc:
                    logger.error(f"Network error: Failed to reach remote service: {exc}")
                    raise HTTPException(
                        status_code=503,
                        detail=f"Failed to reach remote service: {exc}"
                    )
        return {"status": "ok"}