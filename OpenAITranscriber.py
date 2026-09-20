from opeanai import openai

class OpenAITransriber:
    def __init__(self, client: OpenAI | None = None, api_key: str | None = None) -> None:
        self.api_key = api_key
        self.client = client