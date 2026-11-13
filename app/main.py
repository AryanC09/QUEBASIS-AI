# 're' is Python's regex tool for searching strings.
import re

# 'uuid' creates unique ID strings.
import uuid

# 'Path' helps us work with folder directories cleanly.
from pathlib import Path

# FastAPI is the web framework we are using. It creates the server and handles internet requests.
# 'Depends' allows us to run security checks before fulfilling a request. 
# 'HTTPException' crashes the request to show a web error (like a 404). 
# 'Request' grabs the raw incoming web request.
from fastapi import FastAPI, Depends, HTTPException, Request

# These return HTML web pages (instead of just raw JSON data) to the user's browser.
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# 'StaticFiles' lets FastAPI serve standard web files like CSS, images, and Javascript.
from fastapi.staticfiles import StaticFiles

# Pydantic validates incoming data. It makes sure user input perfectly matches the data types we expect.
from pydantic import BaseModel, Field

# We import all the custom modules we built earlier in the project.
from app.observability import initialize
from app.demo_context import principal, Principal
from app.aws import client
from app.config import settings
from app.db import connection, audit
from app.rag import chat
from app.guardrails import check_input, classify_input
from app.memory import history, save_turn, list_messages
from worker.ingest import process_s3_key

# We start our telemetry/tracing system.
initialize()


# BASE finds the absolute folder path where this exact Python file lives.
BASE = Path(__file__).resolve().parent

# We create our web server application. This is the core object of FastAPI.
app = FastAPI(title='Atlas Enterprise RAG', docs_url='/api/docs')

# We tell FastAPI to look in the 'static' folder to serve CSS and Javascript files.
app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')

# We point Jinja2 (the HTML template engine) to our 'templates' folder.
templates = Jinja2Templates(directory=BASE / 'templates')


# These Pydantic classes act as strict bouncers for incoming data.
class Upload(BaseModel):
    # Field() enforces rules: the filename must be between 1 and 180 characters long.
    filename: str = Field(min_length=1, max_length=180)

class Ask(BaseModel):
    # The user's question must be between 3 and 2000 characters.
    question: str = Field(min_length=3, max_length=2000)
    
    # 'uuid.UUID | None = None' means the conversation ID is optional. If missing, it defaults to None.
    conversation_id: uuid.UUID | None = None

class Feedback(BaseModel):
    document_id: str | None = None
    
    # The rating must be between -1 (greater than or equal to/ge) and 1 (less than or equal to/le).
    rating: int = Field(ge=-1, le=1)
    note: str = Field(default='', max_length=500)



# This tells FastAPI: "When someone visits the home page ('/'), run this function."
# We specify that the response is going to be HTML, not JSON.
@app.get('/', response_class=HTMLResponse)
def home(request: Request):
    # This renders the 'index.html' template and injects some variables into it (like the aws_region).
    return templates.TemplateResponse('index.html', {
        'request': request, 
        'region': settings().aws_region,
        'mode': 'single-workspace demo'
    })


# Health checks allow cloud servers to constantly ping our app to see if it crashed.
@app.get('/health/live')
def live(): 
    return {'status': 'alive'}


@app.get('/health/ready')
def ready():
    # 'ready' does a deeper check. It attempts to connect to the database.
    try:
        with connection() as conn: 
            conn.execute('SELECT 1').fetchone()
        return {'status': 'ready'}
    except Exception as exc:
        # If the DB connection fails, we throw an HTTP 503 Service Unavailable error.
        raise HTTPException(503, 'Database unavailable') from exc



# When a user wants to upload a file, they POST to this endpoint.
# 'body: Upload' runs the data through the Pydantic validator we built above.
# 'p: Principal = Depends(principal)' runs our security check and fetches the logged-in user's info.
@app.post('/api/documents/uploads')
def create_upload(body: Upload, p: Principal = Depends(principal)):
    # Grab the file extension and make it lowercase.
    suffix = Path(body.filename).suffix.lower()
    
    # Python sets (using { }) are very fast at checking if an item exists inside them.
    if suffix not in {'.pdf', '.docx', '.txt', '.md'}:
        raise HTTPException(400, 'Allowed types: PDF, DOCX, TXT, MD')
        
    # Generate a brand new, totally random ID for this document.
    doc_id = str(uuid.uuid4())
    
    # Build the exact file path where it will be saved in Amazon S3.
    key = f'tenants/{p.tenant}/incoming/{doc_id}/v1{suffix}'
    
    with connection() as conn:
        # Save a new 'pending' record in the database for this document.
        conn.execute('''INSERT INTO documents(id,tenant_id,title,owner_sub,allowed_groups,s3_key,status,current_version)
                        VALUES (%s,%s,%s,%s,%s,%s,'pending',1)''',
                        (doc_id, p.tenant, body.filename, p.subject, ["workspace"], key))
        audit(conn, p.subject, p.tenant, 'upload_requested', {'document_id': doc_id})
        
    # We ask AWS for a "Presigned URL". This is a secure, temporary, 5-minute (300 sec) ticket 
    # that allows the user's web browser to upload the file directly to S3 without going through our server.
    url = client('s3').generate_presigned_url('put_object', Params={
        'Bucket': settings().s3_bucket,
        'Key': key, 
        'ContentType': 'application/octet-stream'
    }, ExpiresIn=300)
    
    # Return the special URL ticket back to the browser.
    return {'document_id': doc_id, 'upload_url': url, 'headers': {'Content-Type': 'application/octet-stream'}}


class CompleteUpload(BaseModel):
    document_id: uuid.UUID

# Once the browser finishes uploading directly to S3, it calls this endpoint to tell us it's done.
@app.post('/api/documents/complete')
def complete_upload(body: CompleteUpload, p: Principal = Depends(principal)):
    
    with connection() as conn:
        row = conn.execute("""SELECT s3_key,status FROM documents WHERE id=%s AND tenant_id=%s""",
                           (body.document_id, p.tenant)).fetchone()
                           
    if not row: 
        raise HTTPException(404, 'Document not found')
    if row['status'] == 'ready': 
        return {'status': 'ready'}
    if row['status'] == 'processing': 
        raise HTTPException(409, 'Already processing')
        
    try:
        # We manually trigger the worker function we wrote earlier to process and chunk the file.
        process_s3_key(row['s3_key'])
    except Exception as exc:
        raise HTTPException(502, 'Ingestion failed. Check server logs and document status.') from exc
        
    return {'status': 'ready'}


# This endpoint gets a list of all documents the user is allowed to see.
@app.get('/api/documents')
def documents(p: Principal = Depends(principal)):
    with connection() as conn:
        # The '&&' symbol in Postgres SQL means "do these arrays overlap?". 
        # It checks if any of the user's security groups match the document's allowed groups.
        rows = conn.execute('''SELECT id,title,status,current_version,created_at,allowed_groups FROM documents
            WHERE tenant_id=%s AND (allowed_groups && %s::text[] OR owner_sub=%s)
            ORDER BY created_at DESC LIMIT 100''', (p.tenant, list(p.groups), p.subject)).fetchall()
            
    return {'documents': rows}


# The main endpoint where the user asks the AI a question.
@app.post('/api/chat')
def ask(body: Ask, p: Principal = Depends(principal)):
    # Run the question through our custom security guardrails first.
    reason = classify_input(body.question)
    if reason:
        with connection() as conn:
            audit(conn, p.subject, p.tenant, 'guardrail_input_blocked', {'reason': reason})
        raise HTTPException(400, f'Input guardrail blocked this request ({reason}).')
        
    # "HITL" means Human-In-The-Loop. If enabled, and the user asks to do something destructive...
    if settings().hitl_enabled and any(x in body.question.lower() for x in ('delete', 'export', 'send to', 'update policy')):
        with connection() as conn:
            # We pause the request, save it to an 'approvals' table, and tell the user an admin needs to review it.
            row = conn.execute('INSERT INTO approvals(tenant_id,requester,question,status) VALUES (%s,%s,%s,%s) RETURNING id',
                               (p.tenant, p.subject, body.question, 'pending')).fetchone()
            audit(conn, p.subject, p.tenant, 'approval_requested', {'id': str(row['id'])})
            
        return {
            'answer': 'This request requires administrator approval before any action. Open the Approvals tab to review it.',
            'sources': [], 'status': 'pending_approval', 'approval_id': str(row['id'])
        }
        
    # Get the ID of the ongoing conversation, or create a brand new one if this is the first message.
    conversation_id = body.conversation_id or uuid.uuid4()
    
    # Fetch the history, run the AI LangGraph workflow (chat), and save the new turn to the database.
    prior = history(p.tenant, conversation_id)
    result = chat(p, body.question, prior)
    save_turn(p.tenant, conversation_id, body.question, result['answer'])
    
    # If the AI accidentally generated a secret password, our guardrails will have replaced the answer with this exact string.
    if result.get('answer') == 'The response was blocked by the sensitive-data output guardrail.':
        with connection() as conn:
            audit(conn, p.subject, p.tenant, 'guardrail_output_blocked', {'conversation_id': str(conversation_id)})
        result['status'] = 'guardrail_blocked'
        result['sources'] = []
        
    # The '**' unpacks the dictionary. It merges the result dictionary and the conversation ID into one final dictionary.
    return {**result, 'conversation_id': str(conversation_id)}


@app.get('/api/conversations/{conversation_id}/messages')
def conversation_messages(conversation_id: uuid.UUID, p: Principal = Depends(principal)):
    # This calls our memory function to return the full chat log for this conversation.
    return {'conversation_id': str(conversation_id), 'messages': list_messages(p.tenant, conversation_id)}

@app.post('/api/feedback')
def feedback(body: Feedback, p: Principal = Depends(principal)):
    with connection() as conn:
        conn.execute('INSERT INTO feedback(tenant_id,actor,rating,note) VALUES (%s,%s,%s,%s)',
                     (p.tenant, p.subject, body.rating, body.note))
    return {'saved': True}

@app.get('/api/admin/metrics')
def metrics(p: Principal = Depends(principal)):
    with connection() as conn:
        # GROUP BY counts how many documents have each status (e.g., 5 'ready', 2 'failed').
        docs = conn.execute('SELECT status,count(*) AS total FROM documents WHERE tenant_id=%s GROUP BY status', (p.tenant,)).fetchall()
        fb = conn.execute('SELECT rating,count(*) AS total FROM feedback WHERE tenant_id=%s GROUP BY rating', (p.tenant,)).fetchall()
    return {'documents': docs, 'feedback': fb}


class ApprovalDecision(BaseModel):
    approve: bool
    
@app.get('/api/approvals')
def list_approvals(p: Principal = Depends(principal)):
    # Security check: you must be flagged as an admin to see this list.
    if not p.admin: 
        raise HTTPException(403, 'Admin only')
        
    with connection() as conn:
        rows = conn.execute("SELECT id,requester,question,status,reviewer,created_at,reviewed_at FROM approvals WHERE tenant_id=%s ORDER BY created_at DESC LIMIT 100", (p.tenant,)).fetchall()
    return {'approvals': rows}


@app.post('/api/approvals/{approval_id}/decision')
def decide(approval_id: uuid.UUID, body: ApprovalDecision, p: Principal = Depends(principal)):
    # Admin security check.
    if not p.admin: 
        raise HTTPException(403, 'Admin only')
        
    with connection() as conn:
        # We update the approval ticket to either 'approved' or 'rejected'.
        row = conn.execute("UPDATE approvals SET status=%s,reviewer=%s,reviewed_at=now() WHERE id=%s AND tenant_id=%s AND status='pending' RETURNING id",
                           ('approved' if body.approve else 'rejected', p.subject, approval_id, p.tenant)).fetchone()
                           
        if not row: 
            raise HTTPException(404, 'Pending approval not found')
            
        audit(conn, p.subject, p.tenant, 'approval_decided', {'id': str(approval_id), 'approved': body.approve})
        
    # Approval is a decision record only; it never automatically executes a destructive action.
    return {'status': 'approved' if body.approve else 'rejected', 'executed': False}

@app.get('/api/admin/guardrails')
def guardrail_metrics(p: Principal = Depends(principal)):
    if not p.admin: 
        raise HTTPException(403, 'Admin only')
        
    with connection() as conn:
        # We query the audit table to count exactly how many times our custom guardrails have tripped.
        rows = conn.execute("""SELECT action,count(*) AS total FROM audit_events
            WHERE tenant_id=%s AND action IN ('guardrail_input_blocked','guardrail_output_blocked')
            GROUP BY action ORDER BY action""", (p.tenant,)).fetchall()
            
    return {'events': rows, 'mode': 'deterministic_demo', 'managed_bedrock_guardrails': False}