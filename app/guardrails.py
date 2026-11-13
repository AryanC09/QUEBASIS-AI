# A docstring summarizing the file's purpose: protecting the app from bad inputs.
"""Conservative, deterministic demo guardrails. Not a substitute for IAM or auth."""

# 're' is Python's built-in tool for "Regular Expressions" (searching text for specific patterns).
import re

# We import a special error tool from FastAPI (our web framework) to send HTTP error codes (like 400 or 404).
from fastapi import HTTPException

# This is a list of text patterns hackers might use to try and trick the AI (Prompt Injection).
# The 'r' before the quotes means it is a "raw string". This tells Python not to get confused 
# by special characters like backslashes (\b or \s) which are heavily used in regex patterns.
INJECTION = [
    r"\bignore\s+(?:all\s+|any\s+|the\s+|previous\s+|prior\s+)?(?:instructions|rules|system\s+prompt)\b",
    r"\b(?:reveal|print|show|dump|disclose)\s+(?:your\s+|the\s+|hidden\s+|internal\s+)*(?:system|developer)\s+(?:prompt|instructions)\b",
    r"\b(?:reveal|print|dump|expose|send)\s+(?:your\s+|all\s+|the\s+)*(?:api\s*keys?|passwords?|credentials?|secrets?|access\s+tokens?)\b",
    r"\b(?:bypass|disable|turn\s+off)\s+(?:all\s+|the\s+)?(?:guardrails|safety\s+checks|security\s+controls)\b",
    r"\b(?:pretend|act)\s+(?:you\s+are|as\s+if\s+you\s+are)\s+(?:the\s+)?(?:system|developer|administrator)\b",
]

# This is a list of patterns to catch if the AI accidentally tries to print out secret passwords.
SENSITIVE_OUTPUT = [
    # re.compile() prepares the regex pattern in advance so it runs faster when checking lots of text.
    # re.I (or re.IGNORECASE) makes the search case-insensitive so it catches both "KEY" and "key".
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I),
    
    # AKIA and ASIA are standard prefixes for Amazon Web Services (AWS) secret keys.
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    
    # This catches if the AI tries to print out our database URL or other specific API keys.
    re.compile(r"(?i)\b(?:aws_secret_access_key|pinecone_api_key|database_url)\s*[:=]\s*\S+"),
    re.compile(r"(?i)\b(?:password|api[_ -]?key|secret[_ -]?key)\s*[:=]\s*[\"']?[^\s\"']{12,}"),
]


# This creates a custom Error type for our program. 
# It inherits from Python's built-in 'ValueError'.
class GuardrailBlocked(ValueError):
    # 'pass' is a placeholder keyword in Python. It means "do nothing, I just needed an empty block here."
    pass


# The '-> str | None' is a Type Hint. It tells other programmers this function 
# will return either a string (the reason it was blocked) or 'None' (meaning it's safe).
def classify_input(question: str) -> str | None:
    
    # question.strip() removes invisible spaces. If the user just typed spaces, we classify it as 'empty_input'.
    if not question or not question.strip():
        return 'empty_input'
        
    # any() is a built-in Python function that returns True if at least one item inside it is True.
    # We loop through our INJECTION list. re.search() checks if the bad pattern exists anywhere in the user's question.
    if any(re.search(pattern, question, re.I) for pattern in INJECTION):
        return 'prompt_injection_or_secret_request'
        
    # If no bad patterns were found, return None (it passed the test).
    return None


def check_input(question: str) -> str:
    # We call our classify function to see if the question broke any rules.
    reason = classify_input(question)
    
    # In Python, if a variable has text in it, it evaluates to True. If it is 'None', it evaluates to False.
    if reason:
        # If there is a reason, we crash the web request with an HTTP 400 (Bad Request) error.
        raise HTTPException(status_code=400, detail=f'Input guardrail blocked this request ({reason}).')
        
    # If it is safe, we just return the original question untouched.
    return question


def contains_sensitive_output(text: str) -> bool:
    # We use 'text or ""' to make sure we don't accidentally pass 'None' into the regex search.
    # any() checks if at least one of our compiled SENSITIVE_OUTPUT patterns matches the text.
    return any(pattern.search(text or '') for pattern in SENSITIVE_OUTPUT)


def check_output(answer: str) -> str:
    if contains_sensitive_output(answer):
        # Instead of crashing the program, we replace the AI's answer with a safe error message 
        # so the secret data never gets sent back to the user's screen.
        return 'The response was blocked by the sensitive-data output guardrail.'
        
    return answer


def check_evidence(text: str) -> str:
    """Label retrieved document passages as untrusted. Never follow embedded instructions."""
    
    # We don't delete user documents or discard factual content based on regex.
    # Right now, this function just passes the text right back, but having it here 
    # gives us a dedicated place to add document-scanning rules in the future.
    return text