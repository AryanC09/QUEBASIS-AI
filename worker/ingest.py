# 'io' helps Python work with streams of data, like treating raw memory as if it were a physical file.
import io

# 'logging' is Python's built-in tool for printing out messages, warnings, and errors.
import logging

# 'Path' from pathlib is a great tool for working with file paths and file extensions.
from pathlib import Path

# These are third-party libraries we installed to read Word documents (.docx) and PDF files.
from docx import Document
from pypdf import PdfReader

# We bring in the custom functions we built in our other app files.
from app.aws import client, embed
from app.vector import upsert
from app.config import settings
from app.db import connection, audit
from app.observability import trace, initialize

# This calls the observability setup function we reviewed earlier to start tracing.
initialize()

# This configures how our logs will look. 
# %(asctime)s adds a timestamp, %(levelname)s adds the severity (like INFO or ERROR), and %(message)s is our text.
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# We create a specific logger for this "worker" script so we know exactly where log messages came from.
log = logging.getLogger('atlas.worker')


# This function takes the raw binary data (blob) of a file and its file extension (suffix).
# Note: 'blob: bytes' and 'suffix: str' are "type hints". They don't strictly enforce rules in Python, 
# but they help developers know what kind of data is expected.
def parse(blob: bytes, suffix: str):
    
    # If the file is a PDF:
    if suffix == '.pdf':
        # io.BytesIO() tricks the PdfReader into thinking the raw bytes in memory are an actual saved file.
        reader = PdfReader(io.BytesIO(blob))
        
        # This is a List Comprehension. It loops through every page in the PDF.
        # 'enumerate()' is a very common Python tool. It gives us both the index number (i) AND the item (page).
        # We return a list of tuples containing the page number (i+1) and the text on that page.
        return [(i + 1, page.extract_text() or '') for i, page in enumerate(reader.pages)]
        
    # If the file is a Word document:
    if suffix == '.docx':
        doc = Document(io.BytesIO(blob))
        
        # We join all the paragraphs together with a newline character '\n'. 
        # We return a list with just one tuple, assuming the whole document is "page 1".
        return [(1, '\n'.join(p.text for p in doc.paragraphs))]
        
    # If it is a plain text file, we decode the raw bytes into a readable UTF-8 string.
    return [(1, blob.decode('utf-8'))]


# This function breaks long text into smaller overlapping chunks so the AI can read them easily.
def chunks(text, size=1200, overlap=180):
    
    # .split() breaks the text into a list of words, and ' '.join() glues them back together.
    # This is a quick Python trick to remove any extra messy spaces or weird tabs from the text.
    text = ' '.join(text.split())
    pos = 0
    
    # A 'while' loop runs as long as our position is less than the total length of the text.
    while pos < len(text):
        
        # 'yield' makes this function a "Generator". Instead of building a massive list of chunks in memory 
        # and returning them all at once, 'yield' pauses the function and hands back one chunk at a time.
        # text[pos:pos+size] is called "Slicing". It grabs a specific section of the text.
        yield text[pos:pos+size]
        
        # If our slice reached the end of the text, we break out of the loop completely.
        if pos + size >= len(text): 
            break
            
        # We move our position forward by the chunk size, minus the overlap, so the next chunk 
        # repeats a little bit of the end of this one (keeping the context intact).
        pos += size - overlap


# We wrap our main worker function with our custom tracer tool.
@trace("process_s3_key")
def process_s3_key(key):
    s = settings()
    
    # We open a database connection using our custom context manager (the 'with' block).
    with connection() as conn:
        
        # We run a SQL query. 'FOR UPDATE' tells the database to lock this specific row 
        # so no other worker scripts can try to process the exact same file at the same time.
        doc = conn.execute('SELECT * FROM documents WHERE s3_key=%s FOR UPDATE', (key,)).fetchone()
        
        # If the document doesn't exist, or is already 'ready', we stop ('return') immediately.
        if not doc or doc['status'] == 'ready': 
            return
            
        # If it is currently being processed or was retired, we also stop.
        if doc['status'] not in ('pending', 'failed'): 
            return
            
        # We update the database to show we are currently working on it.
        conn.execute("UPDATE documents SET status='processing' WHERE id=%s", (doc['id'],))
        
    try:
        # We ask AWS S3 to give us the file using the specific 'key' (the file path in S3).
        obj = client('s3').get_object(Bucket=s.s3_bucket, Key=key)
        
        # We check the file size in the metadata before downloading to ensure it isn't too huge.
        if obj['ContentLength'] > s.max_upload_bytes: 
            raise ValueError('Upload too large')
            
        # We read the raw file data stream.
        blob = obj['Body'].read(s.max_upload_bytes + 1)
        
        # We double-check the downloaded size just in case the metadata lied.
        if len(blob) > s.max_upload_bytes: 
            raise ValueError('Upload too large')
            
        # Path(key).suffix extracts the file extension. .lower() makes it lowercase.
        # b'%PDF' is a raw Byte String. We check if a PDF file actually starts with the official PDF byte signature.
        if Path(key).suffix.lower() == '.pdf' and not blob.startswith(b'%PDF'): 
            raise ValueError('Invalid PDF')
            
        # We call our parse() function from the top of the file to get our list of pages.
        pages = parse(blob, Path(key).suffix.lower())
        
        # This is a nested List Comprehension. It goes through every page, and then chunks the text on that page, 
        # building a final flat list of tuples containing the (page_number, text_chunk).
        parts = [(page, part) for page, text in pages for part in chunks(text)]
        
        # If the file had no readable text (like a scanned image), we throw an error.
        if not parts: 
            raise ValueError('No extractable text; scanned PDFs need Textract OCR')
            
        # We create an empty list to hold our AI vectors.
        vectors = []
        
        # We loop through our chunks. We build a dictionary for each chunk containing its unique ID, 
        # its AI math vector (by calling the 'embed' function), and its descriptive metadata.
        for i, (page, part) in enumerate(parts):
            vectors.append({
                'id': f'{doc["id"]}:{doc["current_version"]}:{i}',
                'values': embed(part),
                'metadata': {
                    'document_id': str(doc['id']),
                    'title': doc['title'],
                    'page': page,
                    'text': part,
                    'owner_sub': doc['owner_sub'],
                    'allowed_groups': doc['allowed_groups']
                }
            })
            
        # Keep batches small; Pinecone metadata must fit the index's limits.
        # The range() function here uses 3 arguments: start(0), stop(total length), step(50).
        # This loops by 50s. vectors[i:i+50] slices out 50 items at a time and sends them to the Pinecone database.
        for i in range(0, len(vectors), 50): 
            upsert(doc['tenant_id'], vectors[i:i+50])
            
        # If everything worked, we open the database again and mark the file as 'ready'.
        with connection() as conn:
            conn.execute("UPDATE documents SET status='ready' WHERE id=%s", (doc['id'],))
            
            # We log an official audit event saying the document was successfully ingested.
            audit(conn, doc['owner_sub'], doc['tenant_id'], 'ingest_ready', {'document_id': str(doc['id']), 'chunks': len(parts)})
            
        # We print a success message to our logs.
        log.info('Ingested document %s chunks=%d', doc['id'], len(parts))
        
    except Exception:
        # If literally anything goes wrong in the 'try' block, we catch it here.
        # log.exception() prints the exact error so we can fix the bug later.
        log.exception('Ingestion failed for key %s', key)
        
        # We connect to the database one last time to mark the document as 'failed' so it isn't stuck 'processing' forever.
        with connection() as conn:
            conn.execute("UPDATE documents SET status='failed' WHERE id=%s", (doc['id'],))
            
        # 'raise' by itself takes the error we just caught and throws it again, officially crashing this worker job.
        raise
