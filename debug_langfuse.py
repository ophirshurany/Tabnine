from langfuse import Langfuse
import inspect

try:
    l = Langfuse(public_key='pk', secret_key='sk', base_url='https://example.com')
    print(f"Object type: {type(l)}")
    print(f"Dir: {dir(l)}")
    print(f"Methods: {[m for m in dir(l) if callable(getattr(l, m))]}")
    
    if hasattr(l, 'trace'):
        print("trace method exists")
    else:
        print("trace method MISSING")
        
except Exception as e:
    print(f"Error: {e}")
