# 'uuid' is a built-in Python tool used to handle Universally Unique Identifiers 
# (those long, random-looking strings of letters and numbers used to identify things safely).
import uuid

# We import the safe database connection tool we built earlier.
from app.db import connection

# We import our app's settings so we can check how much memory the AI is allowed to have.
from app.config import settings

# This function retrieves the most recent chat history for the AI to read.
# 'tenant: str' and 'conversation_id: uuid.UUID' are type hints. They tell us what kind of data to pass in.
def history(tenant: str, conversation_id: uuid.UUID):
    
    # We open a safe connection to the database. The 'with' block ensures it closes automatically.
    with connection() as conn:
        
        # We execute a SQL query. The triple quotes (""") allow us to write a string across multiple lines.
        # This specific SQL does a clever trick: 
        # 1. The inner 'SELECT' grabs the newest messages (ORDER BY id DESC) up to our memory limit.
        # 2. The outer 'SELECT' flips them back into chronological order (ORDER BY id ASC) so the AI reads them naturally.
        rows = conn.execute("""SELECT role,content FROM (
            SELECT id,role,content,created_at FROM chat_messages
            WHERE tenant_id=%s AND conversation_id=%s ORDER BY id DESC LIMIT %s
        ) recent ORDER BY id ASC""", 
        
        # We pass a tuple to fill in the three '%s' placeholders. 
        # settings().memory_turns * 2 calculates how many total messages (questions + answers) to fetch.
        (tenant, conversation_id, settings().memory_turns * 2)).fetchall()
        # .fetchall() tells the database cursor to bring back a list of all the rows it found.
        
    # We return the list of rows to the rest of the program.
    return rows


# This function saves a back-and-forth conversation turn (the user's question and the AI's answer).
def save_turn(tenant: str, conversation_id: uuid.UUID, question: str, response: str):
    
    # Open our safe database connection again.
    with connection() as conn:
        
        # We execute an INSERT command. 
        # We are actually inserting TWO rows at the exact same time into the 'chat_messages' table.
        # The first set of 'VALUES' is for the 'user', and the second set is for the 'assistant'.
        conn.execute("""INSERT INTO chat_messages(tenant_id,conversation_id,role,content)
                        VALUES (%s,%s,'user',%s),(%s,%s,'assistant',%s)""",
                     
                     # We provide a tuple with 6 items to fill in the 6 '%s' placeholders above.
                     (tenant, conversation_id, question, tenant, conversation_id, response))


# This function gets the full chat history to display on the user's screen.
def list_messages(tenant: str, conversation_id: uuid.UUID):
    
    # Open our safe database connection.
    with connection() as conn:
        
        # We execute a straightforward SELECT command to get the messages.
        # 'LIMIT 100' ensures that if a conversation goes on forever, we don't accidentally 
        # crash the web browser by trying to load millions of messages at once.
        return conn.execute("""SELECT role,content,created_at FROM chat_messages
          WHERE tenant_id=%s AND conversation_id=%s ORDER BY id ASC LIMIT 100""",
          
          # We pass the tenant and conversation ID to fill in the two placeholders.
          (tenant, conversation_id)).fetchall()