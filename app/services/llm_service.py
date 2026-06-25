import json
import os
import re
import time

import requests
from dotenv import load_dotenv

from app.db.repositories import ProfileRepository

load_dotenv()

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"
PROVIDER_GOOGLE = "google"
PROVIDER_OLLAMA = "ollama"

RESUME_CHAR_LIMIT = 2000
JD_CHAR_LIMIT = 1500
SCORING_MAX_TOKENS = 300
TAILORING_MAX_TOKENS = 3000
SCORING_TIMEOUT_SECONDS = 30.0
TAILORING_TIMEOUT_SECONDS = 60.0
RESUME_PROMPT_CHAR_BUDGET = 4000
JD_PROMPT_LIMIT = 2000

OLLAMA_NOT_RUNNING_MESSAGE = (
    "Ollama not running.\nStart with: ollama serve\nPull model:  ollama pull llama3.2"
)

# Approximate, documented assumptions based on rough public per-token
# pricing at typical resume/JD token counts — not live billing rates.
# Good enough for a monthly sense-check, not exact cost accounting.
SCORING_COST_PER_CALL = {
    "claude-haiku-4-5-20251001": 0.002,
    "gpt-4o-mini": 0.0003,
    "gemini-1.5-flash": 0.0,
}
TAILORING_COST_PER_CALL = {
    "claude-sonnet-4-6": 0.03,
    "gpt-4o": 0.02,
    "gemini-1.5-pro": 0.015,
}


def scoring_cost_for_model(model: str) -> float:
    return SCORING_COST_PER_CALL.get(model, 0.0)


def tailoring_cost_for_model(model: str) -> float:
    return TAILORING_COST_PER_CALL.get(model, 0.0)


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

SYSTEM_PROMPT = """You are helping a job seeker tailor their resume
for a specific job. Your goal is to highlight
relevant experience without changing facts.

STRICT RULES — NEVER VIOLATE:
- Keep resume headline EXACTLY as in original
- Do not add domain keywords to headline
  (no Payments, Banking, Healthcare, AI etc)
- Do not change Lead to Senior or vice versa
- Do not change any job titles in experience
- Do not touch header section at all:
  name, headline, contact info = completely untouched
- Only tailor these sections:
  summary bullets, skills section,
  experience bullet points
- Reword and reprioritize existing content only
- Never invent employers, dates, tools, or experience
- Never add technologies not in the original resume
- Do not add metrics where original had none

MAKE IT SOUND HUMAN — NOT AI GENERATED:
- Vary sentence structure across bullets
- Not every bullet should start with a power verb
- Preserve the candidate's natural writing voice
- Keep some informal professional phrasing
- Slight variation in style is good
- Do not make every line sound ATS-optimized
- Keep the same level of formality as original
- Avoid repetitive patterns across bullets
- Do not over-polish — humans write with variation

FORMATTING:
- Use original resume DOCX as template
- Replace only text content
- Keep all fonts, colors, bold, styles exactly
- Never change paragraph count or structure

RESPONSE FORMAT (required so edits can be mapped back into the
original document programmatically):
- The resume below is provided as a numbered list, one line per paragraph
- Return the SAME number of lines, in the SAME order, each line prefixed
  with its original number and a period, e.g. "1. ", "2. ", ...
- For header lines (name, headline, contact info — see line range below)
  return that line's text completely unchanged
- Do not merge, split, add, or remove lines
- Return only the numbered list — no explanations, no markdown"""

USER_PROMPT_TEMPLATE = """Job Title: {job_title}

Job Description:
{jd_text}

Current Resume (numbered lines; lines 1-{header_line_count} are the header —
name/headline/contact info — return those lines completely unchanged):
{resume_text}

Target Role Description:
{role_description}

Return the tailored resume as the same numbered list of lines.
No explanations, no markdown, just the numbered lines."""

NUMBERED_LINE_PATTERN = re.compile(r"^\s*(\d+)\.\s?(.*)$")


class LLMNotConfiguredError(Exception):
    pass


class LLMTimeoutError(Exception):
    pass


class LLMRequestError(Exception):
    pass


class LLMService:
    def __init__(self, profile=None) -> None:
        self.profile = profile or ProfileRepository().get()

    def is_configured(self, purpose: str) -> bool:
        provider, _model = self._resolve(purpose)
        if provider == PROVIDER_OLLAMA:
            return is_ollama_running(self.profile.ollama_base_url)
        return bool(self._get_key(provider))

    def score(self, resume_text: str, jd_text: str, title: str) -> dict:
        provider, model = self._resolve("scoring")
        prompt = SCORING_PROMPT_TEMPLATE.format(
            resume_limit=RESUME_CHAR_LIMIT,
            jd_limit=JD_CHAR_LIMIT,
            resume_text=resume_text[:RESUME_CHAR_LIMIT],
            jd_text=jd_text[:JD_CHAR_LIMIT],
        )
        text = self._call(
            provider, model, system=None, user=prompt,
            max_tokens=SCORING_MAX_TOKENS, timeout=SCORING_TIMEOUT_SECONDS,
        )
        return _parse_json_response(text)

    def tailor(
        self,
        resume_text: str,
        jd_text: str,
        title: str,
        role_description: str,
        profile,
        header_line_count: int,
    ) -> dict[int, str]:
        provider, model = self._resolve("tailoring")
        user_prompt = USER_PROMPT_TEMPLATE.format(
            job_title=title,
            jd_text=jd_text[:JD_PROMPT_LIMIT],
            resume_text=resume_text,
            role_description=role_description or "",
            header_line_count=header_line_count,
        )
        text = self._call(
            provider, model, system=SYSTEM_PROMPT, user=user_prompt,
            max_tokens=TAILORING_MAX_TOKENS, timeout=TAILORING_TIMEOUT_SECONDS,
        )
        return _parse_numbered_response(text)

    def _resolve(self, purpose: str) -> tuple[str, str]:
        if purpose == "scoring":
            return self.profile.scoring_provider, self.profile.scoring_model
        if purpose == "tailoring":
            return self.profile.tailoring_provider, self.profile.tailoring_model
        raise ValueError(f"Unknown purpose: {purpose}")

    def _call(self, provider, model, system, user, max_tokens, timeout) -> str:
        if provider == PROVIDER_ANTHROPIC:
            return self._anthropic(model, system, user, max_tokens, timeout)
        if provider == PROVIDER_OPENAI:
            return self._openai(model, system, user, max_tokens, timeout)
        if provider == PROVIDER_GOOGLE:
            return self._google(model, system, user, max_tokens, timeout)
        if provider == PROVIDER_OLLAMA:
            return self._ollama(model, system, user, max_tokens, timeout)
        raise LLMRequestError(f"Unknown provider: {provider}")

    def _anthropic(self, model, system, user, max_tokens, timeout) -> str:
        import anthropic

        key = self._get_key(PROVIDER_ANTHROPIC)
        if not key:
            raise LLMNotConfiguredError("Add an Anthropic API key in Settings or .env to use Claude")

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": user}],
            "timeout": timeout,
        }
        if system is not None:
            kwargs["system"] = system

        try:
            response = anthropic.Anthropic(api_key=key).messages.create(**kwargs)
        except anthropic.APITimeoutError as error:
            raise LLMTimeoutError(f"Request timed out after {int(timeout)} seconds.") from error
        except anthropic.APIStatusError as error:
            raise LLMRequestError(f"Anthropic API error: {error}") from error
        except anthropic.APIConnectionError as error:
            raise LLMRequestError(f"Could not reach Anthropic: {error}") from error

        return "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )

    def _openai(self, model, system, user, max_tokens, timeout) -> str:
        import openai
        from openai import OpenAI

        key = self._get_key(PROVIDER_OPENAI)
        if not key:
            raise LLMNotConfiguredError("Add an OpenAI API key in Settings to use GPT models")

        messages = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        try:
            response = OpenAI(api_key=key, timeout=timeout).chat.completions.create(
                model=model, max_tokens=max_tokens, messages=messages,
            )
        except openai.APITimeoutError as error:
            raise LLMTimeoutError(f"Request timed out after {int(timeout)} seconds.") from error
        except openai.APIStatusError as error:
            raise LLMRequestError(f"OpenAI API error: {error}") from error
        except openai.APIConnectionError as error:
            raise LLMRequestError(f"Could not reach OpenAI: {error}") from error

        return response.choices[0].message.content or ""

    def _google(self, model, system, user, max_tokens, timeout) -> str:
        import google.generativeai as genai
        from google.api_core.exceptions import DeadlineExceeded, GoogleAPIError

        key = self._get_key(PROVIDER_GOOGLE)
        if not key:
            raise LLMNotConfiguredError("Add a Google API key in Settings to use Gemini models")

        genai.configure(api_key=key)
        kwargs: dict = {"model_name": model}
        if system is not None:
            kwargs["system_instruction"] = system

        try:
            response = genai.GenerativeModel(**kwargs).generate_content(
                user,
                generation_config={"max_output_tokens": max_tokens},
                request_options={"timeout": timeout},
            )
        except DeadlineExceeded as error:
            raise LLMTimeoutError(f"Request timed out after {int(timeout)} seconds.") from error
        except GoogleAPIError as error:
            raise LLMRequestError(f"Google API error: {error}") from error

        return response.text

    def _ollama(self, model, system, user, max_tokens, timeout) -> str:
        base_url = self.profile.ollama_base_url or "http://localhost:11434"
        prompt = f"{system}\n\n{user}" if system else user

        try:
            response = requests.post(
                f"{base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                },
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.exceptions.ConnectionError as error:
            raise LLMRequestError(OLLAMA_NOT_RUNNING_MESSAGE) from error
        except requests.exceptions.Timeout as error:
            raise LLMTimeoutError(f"Request timed out after {int(timeout)} seconds.") from error
        except requests.exceptions.RequestException as error:
            raise LLMRequestError(f"Ollama API error: {error}") from error

        return response.json().get("response", "")

    def _get_key(self, provider: str) -> str:
        if provider == PROVIDER_ANTHROPIC:
            return self.profile.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if provider == PROVIDER_OPENAI:
            return self.profile.openai_api_key
        if provider == PROVIDER_GOOGLE:
            return self.profile.google_api_key
        return ""


def test_connection(provider: str, model: str, api_key_or_url: str) -> tuple[bool, float, str]:
    """Fires a minimal real call against the given provider using a
    typed-but-possibly-unsaved key/URL — used by Settings' "Test" buttons,
    so this never touches the persisted profile or self.profile.
    """
    from app.models.profile import ProfileSettings

    fake_profile = ProfileSettings()
    if provider == PROVIDER_OLLAMA:
        fake_profile.ollama_base_url = api_key_or_url
    elif provider == PROVIDER_ANTHROPIC:
        fake_profile.anthropic_api_key = api_key_or_url
    elif provider == PROVIDER_OPENAI:
        fake_profile.openai_api_key = api_key_or_url
    elif provider == PROVIDER_GOOGLE:
        fake_profile.google_api_key = api_key_or_url

    service = LLMService(profile=fake_profile)
    start = time.monotonic()
    try:
        service._call(provider, model, system=None, user="Reply with OK only", max_tokens=10, timeout=15.0)
        return True, time.monotonic() - start, ""
    except (LLMNotConfiguredError, LLMTimeoutError, LLMRequestError) as error:
        return False, time.monotonic() - start, str(error)
    except Exception as error:  # provider SDKs can raise their own auth errors directly
        return False, time.monotonic() - start, str(error)


def list_ollama_models(base_url: str) -> list[str] | None:
    """Returns the installed model names, or None if Ollama isn't reachable
    at all — distinct from an empty list (reachable, zero models pulled),
    so the UI can show "not running" vs. "run ollama pull ..." correctly.
    """
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=3)
        response.raise_for_status()
    except requests.exceptions.RequestException:
        return None
    return [model["name"] for model in response.json().get("models", [])]


def is_ollama_running(base_url: str) -> bool:
    return list_ollama_models(base_url) is not None


def _parse_json_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
        cleaned = cleaned.removesuffix("```").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise LLMRequestError("The model returned an unexpected response.") from error


def _parse_numbered_response(text: str) -> dict[int, str]:
    result = {}
    for raw_line in text.splitlines():
        match = NUMBERED_LINE_PATTERN.match(raw_line)
        if match:
            result[int(match.group(1))] = match.group(2)
    return result
