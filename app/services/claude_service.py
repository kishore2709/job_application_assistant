import json
import os
import re

import anthropic
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

NOT_CONFIGURED_MESSAGE = "Add ANTHROPIC_API_KEY to .env to enable scoring"
SCORING_TIMEOUT_SECONDS = 30.0

SCORING_SYSTEM_PROMPT = (
    "You are an expert technical recruiter. Compare a candidate's resume "
    "against a job description and judge how strong a fit the candidate is. "
    "Respond with ONLY a single valid JSON object — no markdown code fences, "
    "no commentary before or after it — matching exactly this shape: "
    '{"score": <integer 0-100>, "matched_keywords": [<string>, ...], '
    '"missing_keywords": [<string>, ...], "reasoning": <string>, '
    '"recommendation": <string>}'
)


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
        self._client: Anthropic | None = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic(api_key=self.api_key)
        return self._client

    def score_resume_against_jd(self, resume_text: str, jd_text: str, title: str) -> dict:
        if not self.is_configured():
            raise ClaudeNotConfiguredError(NOT_CONFIGURED_MESSAGE)

        user_message = (
            f"Job Title: {title}\n\n"
            f"Job Description:\n{jd_text}\n\n"
            f"Candidate Resume:\n{resume_text}\n\n"
            "Score this candidate's fit for the role and respond with the JSON object only."
        )

        try:
            response = self._get_client().messages.create(
                model=self.model,
                max_tokens=1024,
                system=SCORING_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
                timeout=SCORING_TIMEOUT_SECONDS,
            )
        except anthropic.APITimeoutError as error:
            raise ClaudeTimeoutError(
                f"Scoring timed out after {int(SCORING_TIMEOUT_SECONDS)} seconds."
            ) from error
        except anthropic.APIStatusError as error:
            raise ClaudeRequestError(f"Claude API error: {error}") from error
        except anthropic.APIConnectionError as error:
            raise ClaudeRequestError(f"Could not reach Claude: {error}") from error

        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        return _parse_json_response(text)


def _parse_json_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
        cleaned = cleaned.removesuffix("```").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise ClaudeRequestError("Claude returned an unexpected response.") from error
