# Apply Code Changes Evaluation: Analysis Report

## Phase 3 Improvements (Real LLM & Better Metrics)

Recent updates have expanded the evaluation capabilities:

1. **Real LLM Integration**: Now supports generating code changes on-the-fly using OpenRouter (e.g., Gemini 2.0 Flash), enabling end-to-end agent evaluation.
2. **Improved Metrics**: Introduced `Overall Success` metric that combines exact match and semantic similarity, relaxing strict formatting requirements.
3. **Separation of Concerns**: Metrics now distinguish between "Apply Failed" (mechanism issue) and "Model Failed" (bad generation), allowing for better root cause analysis.
4. **Model Comparison**: Support for side-by-side comparison of multiple code models.

---

## Executive Summary

This document analyzes the performance of a naive indentation-based "apply" mechanism for integrating code changes into Python files. The evaluation uses a dataset of 20 examples testing various failure modes.

## Evaluation Methodology

### Success Metric Definition

We define **Overall Success** as:

- **Applied Successfully**: The apply mechanism located the function and made changes.
- **Syntax Valid**: The resulting file is valid Python.
- **High Fidelity**: The result matches the target EITHER exactly OR with high semantic similarity (score ≥ 0.8).

This addresses the limitation where valid code was marked as failure due to minor whitespace differences.

### Apply Mechanism

The apply mechanism (`apply_changes.py`) uses a simple indentation-based approach:

1. Find the function definition line (`def function_name(`)
2. Determine the function's base indentation
3. Scan forward until a line with equal or lesser indentation is found
4. Replace the entire block with the new code

### Dataset Design

The dataset (`dataset_builder.py`) contains 20 examples across 4 difficulty levels.
**Key Design Principle:** The `model_output` field is separate from `target_file`, allowing us to test how the apply mechanism handles imperfect inputs.

## Results (Simulated Baseline)

| Metric | Score |
|--------|-------|
| Exact Match | 50% (10/20) |
| **Overall Success** | **55% (11/20)** |
| Apply Succeeded | 90% (18/20) |
| Syntax Valid | 90% (18/20) |
| Function Preserved | 80% (16/20) |

*Note: Overall Success is higher than Exact Match because it accepts semantically equivalent formatting.*

## Analysis: Apply Quality vs. Model Quality

We distinguish failures into two categories:

1. **Apply Mechanism Failures**: The model generated correct code, but the apply mechanism failed to integrate it properly.
    - *Indicators*: `model_output_valid=True`, `apply_succeeded=False` OR `syntax_valid=False` (when model code was valid).
    - *Common Causes*: Decorators missed, indentation mismatches, inability to insert new functions.

2. **Model Quality Failures**: The model generated incorrect or incomplete code.
    - *Indicators*: `model_output_valid=False` (e.g., empty, syntax error in snippet itself) OR `semantic_similarity` is low.
    - *Common Causes*: Hallucinated function names, incomplete code blocks, logic errors.

## LLM-as-a-Judge Analysis

The LLM Judge provides a third opinion. Initial analysis shows:

- **Agreement**: Judge agrees with Exact Match on ~90% of cases.
- **Disagreement**: Judge properly identifies "Success" in cases where Exact Match fails due to benign formatting (e.g., extra newlines), aligning closely with `Semantic Similarity`.

## Recommendations

For a production coding agent, the apply mechanism should:

1. **Normalize indentation** before applying.
2. **Use AST-based comparison** for success metrics (implemented via Semantic Similarity).
3. **Validate syntax** before committing changes.
4. **Support insertion** of new functions (currently a major limitation).
