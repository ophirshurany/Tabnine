"""
Dataset Builder for Apply Code Changes Evaluation

This module provides a diverse dataset designed to stress-test the apply mechanism
with various levels of difficulty and realistic failure modes.

Key Design Principles:
1. model_output is SEPARATE from target_file - allows testing imperfect inputs
2. Examples range from easy (perfect output) to adversarial (designed to break naive apply)
3. Tags allow filtering and analysis by failure mode
4. expected_success indicates whether we expect the apply to work
"""

from typing import List
from models import DatasetExample, DifficultyLevel


def get_dataset() -> List[DatasetExample]:
    """Return the list of evaluation examples with varying difficulty levels."""
    examples = []

    # =========================================================================
    # EASY EXAMPLES: Perfect model output, simple functions
    # These should all succeed - baseline for the apply mechanism
    # =========================================================================

    examples.append(DatasetExample(
        id=1,
        original_file="""def foo(x):
    return x + 1
""",
        target_file="""def foo(x):
    return x + 2
""",
        model_output="""def foo(x):
    return x + 2
""",
        user_prompt="Change foo to add 2 instead of 1.",
        expected_function_name="foo",
        difficulty=DifficultyLevel.EASY,
        expected_success=True,
        tags=["simple", "return-value-change"]
    ))

    examples.append(DatasetExample(
        id=2,
        original_file="""def check_positive(n):
    if n > 0:
        return True
    return False
""",
        target_file="""def check_positive(n):
    if n >= 0:
        return True
    return False
""",
        model_output="""def check_positive(n):
    if n >= 0:
        return True
    return False
""",
        user_prompt="Make check_positive return True for 0 as well.",
        expected_function_name="check_positive",
        difficulty=DifficultyLevel.EASY,
        expected_success=True,
        tags=["simple", "condition-change"]
    ))

    # =========================================================================
    # MEDIUM EXAMPLES: Minor imperfections in model output
    # Tests the apply mechanism's tolerance for formatting differences
    # =========================================================================

    # Example 3: Model output has trailing whitespace
    examples.append(DatasetExample(
        id=3,
        original_file="""def calculate_area(radius):
    pi = 3.14
    return pi * radius * radius
""",
        target_file="""def calculate_area(radius):
    import math
    return math.pi * radius * radius
""",
        model_output="""def calculate_area(radius):
    import math
    return math.pi * radius * radius   
""",  # Note: trailing spaces on last line
        user_prompt="Use math.pi instead of hardcoded 3.14 in calculate_area.",
        expected_function_name="calculate_area",
        difficulty=DifficultyLevel.MEDIUM,
        expected_success=True,  # Should still work, just with trailing whitespace
        tags=["whitespace", "trailing-spaces"]
    ))

    # Example 4: Model output missing final newline
    examples.append(DatasetExample(
        id=4,
        original_file="""def process_data(data):
    result = []
    for item in data:
        result.append(item * 2)
    return result
""",
        target_file="""def process_data(data):
    print(f"Processing {len(data)} items")
    result = []
    for item in data:
        result.append(item * 2)
    return result
""",
        model_output="""def process_data(data):
    print(f"Processing {len(data)} items")
    result = []
    for item in data:
        result.append(item * 2)
    return result""",  # No final newline
        user_prompt="Add a print statement to show the number of items being processed.",
        expected_function_name="process_data",
        difficulty=DifficultyLevel.MEDIUM,
        expected_success=True,
        tags=["whitespace", "missing-newline"]
    ))

    # Example 5: Model output has extra blank lines
    examples.append(DatasetExample(
        id=5,
        original_file="""def cleanup(text):
    text = text.strip()
    # TODO: remove special characters
    text = text.lower()
    return text
""",
        target_file="""def cleanup(text):
    text = text.strip()
    text = text.lower()
    return text
""",
        model_output="""def cleanup(text):
    text = text.strip()

    text = text.lower()

    return text
""",  # Extra blank lines
        user_prompt="Remove the TODO comment from cleanup.",
        expected_function_name="cleanup",
        difficulty=DifficultyLevel.MEDIUM,
        expected_success=False,  # Apply works, but won't exact match due to extra blank lines
        failure_reason="Model output has extra blank lines that don't match target",
        tags=["whitespace", "extra-blank-lines"]
    ))

    # =========================================================================
    # HARD EXAMPLES: Significant issues that challenge the apply mechanism
    # =========================================================================

    # Example 6: Wrong indentation (tabs vs spaces)
    examples.append(DatasetExample(
        id=6,
        original_file="""def sum_evens(nums):
    total = 0
    for n in nums:
        if n % 2 == 0:
            total += n
    return total
""",
        target_file="""def sum_evens(nums):
    return sum(n for n in nums if n % 2 == 0)
""",
        model_output="""def sum_evens(nums):
\treturn sum(n for n in nums if n % 2 == 0)
""",  # Tab instead of spaces
        user_prompt="Rewrite sum_evens to use a generator expression with sum().",
        expected_function_name="sum_evens",
        difficulty=DifficultyLevel.HARD,
        expected_success=False,  # Apply works, but indentation mismatch causes diffh causes diff
        failure_reason="Tab/space mismatch in indentation",
        tags=["indentation", "tabs-vs-spaces"]
    ))

    # Example 7: Model output has wrong base indentation (not at column 0)
    examples.append(DatasetExample(
        id=7,
        original_file="""def is_valid_email(email):
    return "@" in email
""",
        target_file="""def is_valid_email(email):
    return "@" in email and "." in email
""",
        model_output="""    def is_valid_email(email):
        return "@" in email and "." in email
""",  # Entire function indented by 4 spaces
        user_prompt="Update is_valid_email to also check for a dot.",
        expected_function_name="is_valid_email",
        difficulty=DifficultyLevel.HARD,
        expected_success=False,  # Model output has wrong base indentation
        failure_reason="Model output has incorrect base indentation",
        tags=["indentation", "base-indent"]
    ))

    # Example 8: Multi-function file - must not affect other functions
    examples.append(DatasetExample(
        id=8,
        original_file="""def helper():
    return 42

def greet(name):
    return f"Hello, {name}"

def farewell(name):
    return f"Goodbye, {name}"
""",
        target_file="""def helper():
    return 42

def greet(name):
    '''Returns a greeting message.'''
    return f"Hello, {name}"

def farewell(name):
    return f"Goodbye, {name}"
""",
        model_output="""def greet(name):
    '''Returns a greeting message.'''
    return f"Hello, {name}"
""",
        user_prompt="Add a docstring to the greet function.",
        expected_function_name="greet",
        difficulty=DifficultyLevel.HARD,
        expected_success=False,  # Blank line between functions is lost
        failure_reason="Apply mechanism doesn't preserve blank lines between functions",
        tags=["multi-function", "docstring", "whitespace"]
    ))

    # Example 9: Function with decorator
    examples.append(DatasetExample(
        id=9,
        original_file="""import functools

@functools.lru_cache(maxsize=128)
def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
""",
        target_file="""import functools

@functools.lru_cache(maxsize=256)
def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
""",
        model_output="""@functools.lru_cache(maxsize=256)
def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
""",
        user_prompt="Increase the cache size to 256.",
        expected_function_name="fibonacci",
        difficulty=DifficultyLevel.HARD,
        expected_success=False,  # Naive apply won't handle decorator properly
        failure_reason="Decorator not included in function detection",
        tags=["decorator", "edge-case"]
    ))

    # Example 10: Nested function - edit the outer function
    examples.append(DatasetExample(
        id=10,
        original_file="""def outer(x):
    def inner(y):
        return y * 2
    return inner(x)
""",
        target_file="""def outer(x):
    def inner(y):
        return y * 3
    return inner(x)
""",
        model_output="""def outer(x):
    def inner(y):
        return y * 3
    return inner(x)
""",
        user_prompt="Change the inner function to multiply by 3 instead of 2.",
        expected_function_name="outer",
        difficulty=DifficultyLevel.HARD,
        expected_success=True,
        tags=["nested-function"]
    ))

    # =========================================================================
    # ADVERSARIAL EXAMPLES: Edge cases designed to break naive implementations
    # =========================================================================

    # Example 11: Function name appears in string/comment
    examples.append(DatasetExample(
        id=11,
        original_file="""# This module contains calculate_tax function
def calculate_tax(p):
    '''calculate_tax computes tax on price p'''
    rate = 0.2
    return p * rate
""",
        target_file="""# This module contains calculate_tax function
def calculate_tax(price):
    '''calculate_tax computes tax on price'''
    rate = 0.2
    return price * rate
""",
        model_output="""def calculate_tax(price):
    '''calculate_tax computes tax on price'''
    rate = 0.2
    return price * rate
""",
        user_prompt="Rename parameter 'p' to 'price' in calculate_tax.",
        expected_function_name="calculate_tax",
        difficulty=DifficultyLevel.ADVERSARIAL,
        expected_success=True,  # Should work, but tests that we find the right "def"
        tags=["name-in-string", "parameter-rename"]
    ))

    # Example 12: Similar function names
    examples.append(DatasetExample(
        id=12,
        original_file="""def process():
    return "base"

def process_data():
    return "data"

def process_data_async():
    return "async"
""",
        target_file="""def process():
    return "base"

def process_data():
    return "DATA"

def process_data_async():
    return "async"
""",
        model_output="""def process_data():
    return "DATA"
""",
        user_prompt="Make process_data return uppercase 'DATA'.",
        expected_function_name="process_data",
        difficulty=DifficultyLevel.ADVERSARIAL,
        expected_success=False,  # Blank line between functions is lost
        failure_reason="Apply mechanism doesn't preserve blank lines between functions",
        tags=["similar-names", "exact-match-required", "whitespace"]
    ))

    # Example 13: Function not found (model hallucinates wrong name)
    examples.append(DatasetExample(
        id=13,
        original_file="""def validate_input(data):
    return data is not None
""",
        target_file="""def validate_input(data):
    return data is not None and len(data) > 0
""",
        model_output="""def validate(data):
    return data is not None and len(data) > 0
""",  # Wrong function name!
        user_prompt="Also check that data is not empty.",
        expected_function_name="validate",  # This won't be found
        difficulty=DifficultyLevel.ADVERSARIAL,
        expected_success=False,
        failure_reason="Model output has wrong function name",
        tags=["wrong-name", "model-error"]
    ))

    # Example 14: Syntax error in model output
    examples.append(DatasetExample(
        id=14,
        original_file="""def divide(a, b):
    return a / b
""",
        target_file="""def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
""",
        model_output="""def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero"
    return a / b
""",  # Missing closing paren - syntax error
        user_prompt="Add a check for division by zero.",
        expected_function_name="divide",
        difficulty=DifficultyLevel.ADVERSARIAL,
        expected_success=False,  # Apply works, but result has syntax error so not "successful"
        failure_reason="Model output has syntax error",
        tags=["syntax-error", "model-error"]
    ))

    # Example 15: Class method (not standalone function)
    examples.append(DatasetExample(
        id=15,
        original_file="""class Calculator:
    def __init__(self):
        self.result = 0
    
    def add(self, x):
        self.result += x
        return self
    
    def get_result(self):
        return self.result
""",
        target_file="""class Calculator:
    def __init__(self):
        self.result = 0
    
    def add(self, x):
        self.result += x
        return self
    
    def subtract(self, x):
        self.result -= x
        return self
    
    def get_result(self):
        return self.result
""",
        model_output="""    def subtract(self, x):
        self.result -= x
        return self
""",  # This is an INSERT, not a replace - naive apply won't handle it
        user_prompt="Add a subtract method to Calculator.",
        expected_function_name="subtract",
        difficulty=DifficultyLevel.ADVERSARIAL,
        expected_success=False,
        failure_reason="Adding new method requires insert, not replace",
        tags=["class-method", "insert-not-replace"]
    ))

    # Example 16: Empty function body
    examples.append(DatasetExample(
        id=16,
        original_file="""def placeholder():
    pass
""",
        target_file="""def placeholder():
    return "implemented"
""",
        model_output="""def placeholder():
    return "implemented"
""",
        user_prompt="Implement the placeholder function to return 'implemented'.",
        expected_function_name="placeholder",
        difficulty=DifficultyLevel.EASY,
        expected_success=True,
        tags=["pass-statement", "simple"]
    ))

    # Example 17: Function with type hints
    examples.append(DatasetExample(
        id=17,
        original_file="""from typing import List, Optional

def find_max(numbers: List[int]) -> Optional[int]:
    if not numbers:
        return None
    return max(numbers)
""",
        target_file="""from typing import List, Optional

def find_max(numbers: List[int], default: int = 0) -> int:
    if not numbers:
        return default
    return max(numbers)
""",
        model_output="""def find_max(numbers: List[int], default: int = 0) -> int:
    if not numbers:
        return default
    return max(numbers)
""",
        user_prompt="Add a default parameter and change return type.",
        expected_function_name="find_max",
        difficulty=DifficultyLevel.MEDIUM,
        expected_success=True,
        tags=["type-hints", "signature-change"]
    ))

    # Example 18: Async function
    examples.append(DatasetExample(
        id=18,
        original_file="""import asyncio

async def fetch_data(url):
    await asyncio.sleep(1)
    return {"url": url, "data": "sample"}
""",
        target_file="""import asyncio

async def fetch_data(url, timeout=30):
    await asyncio.sleep(1)
    return {"url": url, "data": "sample", "timeout": timeout}
""",
        model_output="""async def fetch_data(url, timeout=30):
    await asyncio.sleep(1)
    return {"url": url, "data": "sample", "timeout": timeout}
""",
        user_prompt="Add a timeout parameter to fetch_data.",
        expected_function_name="fetch_data",
        difficulty=DifficultyLevel.MEDIUM,
        expected_success=True,
        tags=["async", "parameter-add"]
    ))

    # Example 19: Long function with many lines
    examples.append(DatasetExample(
        id=19,
        original_file="""def complex_calculation(data):
    # Step 1: Validate
    if not data:
        return None
    
    # Step 2: Transform
    result = []
    for item in data:
        if isinstance(item, int):
            result.append(item * 2)
        elif isinstance(item, str):
            result.append(item.upper())
        else:
            result.append(str(item))
    
    # Step 3: Aggregate
    total = sum(x for x in result if isinstance(x, int))
    strings = [x for x in result if isinstance(x, str)]
    
    # Step 4: Return
    return {
        "total": total,
        "strings": strings,
        "count": len(result)
    }
""",
        target_file="""def complex_calculation(data):
    # Step 1: Validate
    if not data:
        return {"total": 0, "strings": [], "count": 0}
    
    # Step 2: Transform
    result = []
    for item in data:
        if isinstance(item, int):
            result.append(item * 2)
        elif isinstance(item, str):
            result.append(item.upper())
        else:
            result.append(str(item))
    
    # Step 3: Aggregate
    total = sum(x for x in result if isinstance(x, int))
    strings = [x for x in result if isinstance(x, str)]
    
    # Step 4: Return
    return {
        "total": total,
        "strings": strings,
        "count": len(result)
    }
""",
        model_output="""def complex_calculation(data):
    # Step 1: Validate
    if not data:
        return {"total": 0, "strings": [], "count": 0}
    
    # Step 2: Transform
    result = []
    for item in data:
        if isinstance(item, int):
            result.append(item * 2)
        elif isinstance(item, str):
            result.append(item.upper())
        else:
            result.append(str(item))
    
    # Step 3: Aggregate
    total = sum(x for x in result if isinstance(x, int))
    strings = [x for x in result if isinstance(x, str)]
    
    # Step 4: Return
    return {
        "total": total,
        "strings": strings,
        "count": len(result)
    }
""",
        user_prompt="Return a proper empty result dict instead of None when data is empty.",
        expected_function_name="complex_calculation",
        difficulty=DifficultyLevel.MEDIUM,
        expected_success=True,
        tags=["long-function", "early-return"]
    ))

    # Example 20: Partial code from model (incomplete function)
    examples.append(DatasetExample(
        id=20,
        original_file="""def merge_dicts(dict1, dict2):
    result = dict1.copy()
    result.update(dict2)
    return result
""",
        target_file="""def merge_dicts(dict1, dict2, overwrite=True):
    result = dict1.copy()
    if overwrite:
        result.update(dict2)
    else:
        for k, v in dict2.items():
            if k not in result:
                result[k] = v
    return result
""",
        model_output="""def merge_dicts(dict1, dict2, overwrite=True):
    result = dict1.copy()
    if overwrite:
        result.update(dict2)
    else:
        for k, v in dict2.items():
            if k not in result:
                result[k] = v
    # ... rest of function
""",  # Incomplete - model used placeholder
        user_prompt="Add an overwrite parameter to control merge behavior.",
        expected_function_name="merge_dicts",
        difficulty=DifficultyLevel.ADVERSARIAL,
        expected_success=False,  # Apply works, but result is incomplete
        failure_reason="Model output is incomplete (has placeholder comment)",
        tags=["incomplete", "model-error"]
    ))

    return examples


def get_dataset_by_difficulty(difficulty: DifficultyLevel) -> List[DatasetExample]:
    """Filter dataset by difficulty level."""
    return [ex for ex in get_dataset() if ex.difficulty == difficulty]


def get_dataset_by_tags(tags: List[str]) -> List[DatasetExample]:
    """Filter dataset by tags (returns examples that have ANY of the specified tags)."""
    return [ex for ex in get_dataset() if any(t in ex.tags for t in tags)]


def get_expected_failures() -> List[DatasetExample]:
    """Get examples where we expect the apply mechanism to fail."""
    return [ex for ex in get_dataset() if not ex.expected_success]


def export_to_jsonl(path: str) -> None:
    """Export the dataset to a JSONL file at the given path."""
    import json
    examples = get_dataset()
    with open(path, 'w', encoding='utf-8') as f:
        for ex in examples:
            f.write(ex.model_dump_json() + '\n')


def print_dataset_summary() -> None:
    """Print a summary of the dataset."""
    examples = get_dataset()
    print(f"Total examples: {len(examples)}")
    print("\nBy difficulty:")
    for diff in DifficultyLevel:
        count = len([e for e in examples if e.difficulty == diff])
        print(f"  {diff.value}: {count}")
    
    print("\nExpected outcomes:")
    success = len([e for e in examples if e.expected_success])
    failure = len([e for e in examples if not e.expected_success])
    print(f"  Expected success: {success}")
    print(f"  Expected failure: {failure}")
    
    print("\nTags distribution:")
    all_tags = {}
    for ex in examples:
        for tag in ex.tags:
            all_tags[tag] = all_tags.get(tag, 0) + 1
    for tag, count in sorted(all_tags.items(), key=lambda x: -x[1]):
        print(f"  {tag}: {count}")


if __name__ == "__main__":
    print_dataset_summary()
