import os
import toml
import asyncio
import logging
from typing import List, Dict, Optional, Union, Any, Generator, AsyncGenerator, Coroutine

from openai import OpenAI, AsyncOpenAI, OpenAIError
import tiktoken
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type

from jinja2 import Template
from backend.types import ToolChoice

PROJECT_PATH = os.path.dirname(__file__)

class LLM:
    def __init__(self, model_type: str = "openai", config_path: str = os.path.join(PROJECT_PATH, "config.toml")):
        self.model_type = model_type
        config = self._load_config(config_path)

        if model_type not in config:
            raise ValueError(f"[配置错误] 模型类型 '{model_type}' 未在配置文件中定义")

        self.global_config = config.get("global", {})
        self.config = config[model_type]

        self.api_key = self.config.get("api_key", self.global_config.get("api_key"))
        self.base_url = self.config.get("base_url", self.global_config.get("base_url"))
        self.model = self.config["model"]
        self.temperature = self.config.get("temperature", 0.7)
        self.max_tokens = self.config.get("max_tokens", 1024)
        self.token_limit = self.config.get("token_limit", 8192)
        self.stream = self.config.get("stream", False)
        self.debug = self.config.get("debug", True)

        if not self.api_key or not self.model:
            raise ValueError("[配置错误] 缺少 'api_key' 或 'model'")

        self._init_client_by_model_type()

        try:
            self.tokenizer = tiktoken.encoding_for_model(self.model)
        except Exception:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")

        self._init_logger()
        self.tools = None
        self.tool_choice = None

    def _init_client_by_model_type(self):
        if self.model_type in ["openai", "deepseek"]:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            self.async_client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        elif self.model_type == "qwen":
            from qwen_api import ChatQwen, AsyncChatQwen
            self.client = ChatQwen(api_key=self.api_key, base_url=self.base_url)
            self.async_client = AsyncChatQwen(api_key=self.api_key, base_url=self.base_url)
        else:
            raise ValueError(f"[初始化错误] 不支持的模型类型: {self.model_type}")

    def _init_logger(self):
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('[%(levelname)s] %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG if self.debug else logging.INFO)

    def _load_config(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"配置文件不存在: {path}")
        return toml.load(path)

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text))

    def _log_token_usage(self, messages: List[Dict[str, str]], output: Optional[str] = None):
        input_tokens = sum(self.count_tokens(m["content"]) for m in messages)
        self.logger.debug(f"[Token] 输入 tokens: {input_tokens}")
        if output:
            output_tokens = self.count_tokens(output)
            self.logger.debug(f"[Token] 输出 tokens: {output_tokens}")

    def _check_token_limit(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        total_input = sum(self.count_tokens(m["content"]) for m in messages)
        if total_input + self.max_tokens > self.token_limit:
            self.logger.warning(f"Token 超出限制，将自动截断: 输入 {total_input} + 输出 {self.max_tokens} > 限制 {self.token_limit}")
            while messages and total_input + self.max_tokens > self.token_limit:
                removed = messages.pop(0)
                total_input -= self.count_tokens(removed["content"])
        return messages

    def set_temperature(self, temperature: float):
        self.temperature = temperature

    def set_max_tokens(self, max_tokens: int):
        self.max_tokens = max_tokens

    def enable_function_calling(self, tools: List[Dict], tool_choice: Optional[str] = None):
        self.tools = tools
        if tool_choice:
            self.tool_choice = {"function": {"name": tool_choice}}
        else:
            self.tool_choice = "auto"
        self.logger.debug(f"[FunctionCalling] 工具数量: {len(tools)}, 选择策略: {self.tool_choice}")

    def render_prompt(self, template_str: str, variables: Dict[str, Any]) -> str:
        template = Template(template_str)
        return template.render(**variables)

    def ask_sync(self, messages: List[Dict[str, str]], timeout: Optional[int] = None, **kwargs) -> Dict[str, Any]:
        try:
            messages = self._check_token_limit(messages)
            self._log_token_usage(messages)

            if self.model_type in ["openai", "deepseek"]:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    stream=self.stream,
                    tools=self.tools,
                    tool_choice=self.tool_choice,
                    timeout=timeout,
                    **kwargs
                )
                output = "".join(chunk.choices[0].delta.content or "" for chunk in response) if self.stream else response.choices[0].message.content
            else:
                response = self.client.chat(messages=messages, model=self.model)
                output = response["output"]

            self._log_token_usage(messages, output)
            return {
                "text": output,
                "input_tokens": sum(self.count_tokens(m["content"]) for m in messages),
                "output_tokens": self.count_tokens(output),
                "raw": response
            }

        except Exception as e:
            self.logger.error(f"[Sync ERROR] {e}")
            return {"text": "同步调用失败", "error": str(e)}

    @retry(stop=stop_after_attempt(5), wait=wait_random_exponential(min=1, max=20), retry=retry_if_exception_type(Exception))
    async def ask(self, messages: List[Dict[str, str]], timeout: Optional[int] = None, **kwargs) -> Dict[str, Any]:
        try:
            messages = self._check_token_limit(messages)
            self._log_token_usage(messages)

            if self.model_type in ["openai", "deepseek"]:
                response = await self.async_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    stream=self.stream,
                    tools=self.tools,
                    tool_choice=self.tool_choice,
                    timeout=timeout,
                    **kwargs
                )
                output = "".join(chunk.choices[0].delta.content or "" async for chunk in response) if self.stream else response.choices[0].message.content
            else:
                response = await self.async_client.chat(messages=messages, model=self.model)
                output = response["output"]

            self._log_token_usage(messages, output)
            return {
                "text": output,
                "input_tokens": sum(self.count_tokens(m["content"]) for m in messages),
                "output_tokens": self.count_tokens(output),
                "raw": response
            }

        except Exception as e:
            self.logger.error(f"[Async ERROR] {e}")
            return {"text": "异步调用失败", "error": str(e)}

    def call(self, *args, **kwargs) -> Union[Dict[str, Any], Coroutine[Any, Any, Dict[str, Any]]]:
        try:
            asyncio.get_running_loop()
            return self.ask(*args, **kwargs)
        except RuntimeError:
            return self.ask_sync(*args, **kwargs)

    def stream_sync(self, messages: List[Dict[str, str]]) -> Generator[str, None, None]:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True
            )
            for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as e:
            yield f"[Stream ERROR] {e}"

    async def stream_async(self, messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        try:
            response = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True
            )
            async for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as e:
            yield f"[Async Stream ERROR] {e}"

    def test_prompt(self, prompt: str, role: str = "user", max_tokens: Optional[int] = None, template: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        if template:
            prompt = self.render_prompt(template, {"input": prompt})
        messages = [{"role": role, "content": prompt}]
        if max_tokens:
            self.set_max_tokens(max_tokens)
        return self.ask_sync(messages, **kwargs)
