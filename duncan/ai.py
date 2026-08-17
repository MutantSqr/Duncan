from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AIAnalysis:
    status: str
    text: str
    model: str | None = None


def analyze_with_openai(context: str, model: str | None = None) -> AIAnalysis:
    if not os.getenv("OPENAI_API_KEY"):
        return AIAnalysis("disabled", "AI analysis not requested or OPENAI_API_KEY is not set.")
    try:
        from openai import OpenAI
    except ImportError:
        return AIAnalysis("unavailable", "Install Duncan with the 'ai' extra to enable OpenAI analysis.")
    chosen_model = model or os.getenv("DUNCAN_AI_MODEL", "gpt-5.4-mini")
    prompt = (
        "You are Duncan, a concise senior test engineer. Analyze the supplied test results. "
        "Identify root causes, distinguish test failures from infrastructure failures, rank fixes, "
        "and never claim evidence not present.\n\n" + context[:120_000]
    )
    try:
        response = OpenAI().responses.create(model=chosen_model, input=prompt)
        return AIAnalysis("complete", response.output_text.strip(), chosen_model)
    except Exception as exc:
        return AIAnalysis("error", f"AI analysis failed safely: {type(exc).__name__}: {exc}", chosen_model)
