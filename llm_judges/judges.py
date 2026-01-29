import json
import requests
from typing import Optional, Dict, Any
from .judge_models import JudgeResult
from config import settings

def build_judge_prompt(original_file: str, user_prompt: str, applied_file: str, target_file: Optional[str] = None) -> str:
    """
    Construct the prompt for the LLM judge.
    """
    context = ""
    if target_file:
        context = f"""
Reference target file (may be empty if not available):
<TARGET_FILE>
{target_file}
</TARGET_FILE>
"""
    else:
        context = """
Reference target file (may be empty if not available):
<TARGET_FILE>
</TARGET_FILE>
"""

    prompt = f"""
You are an expert code reviewer evaluating an automated code editing system.

You will be given:

The original file content (before applying a change).

The user request (what change the user wanted).

The applied file content (after the automated apply mechanism).

Optionally, a reference target file (the “ground truth” we expected, if available).

Your task is to decide:

Whether the applied file correctly implements the user’s requested change without introducing obvious regressions.

How good the result is on a discrete 0–5 scale, not a continuous float.

Use the following scale for score:

0 = Completely incorrect. The change does not implement the request at all, or it severely breaks the code.

1 = Mostly incorrect. Some attempt is made, but the main behavior is wrong or broken.

2 = Partially correct. The change captures part of the intent, but important aspects are missing or incorrect.

3 = Mostly correct with issues. The main behavior is implemented, but there are notable problems (e.g., edge cases, formatting that breaks style, minor regressions).

4 = Correct with minor issues. The requested change is correctly implemented and code is usable; remaining issues are cosmetic or very minor.

5 = Fully correct. The applied code correctly implements the requested change, preserves existing behavior, and is clean and reasonable.

Additionally, output a binary field:

is_correct:

true if you consider the change acceptable to ship (score ≥ 4).

false otherwise.

Important instructions:

Focus on semantic behavior first: does the code implement what the user asked?

Consider obvious regressions: did the change break unrelated parts of the code?

Formatting/style issues should lower the score only if they make the code clearly worse or confusing.

If a reference target file is provided, you may use it to help you judge correctness, but do not require it to match exactly.

Output format:

Respond only with a strict JSON object matching this schema:

json
{{
  "is_correct": true,
  "score": 4,
  "reason": "Short explanation (1-3 sentences) why you gave this score."
}}
is_correct must be a boolean (true or false).

score must be an integer in the set.

reason should briefly explain your decision.

Now here is the data:

Original file:
<ORIGINAL_FILE>
{original_file}
</ORIGINAL_FILE>

User request:
<USER_PROMPT>
{user_prompt}
</USER_PROMPT>

Applied file:
<APPLIED_FILE>
{applied_file}
</APPLIED_FILE>
{context}
"""
    return prompt

from tracing import langfuse
from llm_client import LLMClient

def judge_apply_quality(
    original_file: str,
    user_prompt: str,
    applied_file: str,
    target_file: Optional[str] = None,
    model_name: Optional[str] = None,
    trace=None,
    parent_span=None,
) -> JudgeResult:
    """
    Use an LLM via OpenRouter to evaluate the quality of the applied change.
    """
    model = model_name or settings.judge_models[0] if settings.judge_models else settings.code_model_default
    
    # --- Langfuse Judge Span Start ---
    # Choose parent for the span
    if parent_span is not None:
        span_parent = parent_span
    elif trace is not None:
        span_parent = trace
    else:
        # Fallback to standalone span if no parent provided
        span_parent = langfuse 

    # Use start_observation (works on both Client and Span for creating child/new span)
    # On client: creates new root/trace if no context? OR creates span?
    # client.start_observation(name, as_type="span") returns a Span.
    judge_span = span_parent.start_observation(
        name="llm_judge",
        as_type="span",
        input={
            "original_file": original_file,
            "user_prompt": user_prompt,
            "applied_file": applied_file,
            "target_file": target_file,
            "model_name": model,
        },
    )
    # ---------------------------------
    
    prompt = build_judge_prompt(
        original_file=original_file,
        user_prompt=user_prompt,
        applied_file=applied_file,
        target_file=target_file
    )
    
    try:
        # Use the centralized client
        response_json = LLMClient.generate_json(
            model=model,
            prompt=prompt,
            temperature=settings.llm_temperature
        )
        
        result = JudgeResult(
            is_correct=response_json.get("is_correct", False),
            score=response_json.get("score", 0.0),
            reason=response_json.get("reason", "No reason provided"),
            model_name=model
        )
        
        # --- Langfuse Judge Span Update & Score ---
        judge_span.update(
            output={
                "is_correct": result.is_correct,
                "score": result.score,
                "reason": result.reason,
                "judge_model": result.model_name,
            }
        )

        judge_span.score(
            name="judge_score",
            value=result.score,
            data_type="NUMERIC",
            comment=result.reason,
        )
        judge_span.score(
            name="judge_is_correct",
            value=1 if result.is_correct else 0,
            data_type="BOOLEAN",
            comment="1 if judge considers the change correct",
        )
        judge_span.end()
        # ------------------------------------------

        return result
        
    except Exception as e:
        error_msg = f"LLM Call Failed: {str(e)}"
        
        # End span with error info
        judge_span.update(output={"error": error_msg})
        judge_span.end()
        
        return JudgeResult(
            is_correct=False,
            score=0.0,
            reason=error_msg,
            model_name=model
        )
