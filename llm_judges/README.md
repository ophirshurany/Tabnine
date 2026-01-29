# LLM-as-a-Judge

This directory contains the implementation of the LLM-based evaluation system.

## Components

- `judge_models.py`: Defines the `JudgeResult` Pydantic model.
- `judges.py`: Contains the logic to construct prompts and call the LLM using OpenRouter.

## Configuration

The judge behavior is controlled by `.env` and `config.py`.

- `JUDGE_MODELS`: A comma-separated list of OpenRouter model IDs to use as judges.
- `OPENROUTER_API_KEY`: Your OpenRouter API key.

## Usage

You can use the `judge_apply_quality` function programmatically:

```python
from llm_judges.judges import judge_apply_quality

result = judge_apply_quality(
    original_file="...",
    user_prompt="...",
    applied_file="...",
    target_file="..." # Optional
)

print(result.is_correct)
print(result.score)
print(result.reason)
```

## Prompt Structure

The prompt provides the original file, user prompt, and applied result (and optionally the target file) to the LLM and asks for a structured JSON response:

```json
{
    "is_correct": boolean,
    "score": float,
    "reason": "string"
}
```
