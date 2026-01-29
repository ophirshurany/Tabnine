"""
Pipeline module for Apply Code Changes Evaluation

This module provides metrics and evaluation utilities for assessing
the quality of code apply operations.
"""

import ast
import sys
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass
from dataset_builder import get_dataset
from apply_changes import apply_replace_function, extract_function_block
from models import ModelEdit, DatasetExample, EvaluationResult


def exact_match(applied: str, target: str) -> bool:
    """
    Check if the applied code exactly matches the target code (stripped of leading/trailing whitespace).
    """
    return applied.strip() == target.strip()


def line_overlap(applied: str, target: str) -> float:
    """
    Compute a similarity score based on line-by-line comparison.
    
    Metric Definition:
    Intersection of lines at the same position divided by the max length.
    Score = (Count of indices i where applied_lines[i] == target_lines[i]) / max(len(applied_lines), len(target_lines))
    
    This essentially measures how much of the file structure is preserved 
    and perfectly matching in position.
    """
    a_lines = applied.splitlines()
    t_lines = target.splitlines()
    
    if not a_lines and not t_lines:
        return 1.0  # Both empty
    
    max_len = max(len(a_lines), len(t_lines))
    if max_len == 0:
        return 0.0
        
    # Count matching lines at same index
    same_count = sum(1 for a, t in zip(a_lines, t_lines) if a == t)
    
    return same_count / max_len


def check_syntax_valid(code: str) -> Tuple[bool, Optional[str]]:
    """
    Check if the code is syntactically valid Python.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as e:
        return False, f"Line {e.lineno}: {e.msg}"


def check_function_preserved(applied: str, function_name: str) -> bool:
    """
    Check if the target function exists in the applied code.
    
    This verifies that the apply mechanism correctly placed the function
    and it's parseable.
    """
    try:
        tree = ast.parse(applied)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == function_name:
                    return True
        return False
    except SyntaxError:
        return False


def normalized_line_overlap(applied: str, target: str) -> float:
    """
    Compute line overlap after normalizing whitespace.
    
    This is more forgiving than exact line_overlap - it strips each line
    before comparison, so trailing whitespace differences don't matter.
    """
    a_lines = [line.strip() for line in applied.splitlines()]
    t_lines = [line.strip() for line in target.splitlines()]
    
    if not a_lines and not t_lines:
        return 1.0
    
    max_len = max(len(a_lines), len(t_lines))
    if max_len == 0:
        return 0.0
    
    same_count = sum(1 for a, t in zip(a_lines, t_lines) if a == t)
    return same_count / max_len


def semantic_similarity(applied: str, target: str) -> float:
    """
    Compute semantic similarity by comparing AST structures.
    
    This ignores formatting differences and focuses on whether the
    code has the same structure.
    
    Returns a score from 0.0 to 1.0.
    """
    try:
        applied_ast = ast.parse(applied)
        target_ast = ast.parse(target)
        
        # Simple comparison: dump ASTs and compare
        applied_dump = ast.dump(applied_ast)
        target_dump = ast.dump(target_ast)
        
        if applied_dump == target_dump:
            return 1.0
        
        # Partial credit: compare number of matching top-level nodes
        applied_nodes = list(ast.iter_child_nodes(applied_ast))
        target_nodes = list(ast.iter_child_nodes(target_ast))
        
        if not target_nodes:
            return 1.0 if not applied_nodes else 0.0
        
        matches = 0
        for t_node in target_nodes:
            t_dump = ast.dump(t_node)
            for a_node in applied_nodes:
                if ast.dump(a_node) == t_dump:
                    matches += 1
                    break
        
        return matches / len(target_nodes)
        
    except SyntaxError:
        return 0.0


@dataclass
class MetricsSummary:
    """Summary of evaluation metrics across all examples."""
    total: int = 0
    exact_matches: int = 0
    syntax_valid: int = 0
    function_preserved: int = 0
    line_overlap_sum: float = 0.0
    normalized_overlap_sum: float = 0.0
    semantic_similarity_sum: float = 0.0
    
    # By difficulty
    by_difficulty: Dict[str, Dict[str, Any]] = None
    
    # By expected outcome
    expected_success_correct: int = 0  # Expected success and got exact match
    expected_failure_correct: int = 0  # Expected failure and didn't get exact match
    
    def __post_init__(self):
        if self.by_difficulty is None:
            self.by_difficulty = {}


def evaluate_single(
    example: DatasetExample,
    applied_file: str
) -> EvaluationResult:
    """
    Evaluate a single apply result against the target.
    
    Returns an EvaluationResult with all metrics.
    """
    is_exact = exact_match(applied_file, example.target_file)
    overlap = line_overlap(applied_file, example.target_file)
    syntax_ok, syntax_error = check_syntax_valid(applied_file)
    func_preserved = check_function_preserved(applied_file, example.expected_function_name)
    
    return EvaluationResult(
        example_id=example.id,
        exact_match=is_exact,
        line_overlap=overlap,
        syntax_valid=syntax_ok,
        function_preserved=func_preserved,
        applied_file=applied_file,
        error=syntax_error
    )


def run_pipeline():
    """Run the basic evaluation pipeline (without LLM judge)."""
    dataset = get_dataset()
    print(f"Running pipeline on {len(dataset)} examples...\n")
    
    summary = MetricsSummary()
    results: List[EvaluationResult] = []
    
    for ex in dataset:
        print(f"--- Example ID: {ex.id} ({ex.expected_function_name}) [{ex.difficulty.value}] ---")
        
        # Use model_output if available, otherwise fall back to extracting from target
        if ex.model_output:
            predicted_code = ex.model_output
        else:
            predicted_code = extract_function_block(ex.target_file, ex.expected_function_name)
        
        if not predicted_code:
            print(f"  [ERROR] No model output and could not extract function '{ex.expected_function_name}'")
            results.append(EvaluationResult(
                example_id=ex.id,
                exact_match=False,
                line_overlap=0.0,
                syntax_valid=False,
                function_preserved=False,
                applied_file="",
                error="No model output available"
            ))
            continue
        
        # Create the edit object
        edit = ModelEdit(
            function_name=ex.expected_function_name,
            new_function_code=predicted_code
        )
        
        # Apply Changes
        applied_file = apply_replace_function(ex.original_file, edit)
        
        # Evaluate
        result = evaluate_single(ex, applied_file)
        results.append(result)
        
        # Update summary
        summary.total += 1
        if result.exact_match:
            summary.exact_matches += 1
        if result.syntax_valid:
            summary.syntax_valid += 1
        if result.function_preserved:
            summary.function_preserved += 1
        summary.line_overlap_sum += result.line_overlap
        summary.normalized_overlap_sum += normalized_line_overlap(applied_file, ex.target_file)
        summary.semantic_similarity_sum += semantic_similarity(applied_file, ex.target_file)
        
        # Track by difficulty
        diff_key = ex.difficulty.value
        if diff_key not in summary.by_difficulty:
            summary.by_difficulty[diff_key] = {"total": 0, "exact": 0, "syntax_valid": 0}
        summary.by_difficulty[diff_key]["total"] += 1
        if result.exact_match:
            summary.by_difficulty[diff_key]["exact"] += 1
        if result.syntax_valid:
            summary.by_difficulty[diff_key]["syntax_valid"] += 1
        
        # Track expected vs actual
        if ex.expected_success and result.exact_match:
            summary.expected_success_correct += 1
        elif not ex.expected_success and not result.exact_match:
            summary.expected_failure_correct += 1
        
        # Print result
        status = "✓ MATCH" if result.exact_match else "✗ DIFF"
        syntax_status = "✓" if result.syntax_valid else "✗"
        func_status = "✓" if result.function_preserved else "✗"
        expected = "expected" if (ex.expected_success == result.exact_match) else "UNEXPECTED"
        
        print(f"  {status} | Syntax: {syntax_status} | Func: {func_status} | Overlap: {result.line_overlap:.2f} | {expected}")
        
        if not result.exact_match and ex.expected_success:
            # Show why it failed when we expected success
            if ex.failure_reason:
                print(f"  Note: {ex.failure_reason}")
    
    # Print Summary
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    
    total = summary.total
    if total == 0:
        print("No examples processed.")
        return
    
    print(f"\nOverall Results ({total} examples):")
    print(f"  Exact Matches:      {summary.exact_matches:3d} ({summary.exact_matches/total:6.1%})")
    print(f"  Syntax Valid:       {summary.syntax_valid:3d} ({summary.syntax_valid/total:6.1%})")
    print(f"  Function Preserved: {summary.function_preserved:3d} ({summary.function_preserved/total:6.1%})")
    print(f"  Avg Line Overlap:   {summary.line_overlap_sum/total:.4f}")
    print(f"  Avg Normalized:     {summary.normalized_overlap_sum/total:.4f}")
    print(f"  Avg Semantic Sim:   {summary.semantic_similarity_sum/total:.4f}")
    
    print(f"\nBy Difficulty:")
    for diff, stats in sorted(summary.by_difficulty.items()):
        t = stats["total"]
        e = stats["exact"]
        s = stats["syntax_valid"]
        print(f"  {diff:12s}: {e}/{t} exact ({e/t:.0%}), {s}/{t} syntax valid")
    
    # Count expected outcomes
    expected_success = len([ex for ex in dataset if ex.expected_success])
    expected_failure = len([ex for ex in dataset if not ex.expected_success])
    
    print(f"\nExpected vs Actual:")
    print(f"  Expected success, got success: {summary.expected_success_correct}/{expected_success}")
    print(f"  Expected failure, got failure: {summary.expected_failure_correct}/{expected_failure}")


if __name__ == "__main__":
    run_pipeline()
