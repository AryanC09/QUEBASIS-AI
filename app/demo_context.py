# 'dataclasses' is a built-in Python module that saves us from writing boring, repetitive code. 
# It automatically builds the background setup (like constructors) for classes that just hold data.
from dataclasses import dataclass

# The '@dataclass' decorator automatically creates the background code to handle these variables.
# 'frozen=True' makes this class "immutable" (read-only). Once we create a Principal object, 
# no one can accidentally (or maliciously) change its values later in the program. This is great for security!
@dataclass(frozen=True)
class Principal:
    # A "Principal" is a security term representing the user currently using the app.
    
    # We use Type Hints (like ': str') to say what kind of data this should be.
    # We also provide default fallback values (like = "demo-operator").
    subject: str = "demo-operator"
    tenant: str = "demo-workspace"
    
    # 'tuple[str, ...]' means this variable should be a Tuple that contains strings. 
    # The '...' means it can contain any number of strings (one, five, fifty, etc.).
    # Remember the trailing comma in '("workspace",)'! That tells Python it's a Tuple, not just math parentheses.
    groups: tuple[str, ...] = ("workspace",)
    
    # A boolean flag to indicate if this user has administrator privileges.
    admin: bool = True


# This function acts as a quick helper to get the current user.
# The '-> Principal' part is a return Type Hint. It tells other programmers that 
# when they call this function, they will get a 'Principal' object back.
def principal() -> Principal:
    
    # In Python, we create a new object by calling the class name exactly like a function.
    # Because we provided default values for everything up above, we don't need to put anything in the parentheses here.
    return Principal()