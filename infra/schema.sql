-- Make a table for information about uploaded documents, unless it already exists.
CREATE TABLE IF NOT EXISTS documents (
 id uuid PRIMARY KEY, -- Gives each document a unique ID.
 tenant_id text NOT NULL, -- Says which customer or organization the document belongs to.
 title text NOT NULL, -- Stores the document's name.
 owner_sub text NOT NULL, -- Stores the ID of the person who owns the document.
 allowed_groups text[] NOT NULL, -- Lists the groups allowed to see the document.
 s3_key text NOT NULL UNIQUE, -- Stores the document's unique location in Amazon S3.
 status text NOT NULL CHECK(status IN ('pending','processing','ready','failed','retired')), -- Tracks the document's state and only allows these choices.
 current_version integer NOT NULL DEFAULT 1, -- Stores the current version number, starting at 1.
 created_at timestamptz NOT NULL DEFAULT now() -- Records when the document row was created.
); -- Finishes setting up the documents table.
-- Add a quick-lookup list for finding documents by customer and status.
CREATE INDEX IF NOT EXISTS documents_acl_idx ON documents(tenant_id,status);
-- Make a table for feedback people leave about the app.
CREATE TABLE IF NOT EXISTS feedback (
 id bigserial PRIMARY KEY, -- Gives each feedback entry a unique, automatically increasing ID.
 tenant_id text NOT NULL, -- Says which customer or organization sent the feedback.
 actor text NOT NULL, -- Stores who sent the feedback.
 rating integer NOT NULL CHECK(rating BETWEEN -1 AND 1), -- Stores a score of -1, 0, or 1 only.
 note text NOT NULL, -- Stores the person's written comment.
 created_at timestamptz NOT NULL DEFAULT now() -- Records when the feedback was added.
); -- Finishes setting up the feedback table.
-- Make a table for a record of actions that happened in the app.
CREATE TABLE IF NOT EXISTS audit_events (
 id bigserial PRIMARY KEY, -- Gives each recorded action a unique, automatically increasing ID.
 actor text NOT NULL, -- Stores who performed the action.
 tenant_id text NOT NULL, -- Says which customer or organization the action belongs to.
 action text NOT NULL, -- Stores the name of the action that happened.
 detail jsonb NOT NULL, -- Stores extra details about the action in JSON format.
 created_at timestamptz NOT NULL DEFAULT now() -- Records when the action happened.
); -- Finishes setting up the audit events table.
-- Add a quick-lookup list to find an organization's newest events first.
CREATE INDEX IF NOT EXISTS audit_tenant_time ON audit_events(tenant_id,created_at DESC);

-- Make a table for questions that need someone to review and approve them.
CREATE TABLE IF NOT EXISTS approvals (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), -- Makes a unique ID automatically for each approval request.
 tenant_id text NOT NULL, -- Says which customer or organization made the request.
 requester text NOT NULL, -- Stores who asked for approval.
 question text NOT NULL, -- Stores the question that needs review.
 status text NOT NULL DEFAULT 'pending', -- Tracks the review state and starts as waiting for review.
 reviewer text, -- Stores who reviewed it; it can be empty until someone reviews it.
 created_at timestamptz NOT NULL DEFAULT now(), -- Records when the request was made.
 reviewed_at timestamptz -- Records when it was reviewed; it can be empty before review.
); -- Finishes setting up the approvals table.
-- Add a quick-lookup list for finding approval requests by organization and status.
CREATE INDEX IF NOT EXISTS approvals_tenant_idx ON approvals(tenant_id,status);

-- Make a table that keeps recent chat messages in the Aurora database.
CREATE TABLE IF NOT EXISTS chat_messages (
 id bigserial PRIMARY KEY, -- Gives each message a unique, automatically increasing ID.
 tenant_id text NOT NULL, -- Says which customer or organization the conversation belongs to.
 conversation_id uuid NOT NULL, -- Groups this message with the rest of its conversation.
 role text NOT NULL CHECK(role IN ('user','assistant')), -- Says whether the message came from the user or the assistant.
 content text NOT NULL, -- Stores the words in the message.
 created_at timestamptz NOT NULL DEFAULT now() -- Records when the message was added.
); -- Finishes setting up the chat messages table.
-- Add a quick-lookup list to get one organization's newest messages in a conversation.
CREATE INDEX IF NOT EXISTS chat_messages_session_idx ON chat_messages(tenant_id,conversation_id,id DESC);
