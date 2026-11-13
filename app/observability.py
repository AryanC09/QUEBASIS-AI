# A docstring (multi-line string) at the top of a file explains what the entire file is meant to do.
"""Privacy-first Rius tracing. No telemetry is sent without RIUS_API_KEY."""

# 'os' is a built-in Python module that lets us interact with the operating system (like reading environment variables).
import os

# 'logging' is Python's built-in tool for printing messages. It is better than 'print()' 
# because it can add timestamps and filter messages by importance (like INFO, WARNING, or ERROR).
import logging

# 'wraps' is a tool used when building decorators. (Note: It is imported here but not actually used in the code below!)
from functools import wraps

# This creates a logger specifically for this file. 
# '__name__' is a special Python variable that automatically holds the name of the current file.
log = logging.getLogger(__name__)

def initialize():
    """Call once, before instrumented app modules are loaded."""
    
    # We import load_dotenv inside the function instead of at the top of the file.
    # This is called a "lazy import". It saves memory if this function is never actually called.
    from dotenv import load_dotenv
    
    # This loads secret variables from our hidden '.env' file into the computer's memory.
    load_dotenv()
    
    # This 'if' statement checks two things using the 'or' keyword:
    # 1. Is the RIUS_API_KEY missing?
    # 2. Is the RIUS_DISABLED variable set to "1", "true", or "yes"? 
    # .lower() makes the string lowercase so "TRUE", "True", and "true" all match correctly.
    if not os.getenv("RIUS_API_KEY") or os.getenv("RIUS_DISABLED", "false").lower() in ("1", "true", "yes"):
        # We use our logger to print a harmless INFO message saying tracing is turned off.
        log.info("Rius observability disabled (no key or kill switch)")
        # 'return' immediately stops the function here.
        return
        
    # 'try' means Python will attempt to run this block of code.
    try:
        # We try to import the third-party 'rius' library.
        import rius
        
        # We initialize it. Notice 'capture_content=False'. This ensures we don't accidentally 
        # send sensitive user data (like passwords or private messages) to the telemetry server.
        rius.init(service_name=os.getenv("RIUS_SERVICE_NAME", "quebasisai"), capture_content=False)
        
        log.info("Rius observability enabled")
        
    # 'except Exception' catches absolutely any error that happens in the 'try' block (like if 'rius' isn't installed).
    except Exception:
        # log.exception() prints the exact error message so we can debug it, 
        # but the program will safely continue running instead of crashing.
        log.exception("Rius initialization failed; application will continue without telemetry")

# This is a custom decorator factory. It creates the @trace("something") tag you used in the previous code.
def trace(name):
    """Decorate sync/async functions; never export arguments or return values."""
    
    # A decorator works by wrapping another function (here called 'fn') inside a new function.
    def decorate(fn):
        try:
            # We try to import the 'rius' library again.
            import rius
            
            # If rius is available, we use its built-in 'observe' feature to wrap our function.
            # We explicitly set input and output capturing to False for privacy.
            return rius.observe(name=name, capture_input=False, capture_output=False)(fn)
            
        # ImportError specifically catches the error where the 'rius' library isn't installed on the computer.
        except ImportError:
            # This is brilliant: if the library isn't installed, it just returns the original function untouched.
            # This means the app will still work perfectly fine even if the tracing tools are missing!
            return fn
            
    # The trace function returns the decorate function, which then wraps our actual code.
    return decorate