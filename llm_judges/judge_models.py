from pydantic import BaseModel
from typing import Optional

class JudgeResult(BaseModel):
    """
    Structured output from the LLM judge.
    """
    is_correct: bool
    score: float  # 0 to 5 integer, float for compatibility
    reason: str
    model_name: str  # which judge model produced this result
