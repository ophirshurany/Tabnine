"""
Main evaluation runner for Apply Code Changes mechanism.

This script runs the full evaluation pipeline including:
- Basic metrics (exact match, line overlap, syntax validity)
- Optional LLM-as-a-Judge evaluation
- Langfuse tracing for observability
- Detailed analysis and reporting
"""

import argparse
import json
import sys
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from dataset_builder import get_dataset, get_dataset_by_difficulty, get_expected_failures
from apply_changes import apply_replace_function, extract_function_block
from models import ModelEdit, DatasetExample, EvaluationResult, DifficultyLevel
from pipeline import (
    exact_match, line_overlap, check_syntax_valid, 
    check_function_preserved, normalized_line_overlap, semantic_similarity
)
from config import settings
from llm_judges.judges import judge_apply_quality
from llm_client import generate_model_output
from tracing import langfuse


@dataclass
class EvaluationConfig:
    """Configuration for evaluation run."""
    mode: str = "simulated"  # "simulated" or "real"
    code_models: List[str] = field(default_factory=list) # List of models to evaluate
    use_llm_judge: bool = False
    judge_models: List[str] = field(default_factory=list)
    filter_difficulty: Optional[str] = None
    limit: int = 0  # 0 for no limit
    verbose: bool = False
    output_file: Optional[str] = None


@dataclass 
class DetailedResult:
    """Detailed result for a single example."""
    example_id: int
    code_model: str
    difficulty: str
    expected_success: bool
    function_name: str
    tags: List[str]
    
    # Apply results
    apply_succeeded: bool  # Did we find and replace the function?
    exact_match: bool
    line_overlap: float
    normalized_overlap: float
    semantic_similarity: float
    syntax_valid: bool
    syntax_error: Optional[str]
    function_preserved: bool
    
    # Success Metric
    overall_success: bool = False

    # Judge results (optional)
    judge_scores: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Analysis
    outcome_as_expected: bool = False
    failure_reason: Optional[str] = None


def run_evaluation(config: EvaluationConfig) -> List[DetailedResult]:
    """
    Run the full evaluation pipeline.
    
    Returns a list of DetailedResult objects for analysis.
    """
    # Load dataset
    dataset = get_dataset()
    
    # Filter by difficulty if specified
    if config.filter_difficulty:
        try:
            diff = DifficultyLevel(config.filter_difficulty)
            dataset = get_dataset_by_difficulty(diff)
        except ValueError:
            print(f"Warning: Unknown difficulty '{config.filter_difficulty}', using full dataset")
    
    # Apply limit
    if config.limit > 0:
        dataset = dataset[:config.limit]
    
    print(f"Running evaluation on {len(dataset)} examples...")
    print(f"Mode: {config.mode.upper()}")
    
    # Determine code models to run
    code_models_to_test = config.code_models
    if not code_models_to_test:
        if config.mode == "real":
            code_models_to_test = [settings.code_model_default]
        else:
            code_models_to_test = ["simulated"]
            
    print(f"Code Models: {code_models_to_test}")
    
    # Setup judge models
    judge_models = []
    if config.use_llm_judge:
        judge_models = config.judge_models if config.judge_models else settings.judge_models
        if not judge_models:
            judge_models = [settings.code_model_default]
        print(f"LLM Judges enabled: {judge_models}")
    
    all_results: List[DetailedResult] = []
    
    # Outer loop: Iterate over Code Models
    for code_model in code_models_to_test:
        print(f"\n" + "=" * 80)
        print(f"EVALUATING CODE MODEL: {code_model}")
        print("=" * 80)
    
        # Aggregate stats for this model
        stats = {
            "total": 0,
            "exact_matches": 0,
            "syntax_valid": 0,
            "function_preserved": 0,
            "apply_succeeded": 0,
            "overall_success": 0,
            "outcome_as_expected": 0,
            "by_difficulty": {},
            "by_tag": {},
            "judge_scores": {m: {"sum": 0.0, "correct": 0, "count": 0} for m in judge_models}
        }
        
        current_model_results = []
    
        for ex in dataset:
            print(f"\n--- Example {ex.id}: {ex.expected_function_name} [{ex.difficulty.value}] ---")
            
            # --- Langfuse Trace Start ---
            trace = langfuse.start_span(
                name="apply_evaluation",
                input={
                    "id": ex.id,
                    "code_model": code_model,
                    "mode": config.mode,
                    "user_prompt": ex.user_prompt,
                    "original_file": ex.original_file,
                    "difficulty": ex.difficulty.value,
                    "expected_success": ex.expected_success,
                },
                metadata={
                    "expected_function_name": ex.expected_function_name,
                    "tags": ex.tags,
                },
            )
            
            # Get model output
            model_output = ""
            if config.mode == "real":
                print(f"  Generating code with {code_model}...")
                model_output = generate_model_output(ex.original_file, ex.user_prompt, code_model)
                if not model_output:
                     print("  [ERROR] Empty response from model")
            else:
                # Simulated mode
                model_output = ex.model_output
                if not model_output:
                    # Fallback: extract from target (legacy behavior)
                    model_output = extract_function_block(ex.target_file, ex.expected_function_name)
                    if config.verbose:
                        print(f"  [INFO] No model_output, extracted from target_file")
            
            if not model_output:
                print(f"  [ERROR] No model output available")
                # Create failure result
                res = DetailedResult(
                    example_id=ex.id,
                    code_model=code_model,
                    difficulty=ex.difficulty.value,
                    expected_success=ex.expected_success,
                    function_name=ex.expected_function_name,
                    tags=ex.tags,
                    apply_succeeded=False,
                    exact_match=False,
                    line_overlap=0.0,
                    normalized_overlap=0.0,
                    semantic_similarity=0.0,
                    syntax_valid=False,
                    syntax_error="No model output",
                    function_preserved=False,
                    overall_success=False, # Default to False if no model output
                    failure_reason="No model output available"
                )
                current_model_results.append(res)
                all_results.append(res)
                trace.end()
                continue
            
            # Create edit
            edit = ModelEdit(
                function_name=ex.expected_function_name,
                new_function_code=model_output
            )
            
            # --- Apply Span ---
            apply_span = trace.start_observation(
                name="apply_change",
                as_type="span",
                input={
                    "original_file": ex.original_file,
                    "function_name": ex.expected_function_name,
                    "model_output": model_output,
                },
            )
            
            # Apply the change
            applied_file = apply_replace_function(ex.original_file, edit)
            
            # Check if apply actually did something (function was found)
            # Heuristic: file changed OR model output is contained
            apply_succeeded = applied_file != ex.original_file or (model_output.strip() and model_output.strip() in applied_file)
            
            # Compute metrics
            is_exact = exact_match(applied_file, ex.target_file)
            overlap = line_overlap(applied_file, ex.target_file)
            norm_overlap = normalized_line_overlap(applied_file, ex.target_file)
            sem_sim = semantic_similarity(applied_file, ex.target_file)
            syntax_ok, syntax_err = check_syntax_valid(applied_file)
            func_preserved = check_function_preserved(applied_file, ex.expected_function_name)
            
            # Primary Success Metric
            # Success = Applied AND Syntax Valid AND (Exact Match OR High Semantic Similarity)
            # We use 0.8 as the threshold for semantic similarity
            overall_success = apply_succeeded and syntax_ok and (is_exact or sem_sim >= 0.8)
            
            # Determine if outcome matches expectation
            outcome_as_expected = (ex.expected_success == is_exact)
            
            # Create result
            result = DetailedResult(
                example_id=ex.id,
                code_model=code_model,
                difficulty=ex.difficulty.value,
                expected_success=ex.expected_success,
                function_name=ex.expected_function_name,
                tags=ex.tags,
                apply_succeeded=apply_succeeded,
                exact_match=is_exact,
                line_overlap=overlap,
                normalized_overlap=norm_overlap,
                semantic_similarity=sem_sim,
                syntax_valid=syntax_ok,
                syntax_error=syntax_err,
                function_preserved=func_preserved,
                overall_success=overall_success,
                outcome_as_expected=outcome_as_expected,
                failure_reason=ex.failure_reason if (config.mode == "simulated" and not is_exact) else None
            )
            
            # Update stats
            stats["total"] += 1
            if is_exact:
                stats["exact_matches"] += 1
            if syntax_ok:
                stats["syntax_valid"] += 1
            if func_preserved:
                stats["function_preserved"] += 1
            if apply_succeeded:
                stats["apply_succeeded"] += 1
            if overall_success:
                stats["overall_success"] += 1
            if outcome_as_expected:
                stats["outcome_as_expected"] += 1
            
            # By difficulty
            diff_key = ex.difficulty.value
            if diff_key not in stats["by_difficulty"]:
                stats["by_difficulty"][diff_key] = {"total": 0, "exact": 0, "syntax": 0}
            stats["by_difficulty"][diff_key]["total"] += 1
            if is_exact:
                stats["by_difficulty"][diff_key]["exact"] += 1
            if syntax_ok:
                stats["by_difficulty"][diff_key]["syntax"] += 1
            
            # By tag
            for tag in ex.tags:
                if tag not in stats["by_tag"]:
                    stats["by_tag"][tag] = {"total": 0, "exact": 0}
                stats["by_tag"][tag]["total"] += 1
                if is_exact:
                    stats["by_tag"][tag]["exact"] += 1
            
            # Log to span
            apply_span.update(output={"applied_file": applied_file})
            apply_span.score(name="exact_match", value=1 if is_exact else 0, data_type="BOOLEAN")
            apply_span.score(name="line_overlap", value=overlap, data_type="NUMERIC")
            apply_span.score(name="semantic_similarity", value=sem_sim, data_type="NUMERIC")
            apply_span.score(name="syntax_valid", value=1 if syntax_ok else 0, data_type="BOOLEAN")
            apply_span.end()
            
            # Print result
            status = "✓" if is_exact else "✗"
            success_status = "SUCCESS" if overall_success else "FAIL"
            expected_str = "as expected" if outcome_as_expected else "UNEXPECTED"
            print(f"  Exact: {status} | Success: {success_status} | SemSim: {sem_sim:.2f} | {expected_str}")
            
            # LLM Judge
            for model_name in judge_models:
                print(f"  Judge ({model_name})... ", end="", flush=True)
                try:
                    judge_result = judge_apply_quality(
                        original_file=ex.original_file,
                        user_prompt=ex.user_prompt,
                        applied_file=applied_file,
                        target_file=ex.target_file,
                        model_name=model_name,
                        trace=trace,
                        parent_span=apply_span
                    )
                    print(f"Score: {judge_result.score:.2f} | Correct: {judge_result.is_correct}")
                    
                    result.judge_scores[model_name] = {
                        "score": judge_result.score,
                        "is_correct": judge_result.is_correct,
                        "reason": judge_result.reason
                    }
                    
                    stats["judge_scores"][model_name]["sum"] += judge_result.score
                    stats["judge_scores"][model_name]["count"] += 1
                    if judge_result.is_correct:
                        stats["judge_scores"][model_name]["correct"] += 1
                        
                except Exception as e:
                    print(f"Error: {e}")
                    result.judge_scores[model_name] = {"error": str(e)}
            
            current_model_results.append(result)
            all_results.append(result)
            trace.end()
        
        # --- End of Code Model Loop ---
        # Print Summary for this model
        print("\n" + "-" * 70)
        print(f"SUMMARY FOR MODEL: {code_model}")
        print("-" * 70)
        
        total = stats["total"]
        if total == 0:
            print("No examples processed.")
        else:
            print(f"\n📊 Overall Results ({total} examples)")
            print(f"   Exact Matches:      {stats['exact_matches']:3d} ({stats['exact_matches']/total:6.1%})")
            print(f"   Overall Success:    {stats['overall_success']:3d} ({stats['overall_success']/total:6.1%})")
            print(f"   Apply Succeeded:    {stats['apply_succeeded']:3d} ({stats['apply_succeeded']/total:6.1%})")
            print(f"   Syntax Valid:       {stats['syntax_valid']:3d} ({stats['syntax_valid']/total:6.1%})")
            print(f"   Function Preserved: {stats['function_preserved']:3d} ({stats['function_preserved']/total:6.1%})")
            print(f"   Outcome as Expected:{stats['outcome_as_expected']:3d} ({stats['outcome_as_expected']/total:6.1%})")
    
            if judge_models:
                print(f"   Judge Results:")
                for model, s in stats["judge_scores"].items():
                    if s["count"] > 0:
                        print(f"     {model}: Avg {s['sum']/s['count']:.2f}, Correct {s['correct']}/{s['count']}")

    # Save results if output file specified (using all results)
    if config.output_file:
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "config": {
                "mode": config.mode,
                "code_models": code_models_to_test,
                "use_llm_judge": config.use_llm_judge,
                "judge_models": judge_models,
            },
            "results": [
                {
                    "example_id": r.example_id,
                    "code_model": r.code_model,
                    "difficulty": r.difficulty,
                    "function_name": r.function_name,
                    "exact_match": r.exact_match,
                    "overall_success": r.overall_success,
                    "syntax_valid": r.syntax_valid,
                    "line_overlap": r.line_overlap,
                    "semantic_similarity": r.semantic_similarity,
                    "judge_scores": r.judge_scores,
                }
                for r in all_results
            ]
        }
        with open(config.output_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"\n📁 Results saved to {config.output_file}")
    
    langfuse.flush()
    return all_results


def main():
    parser = argparse.ArgumentParser(
        description="Run Apply Code Changes evaluation pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_evaluation.py                    # Basic evaluation
  python run_evaluation.py --use-llm-judge    # With LLM judge
  python run_evaluation.py --difficulty hard  # Only hard examples
  python run_evaluation.py -o results.json    # Save results to file
        """
    )
    parser.add_argument("--mode", type=str, default="simulated",
                        choices=["simulated", "real"],
                        help="Execution mode: simulated (dataset output) or real (live LLM generation)")
    parser.add_argument("--code-model", type=str, action="append",
                        help="Model to use for code generation (can specify multiple)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit number of examples (0 for all)")
    parser.add_argument("--use-llm-judge", action="store_true", 
                        help="Enable LLM-as-a-Judge evaluation")
    parser.add_argument("--judge-model", type=str, action="append",
                        help="Specific judge model(s) to use (can specify multiple)")
    parser.add_argument("--all-judge-models", action="store_true",
                        help="Use all configured judge models")
    parser.add_argument("--difficulty", "-d", type=str,
                        choices=["easy", "medium", "hard", "adversarial"],
                        help="Filter examples by difficulty level")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")
    parser.add_argument("--output", "-o", type=str,
                        help="Save results to JSON file")
    
    args = parser.parse_args()
    
    # Build config
    judge_models = []
    if args.all_judge_models:
        judge_models = settings.judge_models
    elif args.judge_model:
        judge_models = args.judge_model
    
    # Default code model if real mode and none specified
    code_models = args.code_model
    
    config = EvaluationConfig(
        mode=args.mode,
        code_models=code_models,
        use_llm_judge=args.use_llm_judge or args.all_judge_models or bool(args.judge_model),
        judge_models=judge_models,
        filter_difficulty=args.difficulty,
        limit=args.limit,
        verbose=args.verbose,
        output_file=args.output
    )
    
    run_evaluation(config)


if __name__ == "__main__":
    main()
