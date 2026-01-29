import os
from typing import Optional, Any

# Try to import Langfuse, provide None if missing
try:
    from langfuse import Langfuse
except ImportError:
    Langfuse = None

# Load environment variables
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_BASE_URL = os.getenv("LANGFUSE_BASE_URL")

class NoOpSpan:
    """A no-op span that ignores all calls."""
    def span(self, *args, **kwargs) -> 'NoOpSpan':
        return self

    def start_span(self, *args, **kwargs) -> 'NoOpSpan':
        return self

    def start_observation(self, *args, **kwargs) -> 'NoOpSpan':
        return self

    def update(self, *args, **kwargs) -> 'NoOpSpan':
        return self

    def score(self, *args, **kwargs) -> 'NoOpSpan':
        return self
        
    def score_trace(self, *args, **kwargs) -> 'NoOpSpan':
        return self

    def end(self, *args, **kwargs) -> 'NoOpSpan':
        return self
        
    def event(self, *args, **kwargs) -> 'NoOpSpan':
        return self
        
    def generation(self, *args, **kwargs) -> 'NoOpSpan':
        return self

class NoOpLangfuse:
    """A no-op Langfuse client that returns no-op spans."""
    def trace(self, *args, **kwargs) -> NoOpSpan:
        return NoOpSpan()

    def span(self, *args, **kwargs) -> NoOpSpan:
        return NoOpSpan()

    def start_span(self, *args, **kwargs) -> NoOpSpan:
        return NoOpSpan()

    def start_observation(self, *args, **kwargs) -> NoOpSpan:
        return NoOpSpan()
        
    def score(self, *args, **kwargs) -> Any:
        return None
        
    def flush(self, *args, **kwargs) -> None:
        pass

# Initialize Langfuse or fallback to NoOp
if Langfuse and LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY:
    try:
        langfuse = Langfuse(
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            base_url=LANGFUSE_BASE_URL,
        )
    except Exception as e:
        print(f"Warning: Failed to initialize Langfuse: {e}")
        langfuse = NoOpLangfuse()
else:
    # If dependencies missing or keys not set, use NoOp
    if Langfuse is None:
        pass # specific warning if import failed could be added if desired, but silent fallback is often preferred
    elif not (LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY):
        # Only warn if it looks like they might have wanted it but missed keys? 
        # Or just stay silent to avoid noise in non-instrumented envs.
        pass
    langfuse = NoOpLangfuse()
