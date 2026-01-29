"""
End-to-end tests for the Apply Code Changes evaluation pipeline.

These tests verify:
1. Pipeline integrity (no crashes)
2. Expected success/failure rates by difficulty
3. LLM judge interface
4. Specific failure mode detection
"""

import unittest
from unittest.mock import patch, MagicMock
from dataset_builder import get_dataset, get_dataset_by_difficulty, get_expected_failures
from apply_changes import apply_replace_function, extract_function_block
from models import ModelEdit, DifficultyLevel
from pipeline import (
    exact_match, line_overlap, check_syntax_valid, 
    check_function_preserved, normalized_line_overlap, semantic_similarity
)
from llm_judges.judges import judge_apply_quality
from llm_judges.judge_models import JudgeResult


class TestDataset(unittest.TestCase):
    """Tests for dataset structure and content."""
    
    def setUp(self):
        self.dataset = get_dataset()
    
    def test_dataset_not_empty(self):
        """Dataset should have examples."""
        self.assertGreater(len(self.dataset), 0)
    
    def test_dataset_has_all_difficulties(self):
        """Dataset should cover all difficulty levels."""
        difficulties = set(ex.difficulty for ex in self.dataset)
        self.assertEqual(difficulties, set(DifficultyLevel))
    
    def test_all_examples_have_model_output(self):
        """All examples should have model_output defined."""
        for ex in self.dataset:
            self.assertIsNotNone(ex.model_output, f"Example {ex.id} missing model_output")
            self.assertTrue(len(ex.model_output.strip()) > 0, f"Example {ex.id} has empty model_output")
    
    def test_expected_failures_exist(self):
        """Dataset should include expected failure cases."""
        failures = get_expected_failures()
        self.assertGreater(len(failures), 0, "Dataset should have expected failure cases")
    
    def test_examples_have_tags(self):
        """All examples should have at least one tag."""
        for ex in self.dataset:
            self.assertGreater(len(ex.tags), 0, f"Example {ex.id} has no tags")


class TestApplyMechanism(unittest.TestCase):
    """Tests for the apply mechanism itself."""
    
    def setUp(self):
        self.dataset = get_dataset()
    
    def test_apply_does_not_crash(self):
        """Apply mechanism should not crash on any example."""
        for ex in self.dataset:
            model_output = ex.model_output or extract_function_block(ex.target_file, ex.expected_function_name)
            if not model_output:
                continue
            
            edit = ModelEdit(
                function_name=ex.expected_function_name,
                new_function_code=model_output
            )
            
            # Should not raise
            applied = apply_replace_function(ex.original_file, edit)
            self.assertIsInstance(applied, str)
    
    def test_easy_examples_succeed(self):
        """Easy examples should all produce exact matches."""
        easy = get_dataset_by_difficulty(DifficultyLevel.EASY)
        
        for ex in easy:
            edit = ModelEdit(
                function_name=ex.expected_function_name,
                new_function_code=ex.model_output
            )
            applied = apply_replace_function(ex.original_file, edit)
            
            self.assertTrue(
                exact_match(applied, ex.target_file),
                f"Easy example {ex.id} should produce exact match"
            )
    
    def test_expected_failures_do_not_exact_match(self):
        """Examples marked as expected failures should not produce exact matches."""
        failures = get_expected_failures()
        
        for ex in failures:
            edit = ModelEdit(
                function_name=ex.expected_function_name,
                new_function_code=ex.model_output
            )
            applied = apply_replace_function(ex.original_file, edit)
            
            # These should NOT be exact matches
            is_exact = exact_match(applied, ex.target_file)
            self.assertFalse(
                is_exact,
                f"Expected failure example {ex.id} should not produce exact match"
            )
    
    def test_function_not_found_returns_original(self):
        """When function is not found, original should be returned."""
        original = "def other_func():\n    pass\n"
        edit = ModelEdit(
            function_name="nonexistent",
            new_function_code="def nonexistent():\n    return 42\n"
        )
        
        applied = apply_replace_function(original, edit)
        self.assertEqual(applied, original)


class TestMetrics(unittest.TestCase):
    """Tests for evaluation metrics."""
    
    def test_exact_match_identical(self):
        """Identical strings should match."""
        self.assertTrue(exact_match("def foo():\n    pass", "def foo():\n    pass"))
    
    def test_exact_match_whitespace_tolerant(self):
        """Exact match should ignore leading/trailing whitespace."""
        self.assertTrue(exact_match("  def foo():\n    pass  ", "def foo():\n    pass"))
    
    def test_exact_match_different(self):
        """Different strings should not match."""
        self.assertFalse(exact_match("def foo():\n    pass", "def bar():\n    pass"))
    
    def test_line_overlap_identical(self):
        """Identical files should have 1.0 overlap."""
        code = "def foo():\n    return 1\n"
        self.assertEqual(line_overlap(code, code), 1.0)
    
    def test_line_overlap_partial(self):
        """Partially matching files should have partial overlap."""
        a = "line1\nline2\nline3"
        b = "line1\nchanged\nline3"
        overlap = line_overlap(a, b)
        self.assertGreater(overlap, 0)
        self.assertLess(overlap, 1)
    
    def test_syntax_valid_good_code(self):
        """Valid Python should pass syntax check."""
        valid, error = check_syntax_valid("def foo():\n    return 42\n")
        self.assertTrue(valid)
        self.assertIsNone(error)
    
    def test_syntax_valid_bad_code(self):
        """Invalid Python should fail syntax check."""
        valid, error = check_syntax_valid("def foo(\n    return 42\n")
        self.assertFalse(valid)
        self.assertIsNotNone(error)
    
    def test_function_preserved_found(self):
        """Function should be found when present."""
        code = "def my_func():\n    return 1\n"
        self.assertTrue(check_function_preserved(code, "my_func"))
    
    def test_function_preserved_not_found(self):
        """Function should not be found when absent."""
        code = "def other_func():\n    return 1\n"
        self.assertFalse(check_function_preserved(code, "my_func"))
    
    def test_semantic_similarity_identical(self):
        """Identical ASTs should have 1.0 similarity."""
        code = "def foo():\n    return 1\n"
        self.assertEqual(semantic_similarity(code, code), 1.0)
    
    def test_semantic_similarity_formatting_only(self):
        """Code with only formatting differences should have high similarity."""
        a = "def foo():\n    return 1"
        b = "def foo():\n    return 1\n"
        sim = semantic_similarity(a, b)
        self.assertEqual(sim, 1.0)


class TestLLMJudge(unittest.TestCase):
    """Tests for LLM judge interface."""
    
    def setUp(self):
        self.dataset = get_dataset()
    
    @patch('llm_judges.judges.LLMClient.generate_json')
    def test_judge_returns_structured_result(self, mock_generate):
        """Judge should return a JudgeResult object."""
        mock_generate.return_value = {
            "is_correct": True,
            "score": 5.0,
            "reason": "The change was applied correctly."
        }
        
        ex = self.dataset[0]
        result = judge_apply_quality(
            original_file=ex.original_file,
            user_prompt=ex.user_prompt,
            applied_file=ex.target_file,
            target_file=ex.target_file,
            model_name="test-model"
        )
        
        self.assertIsInstance(result, JudgeResult)
        self.assertTrue(result.is_correct)
        self.assertEqual(result.score, 5.0)
        self.assertEqual(result.model_name, "test-model")
    
    @patch('llm_judges.judges.LLMClient.generate_json')
    def test_judge_handles_failure(self, mock_generate):
        """Judge should handle API failures gracefully."""
        mock_generate.side_effect = Exception("API Error")
        
        ex = self.dataset[0]
        result = judge_apply_quality(
            original_file=ex.original_file,
            user_prompt=ex.user_prompt,
            applied_file=ex.target_file,
            target_file=ex.target_file,
            model_name="test-model"
        )
        
        # Should return a result with error info, not crash
        self.assertIsInstance(result, JudgeResult)
        self.assertFalse(result.is_correct)
        self.assertEqual(result.score, 0.0)
        self.assertIn("Failed", result.reason)


class TestSpecificFailureModes(unittest.TestCase):
    """Tests for specific failure modes in the dataset."""
    
    def test_decorator_not_handled(self):
        """Verify that decorators are not handled by naive apply."""
        # Example 9: fibonacci with decorator
        original = """import functools

@functools.lru_cache(maxsize=128)
def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
"""
        model_output = """@functools.lru_cache(maxsize=256)
def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
"""
        target = """import functools

@functools.lru_cache(maxsize=256)
def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
"""
        
        edit = ModelEdit(function_name="fibonacci", new_function_code=model_output)
        applied = apply_replace_function(original, edit)
        
        # Should NOT match because decorator handling is broken
        self.assertFalse(exact_match(applied, target))
        # But the function should still be preserved
        self.assertTrue(check_function_preserved(applied, "fibonacci"))
    
    def test_wrong_function_name_not_found(self):
        """Verify that wrong function name results in no change."""
        original = """def validate_input(data):
    return data is not None
"""
        model_output = """def validate(data):
    return data is not None and len(data) > 0
"""
        
        edit = ModelEdit(function_name="validate", new_function_code=model_output)
        applied = apply_replace_function(original, edit)
        
        # Should return original unchanged
        self.assertEqual(applied, original)
    
    def test_similar_function_names_correct_replacement(self):
        """Verify that similar function names are matched exactly (not by prefix)."""
        original = """def process():
    return "base"

def process_data():
    return "data"

def process_data_async():
    return "async"
"""
        model_output = """def process_data():
    return "DATA"
"""
        
        edit = ModelEdit(function_name="process_data", new_function_code=model_output)
        applied = apply_replace_function(original, edit)
        
        # The correct function should be replaced
        self.assertIn('return "DATA"', applied)
        # Other functions should be preserved (not replaced)
        self.assertIn('def process():', applied)
        self.assertIn('return "base"', applied)
        self.assertIn('def process_data_async():', applied)
        self.assertIn('return "async"', applied)
        # The function should be preserved
        self.assertTrue(check_function_preserved(applied, "process_data"))


if __name__ == '__main__':
    unittest.main()
