# 'import' is like '#include' in C/C++ or 'import' in Java. 
# We are bringing in a built-in tool to handle JSON text formatting.
import json

# Python lets us import specific functions from a library using 'from X import Y'. 
# 'contextmanager' is a tool that helps automatically manage opening and closing resources.
from contextlib import contextmanager

# psycopg is a third-party library we installed. It is the driver that lets Python talk to PostgreSQL.
import psycopg

# We import a specific setting that tells the database to return rows as Key-Value pairs (dictionaries) 
# instead of standard arrays (tuples).
from psycopg.rows import dict_row

# This imports the 'settings' class from a file named 'config.py' located in the 'app' folder of our project.
from app.config import settings

# The '@' symbol is called a 'decorator'. It modifies the function directly below it. 
# Here, it turns the connection() function into a "Context Manager". This means it will 
# automatically handle closing the database connection for us so we don't cause memory leaks.
@contextmanager
def connection():
    # Render provides a PostgreSQL connection URL. Prefer its external URL
    # for a FastAPI process running on your computer.
    
    # We create an object of the settings class and access its 'database_url' property. 
    # This URL holds the database username, password, and address.
    url = settings().database_url
    
    # In Python, 'if not' checks if a variable is empty, false, or null. 
    if not url:
        # 'raise' is exactly like 'throw' in C++ or Java. It throws an error and stops the program.
        raise RuntimeError("DATABASE_URL is missing from .env")
        
    # The 'with' keyword is very special in Python. It opens the database connection, assigns it 
    # to the variable 'conn', and GUARANTEES that the connection will be safely closed when we are 
    # done with it, even if our program crashes.
    with psycopg.connect(url, row_factory=dict_row, connect_timeout=10) as conn:
        
        # 'yield' is like 'return', but it only pauses the function. 
        # It hands the 'conn' object to whoever called this function. Once that other code is finished 
        # using the database, this function un-pauses, and the 'with' block automatically closes the connection.
        yield conn

# This defines a function that takes 5 arguments. No data types are declared because Python is dynamically typed.
def audit(conn, actor, tenant, action, detail):
    
    # conn.execute() runs a SQL command. 
    # Notice the '%s' symbols? Those are placeholders. We use them instead of directly injecting 
    # variables into the SQL string to protect the database from SQL Injection attacks.
    conn.execute('INSERT INTO audit_events (actor,tenant_id,action,detail) VALUES (%s,%s,%s,%s)',
                 
                 # This comma-separated list provides the variables to fill into those '%s' placeholders.
                 # json.dumps() takes the 'detail' variable and converts it into a JSON-formatted text string.
                 (actor, tenant, action, json.dumps(detail)))
