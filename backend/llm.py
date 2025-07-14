import os
import toml
from typing import List, Dict, Optional, Union
from openai import OpenAI, OpenAIError
import tiktoken
from mcp.server.fastmcp import FastMCP
from tenacity import retry,stop_after_attempt,wait_random_exponential,retry_if_exception_type

PROJECT_PATH = os.path.dirname(__file__)
class LLM:
    def __init__(self, model_type: str = "qwen", config_path=os.path.join(PROJECT_PATH,"../", "config","config.toml")):
        self.config = self._load_config(config_path)[model_type]
        self.model = self.config["model"]
        self.api_key = self.config.get("api_key")
        self.base_url = self.config.get("base_url")
        self.temperature = self.config.get("temperature")
        self.max_tokens = self.config.get("max_tokens")

        if model_type in ["openai", "qwen"]:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        else:
            raise ValueError(f"Unsupported LLM type: {model_type}")

        try:
            self.tokenizer = tiktoken.encoding_for_model(self.model)
        except Exception:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")

    def _load_config(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config file not found at {path}")
        return toml.load(path)

    def count_tokens(self, text: str) -> int:

        return len(self.tokenizer.encode(text))

    def _change_temperature(self, temperature: float):
        self.temperature = temperature

    def _change_max_tokens(self, max_tokens: int):
        self.max_tokens = max_tokens

    @retry(
        stop=stop_after_attempt(6),
        wait=wait_random_exponential(min=1, max=60),
        retry=retry_if_exception_type(
            (OpenAIError, Exception, ValueError)
        ),
    )
    async def ask(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict] = None
    ) -> str:

        try:
            total_input_tokens = sum(self.count_tokens(m['content']) for m in messages)
            print(f"[INFO] 输入 token 总数: {total_input_tokens}")

            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format=response_format
            )
            output_text = completion.choices[0].message.content
            output_tokens = self.count_tokens(output_text)
            print(f"[INFO] 输出 token 数量: {output_tokens}")
            return output_text
        except Exception as e:
            print(f"[ERROR] LLM 调用失败: {e}")
            return "抱歉，我现在无法处理您的请求。"