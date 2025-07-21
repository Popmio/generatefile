from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from pydantic import BaseModel, Field
import logging
import asyncio

from backend.llm import LLM


class BaseAgent(BaseModel, ABC):
    """
    通用 LLM 智能体基类：支持 Prompt 构建、LLM 同/异步调用、工具调用、上下文记忆等功能。
    子类需实现 build_prompt 与 observe 方法。
    """

    model_type: str = "openai"
    config_path: str = "config/config.toml"
    stream: bool = False
    debug: bool = True

    memory: List[Dict[str, str]] = Field(default_factory=list)
    llm: Optional[LLM] = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.llm = LLM(model_type=self.model_type, config_path=self.config_path)
        self.llm.stream = self.stream
        self.llm.debug = self.debug

        self.logger = logging.getLogger(self.__class__.__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG if self.debug else logging.INFO)

    @abstractmethod
    def build_prompt(self, input_data: Any) -> List[Dict[str, str]]:
        pass

    @abstractmethod
    def observe(self, output: str, raw_response: Dict[str, Any]) -> None:
        pass

    def postprocess(self, output: str) -> str:
        return output

    def enable_tools(self, tools: List[Dict], tool_choice: Optional[str] = None):
        self.llm.enable_function_calling(tools, tool_choice)

    def remember(self, role: str, content: str):
        self.memory.append({"role": role, "content": content})

    def clear_memory(self):
        self.memory.clear()

    def run(self, input_data: Any, stream: Optional[bool] = None, **kwargs) -> Dict[str, Any]:
        messages = self.build_prompt(input_data)
        self.memory.extend(messages)
        use_stream = stream if stream is not None else self.stream

        if use_stream:
            output = self._run_stream(messages)
            return {"text": output}
        else:
            response = self.llm.ask_sync(messages, **kwargs)
            output = response.get("text", "")
            output = self.postprocess(output)
            self.observe(output, response)
            return response

    def _run_stream(self, messages: List[Dict[str, str]]) -> str:
        output = ""
        for chunk in self.llm.stream_sync(messages):
            print(chunk, end="", flush=True)
            output += chunk
        output = self.postprocess(output)
        self.observe(output, {"text": output})
        return output

    async def arun(self, input_data: Any, **kwargs) -> Dict[str, Any]:
        messages = self.build_prompt(input_data)
        self.memory.extend(messages)
        response = await self.llm.ask(messages, **kwargs)
        output = response.get("text", "")
        output = self.postprocess(output)
        self.observe(output, response)
        return response

    async def stream_async(self, input_data: Any) -> AsyncGenerator[str, None]:
        messages = self.build_prompt(input_data)
        self.memory.extend(messages)
        async for chunk in self.llm.stream_async(messages):
            yield chunk

    def render_prompt(self, template_str: str, variables: Dict[str, Any]) -> str:

        return self.llm.render_prompt(template_str, variables)

    def __enter__(self):
        self.logger.debug("Agent context entered.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.debug("Agent context exited.")
        self.clear_memory()

