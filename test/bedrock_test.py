import os  # Lets the program read settings stored in environment variables.
import json  # Lets the program convert Python data to and from JSON text.
import boto3  # Provides the AWS SDK used to call Amazon Bedrock.
from dotenv import load_dotenv  # Imports the helper that loads settings from a .env file.

load_dotenv()  # Reads values from the local .env file into environment variables.

# 1. Fixed variable name 'client' & 2. Fixed 'aws_access_key_id' spelling
client = boto3.client(  # Creates a connection object for calling Bedrock.
    "bedrock-runtime",  # Selects the Bedrock Runtime service.
    region_name=os.getenv("AWS_REGION"),  # Uses the AWS region set in the environment.
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),  # Uses the configured AWS access key.
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),  # Uses the configured AWS secret key.
)  # Finishes creating the Bedrock connection.

# TEST: AMAZON TITAN EMBEDDINGS
embedding_response = client.invoke_model(  # Sends a request to the chosen embedding model.
    modelId=os.getenv("BEDROCK_EMBED_MODEL"),  # Gets the embedding model name from the environment.
    body=json.dumps({  # Converts the model's input settings into JSON text.
        "inputText": "Hello Amazon Bedrock",  # Text that the model will turn into numbers.
        "dimensions": 1024,  # Requests an embedding with 1,024 numbers.
        "normalize": True  # Requests a normalized embedding vector.
    }),  # Ends the JSON request body.
    contentType="application/json",  # Tells Bedrock that the request body is JSON.
    accept="application/json"  # Requests the response in JSON format.
)  # Finishes the embedding model request.

embedding_data = json.loads(  # Turns the model's JSON response into a Python dictionary.
    embedding_response["body"].read()  # Reads the response body returned by Bedrock.
)  # Finishes converting the response body from JSON.
print("Embedding dimension: ", len(embedding_data["embedding"]))  # Prints how many numbers are in the embedding.

# AMAZON NOVA LITE TEST
chat_response = client.converse(  # Sends a chat request to the chosen model.
    modelId=os.getenv("BEDROCK_CHAT_MODEL"),  # Gets the chat model name from the environment.
    messages=[  # Starts the list of messages in the conversation.
        {  # Starts one message entry.
            "role": "user",  # Marks this message as coming from the user.
            "content": [  # Starts the content parts of this message.
                {"text": "Explain RAG in one sentence"}  # Provides the question for the model.
            ]  # Ends the message content parts.
        }  # Ends the user message entry.
    ],  # Ends the conversation message list.
    inferenceConfig={"maxTokens": 200}  # Limits the generated answer to 200 tokens.
)  # Finishes the chat model request.

# 4. Fixed 'chat_response' spelling
print(  # Displays the model's answer in the terminal.
    "Nova Response: ",  # Prints a label before the answer.
    chat_response["output"]["message"]["content"][0]["text"]  # Gets the answer text from the response.
)  # Finishes printing the answer.
