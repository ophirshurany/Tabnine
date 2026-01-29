from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

class DifficultyLevel(str, Enum):
    """Difficulty level for dataset examples."""
    EASY = "easy"           # Perfect model output, simple function
    MEDIUM = "medium"       # Minor imperfections (whitespace, formatting)
    HARD = "hard"           # Significant issues (wrong indentation, partial code)
    ADVERSARIAL = "adversarial"  # Edge cases designed to break naive apply


class DatasetExample(BaseModel):
    """
    Schema for a single evaluation example.
    
    Key design: model_output is SEPARATE from target_file to allow testing
    the apply mechanism with imperfect/noisy model outputs.
    """
    id: int
    language: str = "python"
    original_file: str
    target_file: str                    # Ground truth: what the file SHOULD look like after apply
    user_prompt: str
    expected_function_name: str         # Function that is supposed to be edited
    model_output: Optional[str] = None  # Simulated model output (may be imperfect)
    difficulty: DifficultyLevel = DifficultyLevel.EASY
    expected_success: bool = True       # Whether we expect the apply to succeed
    failure_reason: Optional[str] = None  # Expected failure mode if expected_success=False
    tags: List[str] = []                # Tags for categorizing examples (e.g., "indentation", "multi-function")


class ModelEdit(BaseModel):
    """
    Schema for the expected output from the coding model (or simulation).
    """
    function_name: str
    new_function_code: str  # full updated implementation of the function


class EvaluationResult(BaseModel):
    """
    Schema for evaluation results of a single example.
    """
    example_id: int
    exact_match: bool
    line_overlap: float
    syntax_valid: bool
    function_preserved: bool  # Was the target function correctly placed?
    judge_score: Optional[float] = None
    judge_is_correct: Optional[bool] = None
    judge_reason: Optional[str] = None
    applied_file: str
    error: Optional[str] = None
