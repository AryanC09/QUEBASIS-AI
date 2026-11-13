# We bring in our custom tracking tool to monitor how long our functions take to run.
from app.observability import trace

# 'typing' helps us define what kind of data to expect in our code. 
# 'TypedDict' lets us build a dictionary with specific expected keys, and 'Any' means a value can be any data type.
from typing import TypedDict, Any

# 'langgraph' is a third-party library for building AI workflows. 
# It acts like a flowchart. We import the main graph builder, and the START and END points of the flowchart.
from langgraph.graph import StateGraph, START, END

# We bring in the AI functions we built earlier to talk to AWS.
from app.aws import embed, answer

# We bring in the search function we built earlier to search our Pinecone database.
from app.vector import search

# We bring in our application's settings and passwords.
from app.config import settings

# We bring in our custom security tools to make sure the user isn't typing bad questions.
from app.guardrails import check_input, check_output


# We create a blueprint for the "State". The State is the memory dictionary passed between every step of our flowchart.
# 'total=False' means that a state dictionary doesn't have to contain every single one of these keys at all times.
class State(TypedDict, total=False):
    question: str
    principal: Any
    passages: list
    answer: str
    sources: list
    status: str
    history: list


# This is the first step in our flowchart. It checks the user's question for safety.
@trace("guard")
def guard(s): 
    # It takes the current state ('s'), runs the question through our security check, 
    # and returns the updated safe question back into the state memory to replace the old one.
    return {'question': check_input(s['question'])}


# This step searches our database for documents related to the user's question.
@trace("retrieve")
def retrieve(s):
    # 'principal' holds the user's login info (like their tenant ID and what security groups they belong to).
    p = s['principal']
    
    # This is a List Comprehension. It loops through the chat history and grabs only the messages sent by the 'user'.
    # We use .get('history', []) so that if the history is completely empty, it defaults to a safe empty list [].
    prior_questions = [m['content'] for m in s.get('history', []) if m['role'] == 'user']
    
    # If there are prior questions, we glue the very last one ([-1]) to the current question so the AI has context.
    # If there is no history, we just use the current question by itself.
    query = (prior_questions[-1] + '\nFollow-up: ' + s['question']) if prior_questions else s['question']
    
    # We turn the text query into math (embed) and search the database, making sure the user is allowed to see the results.
    hits = search(p.tenant, embed(query), p.groups, p.subject)
    
    # We filter the search results. We only keep the hits that score higher than our minimum relevance setting.
    hits = [h for h in hits if h['score'] >= settings().min_relevance]
    
    # We build a list of sources so we can show the user exactly where the AI got its information.
    # We safely grab metadata using .get() so the program doesn't crash if a piece of info is missing.
    sources = [{'index': i + 1, 'document_id': h['metadata'].get('document_id', ''), 
                'title': h['metadata'].get('title', ''), 'page': h['metadata'].get('page', 1), 
                'excerpt': h['metadata'].get('text', '')[:320]} for i, h in enumerate(hits)]
                
    # We return the found passages and the source citations to be saved into the state memory.
    return {'passages': hits, 'sources': sources}


# This is a "routing" function. It acts like a traffic cop to decide which path the flowchart should take next.
def route(s): 
    # If we found passages, go to the 'generate' step. If the passages list is empty, go to 'no_evidence'.
    return 'generate' if s['passages'] else 'no_evidence'


# If no documents were found, this step creates a standard apology message.
@trace("no_evidence")
def no_evidence(s): 
    return {'answer': 'I could not find supporting evidence in documents you are authorized to access.', 
            'status': 'no_evidence'}


# If we did find documents, this step asks the AI to read them and generate an answer.
@trace("generate")
def generate(s):
    # We glue all the found text passages together into one giant string so the AI can read it.
    # We use an f-string to format it nicely with the document title and page number.
    evidence = '\n\n'.join(f'[{i+1}] {h["metadata"].get("title", "Document")}, page {h["metadata"].get("page", 1)}: {h["metadata"].get("text", "")}' 
                           for i, h in enumerate(s['passages']))
                           
    # We send the question, the evidence, and the chat history to our AWS AI model, and return its text answer.
    return {'answer': answer(s['question'], evidence, s.get('history', [])), 
            'status': 'answered'}


# This is the final step. It checks the AI's generated answer to make sure it didn't say anything unsafe or hallucinatory.
@trace("validate")
def validate(s): 
    return {'answer': check_output(s['answer'])}


# This function builds our actual LangGraph flowchart using the steps we defined above.
def make_graph():
    # Create a new graph that uses our 'State' blueprint for its memory.
    g = StateGraph(State)
    
    # We loop through a list of our step names and functions, adding each one as a "node" (a box in the flowchart).
    for name, fn in [('guard', guard), ('retrieve', retrieve), ('no_evidence', no_evidence), 
                     ('generate', generate), ('validate', validate)]:
        g.add_node(name, fn)
        
    # We draw lines (edges) connecting the boxes. START goes to 'guard', and 'guard' goes to 'retrieve'.
    g.add_edge(START, 'guard')
    g.add_edge('guard', 'retrieve')
    
    # From 'retrieve', we use our traffic cop function 'route' to decide conditionally where to go next based on its rules.
    g.add_conditional_edges('retrieve', route, {'generate': 'generate', 'no_evidence': 'no_evidence'})
    
    # 'generate' flows into 'validate'. Both 'validate' and 'no_evidence' flow to the END of the graph.
    g.add_edge('generate', 'validate')
    g.add_edge('validate', END)
    g.add_edge('no_evidence', END)
    
    # .compile() locks the graph in and gets it ready to run.
    return g.compile()


# We run the builder function once and save the finished graph into a global variable.
graph = make_graph()


# This is the main function our web server will call when a user types a message.
@trace("chat")
def chat(p, question, history=None):
    # graph.invoke() runs the entire flowchart from START to END.
    # We pass in the initial state memory containing the user, their question, and the chat history.
    r = graph.invoke({'principal': p, 'question': question, 'history': history or []})
    
    # Once the flowchart is finished, we return the final answer, sources, and status back to the user.
    return {'answer': r['answer'], 'sources': r.get('sources', []), 'status': r.get('status', 'answered')}