import json
import os
import re

import anthropic
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

NOT_CONFIGURED_MESSAGE = "Add ANTHROPIC_API_KEY to .env to enable scoring"
SCORING_TIMEOUT_SECONDS = 30.0
TAILORING_TIMEOUT_SECONDS = 60.0

RESUME_CHAR_LIMIT = 2000
JD_CHAR_LIMIT = 1500
SCORING_MAX_TOKENS = 300
TAILORING_MAX_TOKENS = 3000

SCORING_PROMPT_TEMPLATE = """Score this resume against this job (0-100).
Return JSON only:
{{
  "score": 75,
  "matched": ["Java", "Spring Boot"],
  "missing": ["Kotlin", "GraphQL"],
  "reason": "One sentence summary",
  "recommend": "One sentence recommendation"
}}

RESUME (first {resume_limit} chars):
{resume_text}

JOB (first {jd_limit} chars):
{jd_text}"""


class ClaudeNotConfiguredError(Exception):
    pass


class ClaudeRequestError(Exception):
    pass


class ClaudeTimeoutError(Exception):
    pass


class ClaudeService:
    def __init__(self) -> None:
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        self.scoring_model = os.getenv("SCORING_MODEL", "claude-haiku-4-5-20251001")
        self._client: Anthropic | None = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic(api_key=self.api_key)
        return self._client

    def score_resume_against_jd(self, resume_text: str, jd_text: str, title: str) -> dict:
        prompt = SCORING_PROMPT_TEMPLATE.format(
            resume_limit=RESUME_CHAR_LIMIT,
            jd_limit=JD_CHAR_LIMIT,
            resume_text=resume_text[:RESUME_CHAR_LIMIT],
            jd_text=jd_text[:JD_CHAR_LIMIT],
        )
        text = self._send(
            model=self.scoring_model,
            max_tokens=SCORING_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
            timeout=SCORING_TIMEOUT_SECONDS,
        )
        return _parse_json_response(text)

    def tailor_resume_text(self, system_prompt: str, user_prompt: str) -> str:
        return self._send(
            model=self.model,
            max_tokens=TAILORING_MAX_TOKENS,
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
            timeout=TAILORING_TIMEOUT_SECONDS,
        )

    def _send(
        self,
        model: str,
        max_tokens: int,
        messages: list[dict],
        timeout: float,
        system: str | None = None,
    ) -> str:
        if not self.is_configured():
            raise ClaudeNotConfiguredError(NOT_CONFIGURED_MESSAGE)

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "timeout": timeout,
        }
        if system is not None:
            kwargs["system"] = system

        try:
            response = self._get_client().messages.create(**kwargs)
        except anthropic.APITimeoutError as error:
            raise ClaudeTimeoutError(f"Request timed out after {int(timeout)} seconds.") from error
        except anthropic.APIStatusError as error:
            raise ClaudeRequestError(f"Claude API error: {error}") from error
        except anthropic.APIConnectionError as error:
            raise ClaudeRequestError(f"Could not reach Claude: {error}") from error

        return "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )


def _parse_json_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
        cleaned = cleaned.removesuffix("```").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise ClaudeRequestError("Claude returned an unexpected response.") from error
