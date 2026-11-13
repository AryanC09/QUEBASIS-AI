# Import our custom tracing tool to log when functions start and stop.
from app.observability import trace

# 'logging' is Python's built-in tool for printing structured messages (like INFO or ERROR).
import logging

# 'time' lets us interact with the computer's clock and pause the program.
import time

# 'lru_cache' remembers the result of a function so Python doesn't repeat heavy work.
from functools import lru_cache

# We import the tools needed to talk to Pinecone, which is a specialized database for AI math (vectors).
from pinecone import Pinecone, ServerlessSpec

# We bring in our app's configuration settings.
from app.config import settings

# This sets up a logger specifically for this file. 
# '__name__' automatically fills in the name of the current file.
log = logging.getLogger(__name__)


# @lru_cache(maxsize=1) tells Python to save the result of this function. 
# maxsize=1 means it only needs to remember one thing (the database connection). 
# The next time we call index(), it instantly returns the saved connection instead of rebuilding it.
@lru_cache(maxsize=1)
def index():
    """Return an initialized Pinecone index. Safe for repeated requests in one process."""
    
    # Load our settings.
    s = settings()
    
    # Check if the required secrets are missing. If they are, crash the program with an error.
    if not s.pinecone_api_key:
        raise RuntimeError("PINECONE_API_KEY is missing from .env")
    if not s.pinecone_index_name:
        raise RuntimeError("PINECONE_INDEX_NAME is missing from .env")
        
    # Create the main connection to Pinecone using our API key.
    pc = Pinecone(api_key=s.pinecone_api_key)
    name = s.pinecone_index_name
    
    # We use a 'try' block because asking for an index that doesn't exist yet will cause an error.
    try:
        # Describe rather than list: avoids listing every index and works for existing indexes.
        info = pc.describe_index(name)
        
    # If an error happens, it is caught here in the 'exc' (exception) variable.
    except Exception as exc:
        
        # 'getattr' safely checks if the error has a 'status' code attached to it.
        # A 404 status means "Not Found". If the error is NOT 404 (like a wifi failure), 
        # the 'raise' command immediately throws the error and stops the program.
        if getattr(exc, 'status', None) != 404:
            raise
            
        # If we made it here, the index simply doesn't exist yet, so we log that we are creating it.
        log.info('Creating Pinecone index %s (dimension=%d, metric=cosine)', name, s.embed_dim)
        
        try:
            # We tell Pinecone to create the new database index with our specific AI dimensions.
            pc.create_index(name=name, dimension=s.embed_dim, metric='cosine',
                            spec=ServerlessSpec(cloud=s.pinecone_cloud, region=s.pinecone_region))
                            
        # We catch a potential error during creation in 'create_exc'.
        except Exception as create_exc:
            # A 409 error means "Conflict". This happens if two parts of our app try to create 
            # the index at the exact same millisecond. If it's not a 409, we crash ('raise').
            if getattr(create_exc, 'status', None) != 409:
                raise
                
        # Now that it is definitely created, we fetch its info.
        info = pc.describe_index(name)
        
    # We double-check that the database's dimension size matches what our AI expects.
    # int() makes sure the dimension is a whole number.
    if int(info.dimension) != s.embed_dim:
        raise ValueError(f'Pinecone index {name} dimension={info.dimension}, expected {s.embed_dim}. '
                         'Use a different index name or matching EMBED_DIM.')
                         
    # We double-check that the database is using the correct math formula ('cosine').
    # str().lower() makes sure the word is text and all lowercase before checking.
    if str(info.metric).lower() != 'cosine':
        raise ValueError(f'Pinecone index {name} must use cosine metric, got {info.metric}')
        
    # time.monotonic() gets the computer's current internal clock time in seconds.
    # We add our timeout limit (e.g., 60 seconds) to create a deadline in the future.
    deadline = time.monotonic() + s.pinecone_ready_timeout
    
    # A 'while' loop keeps repeating as long as the database status is NOT 'ready'.
    while not pc.describe_index(name).status['ready']:
        # If the current time passes our deadline, we give up and crash with a TimeoutError.
        if time.monotonic() >= deadline:
            raise TimeoutError(f'Pinecone index {name} was not ready within {s.pinecone_ready_timeout}s')
            
        # time.sleep(3) pauses our Python script for 3 seconds so we don't spam the database with checks.
        time.sleep(3)
        
    log.info('Pinecone index %s ready', name)
    
    # Finally, we return the fully initialized and ready-to-use database connection.
    return pc.Index(name)


def namespace(tenant):
    # In Python, the '+' symbol glues strings together. 
    # If tenant is "apple", this returns "tenant-apple".
    return 'tenant-' + tenant


# We wrap this function with our custom tracing tool to monitor it.
@trace("upsert")
def upsert(tenant, records):
    # index() gets our cached database connection. 
    # .upsert() means "Update or Insert". It saves our records into the database.
    return index().upsert(vectors=records, namespace=namespace(tenant))


@trace("search")
def search(tenant, vector, groups, owner, limit=5):
    # This creates a complex Dictionary for filtering security permissions.
    # It tells the database: "Only return files if the user is in the 'allowed_groups' list, 
    # OR ('$or') if the user is the exact 'owner' of the file."
    acl = {'$or': [{'allowed_groups': {'$in': list(groups)}},
                   {'owner_sub': {'$eq': owner}}]}
                   
    # We ask the database to query (search) using our AI vector, returning the top matches.
    result = index().query(vector=vector, top_k=limit, include_metadata=True,
                           namespace=namespace(tenant), filter=acl)
                           
    # This is a classic Python "List Comprehension". It is a powerful shortcut to build a new list.
    # It loops through every match 'm' in our results, creates a new dictionary for each one 
    # with just the 'id', 'score', and 'metadata', and puts them all into a fresh list to return.
    return [{'id': m.id, 'score': m.score, 'metadata': m.metadata or {}}
            for m in result.matches]


def delete_document(tenant, ids):
    # Empty lists in Python evaluate to 'False'. 
    # So 'if ids:' means "If the list of IDs is not empty, run the code below."
    if ids:
        # We tell the database to delete the specific IDs from this tenant's namespace.
        index().delete(ids=ids, namespace=namespace(tenant))