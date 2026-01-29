from models import ModelEdit

def apply_replace_function(original_file: str, edit: ModelEdit) -> str:
    """
    Naively replace the implementation of a single function in a Python file.

    Logic:
    1. Finds the line starting with `def {function_name}(` (ignoring leading spaces).
    2. Determines the end of the function block based on indentation.
    3. Replaces the entire block with `edit.new_function_code`.

    Args:
        original_file: The full content of the file.
        edit: The ModelEdit object containing the function name and new code.

    Returns:
        The modified file content.
    """
    lines = original_file.splitlines(keepends=True) # Keep newlines to preserve file structure exactly
    n = len(lines)

    # Find function start
    start_idx = None
    file_indent = None 
    
    # We search for "def function_name(" or "async def function_name("
    target_def = f"def {edit.function_name}("
    target_async_def = f"async def {edit.function_name}("
    
    for i, line in enumerate(lines):
        # Naive check: does stripped line start with the def?
        # This might match "def my_func_helper" if looking for "def my_func", so be careful.
        # Ideally we check for word boundary, but sticking to requested simple logic:
        # "Locate the function definition line: a line whose stripped text starts with def {function_name}(."
        stripped = line.lstrip()
        if stripped.startswith(target_def) or stripped.startswith(target_async_def):
            start_idx = i
            base_indent = len(line) - len(stripped)
            break

    if start_idx is None:
        # Function not found; return original.
        print(f"Warning: Function '{edit.function_name}' not found in file.")
        return original_file

    # Find function end
    # "Scan forward until: A non-empty line with indentation less than or equal to the function’s base indentation, or End of file."
    end_idx = start_idx + 1
    while end_idx < n:
        line = lines[end_idx]
        stripped = line.strip()
        
        # Empty lines (whitespace only) are considered part of the function (or at least don't terminate it)
        # unless followed by a dedent. 
        # Standard python parsing relies on the next non-empty line.
        if stripped: # If line is not empty
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent:
                break
        end_idx += 1

    # Prepare new lines
    # edit.new_function_code comes as a string, potentially without matching indentation of the file context if extracted poorly,
    # but usually "ideal" extraction preserves it, or model output might generally have 0 indent.
    # The requirement says: "Replace the original function block with edit.new_function_code."
    # We will just dump it in. If formatting is off, that's a model/pipeline issue for later.
    
    # Ensure new_function_code ends with newline if the original file context usually expects it, 
    # but let's just use what's given + ensure separation.
    new_code = edit.new_function_code
    if not new_code.endswith('\n'):
        new_code += '\n'
        
    # Construct result
    # lines[:start_idx] includes everything before the def
    # new_code is the replacement
    # lines[end_idx:] is everything after
    
    # helper to join list of strings
    prefix = "".join(lines[:start_idx])
    suffix = "".join(lines[end_idx:])
    
    return prefix + new_code + suffix


def extract_function_block(file_content: str, function_name: str) -> str:
    """
    Extract the full function block for `function_name` from `file_content`
    using the same indentation-based logic as apply_replace_function.
    
    Returns empty string if not found.
    """
    lines = file_content.splitlines(keepends=True)
    n = len(lines)
    
    target_def = f"def {function_name}("
    target_async_def = f"async def {function_name}("
    
    start_idx = None
    base_indent = 0
    
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith(target_def) or stripped.startswith(target_async_def):
            start_idx = i
            base_indent = len(line) - len(stripped)
            break
            
    if start_idx is None:
        return ""
        
    end_idx = start_idx + 1
    while end_idx < n:
        line = lines[end_idx]
        stripped = line.strip()
        if stripped:
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent:
                break
        end_idx += 1
        
    return "".join(lines[start_idx:end_idx])
