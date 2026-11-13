"""Initialize Atlas tables in Render PostgreSQL from infra/schema.sql.

Usage (from project root): python scripts/init_db.py
Safe to rerun: the supplied schema uses CREATE ... IF NOT EXISTS.
"""
# pathlib helps us easily build and read file paths across different operating systems (Windows, Mac, Linux).
from pathlib import Path

# sys provides access to some variables used or maintained by the Python interpreter, like exiting a program.
import sys

# psycopg is our installed library for talking to PostgreSQL databases.
import psycopg

# load_dotenv reads key-value pairs from a .env file and adds them to environment variables.
from dotenv import load_dotenv

# os gives us a way to interact with the operating system, like reading those environment variables.
import os

# __file__ is a special Python variable that holds the path to this specific script.
# .resolve() gets the absolute path, and .parents[1] goes up one directory level to find the project root.
ROOT = Path(__file__).resolve().parents[1]

# This automatically finds the secret '.env' file in the ROOT folder and loads its contents into memory.
load_dotenv(ROOT / '.env')

# We build the exact file path to our SQL file by combining the ROOT path with folder names using the '/' operator.
SCHEMA = ROOT / 'infra' / 'schema.sql'

# This is a 'Tuple' (created using parentheses). It is an ordered list of strings that cannot be changed.
REQUIRED = ('documents', 'feedback', 'audit_events', 'approvals', 'chat_messages')


def main():
    # os.getenv grabs the DATABASE_URL secret. If it's missing, it defaults to an empty string ''.
    # .strip() removes any accidental spaces from the beginning or end of the text.
    url = os.getenv('DATABASE_URL', '').strip()
    
    # Python checks if 'url' is empty (falsy) or if it still contains placeholder text from the template.
    if not url or 'YOUR_' in url or 'USERNAME:' in url:
        print('ERROR: Set a real DATABASE_URL in the project .env file.')
        return 1 # Returning 1 tells the operating system that this script failed.
        
    # .is_file() checks if the SQL schema file actually exists at the path we built earlier.
    if not SCHEMA.is_file():
        print(f'ERROR: Schema not found: {SCHEMA}')
        return 1
        
    print('Connecting to Render PostgreSQL (credentials hidden)...')
    
    # 'try' tells Python to attempt this code. If a crash happens, jump to the 'except' block below.
    try:
        # The 'with' statement safely opens the database connection and guarantees it will close when done.
        with psycopg.connect(url, connect_timeout=15) as conn:
            
            # Execute as one transaction: either the schema succeeds or it rolls back.
            with conn.transaction():
                # .read_text() grabs all the text inside the schema.sql file.
                # conn.execute() runs that text directly on the database.
                conn.execute(SCHEMA.read_text(encoding='utf-8'))
                
            # A cursor is a tool that allows Python to execute queries and fetch the results line by line.
            with conn.cursor() as cur:
                
                # Ask the database what its current name is.
                cur.execute('SELECT current_database()')
                
                # .fetchone() returns the first row of results as a tuple. We use [0] to grab the first item inside it.
                dbname = cur.fetchone()[0]
                
                # Check if the chat_messages table exists. 
                # VERY IMPORTANT: Note the trailing comma in ('public.chat_messages',).
                # Python needs that comma to know it is a Tuple with one item, not just a string inside math parentheses.
                cur.execute('SELECT to_regclass(%s)', ('public.chat_messages',))
                if cur.fetchone()[0] is None:
                    # 'raise' manually triggers a crash (an exception) with our custom error message.
                    raise RuntimeError('chat_messages table was not created')
                    
                # A 'for' loop goes through every item in our REQUIRED tuple one by one.
                for table in REQUIRED:
                    # We use an f-string (f'...') to easily inject the table variable into the string.
                    cur.execute('SELECT to_regclass(%s)', (f'public.{table}',))
                    
                    if cur.fetchone()[0] is None:
                        raise RuntimeError(f'Missing table: {table}')
                        
        # The '!r' inside {dbname!r} tells Python to print the name with quotes around it (the repr() format).
        print(f'SUCCESS: Database {dbname!r} initialized; verified {len(REQUIRED)} tables.')
        print('You can safely rerun this script. Existing rows are preserved.')
        return 0 # Returning 0 tells the operating system the script succeeded.
        
    # If any error happened inside the 'try' block, it gets caught here in the variable 'exc'.
    except Exception as exc:
        # type(exc).__name__ prints the specific type of error (like 'RuntimeError' or 'ConnectionError').
        print(f'ERROR: Database initialization failed: {type(exc).__name__}: {exc}')
        return 1

# This is a standard Python idiom. It means: "If I am running this script directly from the terminal, execute main()."
# sys.exit() takes the 0 or 1 returned by main() and passes it to the operating system.
if __name__ == '__main__':
    sys.exit(main())
