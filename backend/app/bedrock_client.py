from openai import AsyncOpenAI, OpenAIError

from app.config import get_settings


class BedrockClientError(Exception):
    pass


DEFAULT_TIMEOUT_SECONDS = 30


class BedrockClient:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        settings = get_settings()
        self._client = AsyncOpenAI(base_url=settings.bedrock_base_url, api_key=settings.bedrock_api_key, timeout=timeout)
        self._model = settings.bedrock_model

    async def chat(self, messages: list[dict], temperature: float = 0.0) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
            )
        except OpenAIError as exc:
            raise BedrockClientError(f"Bedrock request failed: {exc}") from exc

        if not response.choices or not response.choices[0].message.content:
            raise BedrockClientError("Bedrock returned an empty response")

        return response.choices[0].message.content
