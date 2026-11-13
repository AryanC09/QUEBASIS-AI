import os
import json
import boto3
from dotenv import load_dotenv

load_dotenv()

# 1. Fixed variable name 'client' & 2. Fixed 'aws_access_key_id' spelling
client = boto3.client(
    "bedrock-runtime",
    region_name=os.getenv("AWS_REGION"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)

# TEST: AMAZON TITAN EMBEDDINGS
embedding_response = client.invoke_model(
    modelId=os.getenv("BEDROCK_EMBED_MODEL"),  # 3. Added missing comma here
    body=json.dumps({
        "inputText": "Hello Amazon Bedrock",
        "dimensions": 1024,
        "normalize": True
    }),
    contentType="application/json",
    accept="application/json"
)

embedding_data = json.loads(
    embedding_response["body"].read()
)
print("Embedding dimension: ", len(embedding_data["embedding"]))

# AMAZON NOVA LITE TEST
chat_response = client.converse(
    modelId=os.getenv("BEDROCK_CHAT_MODEL"),
    messages=[
        {
            "role": "user",
            "content": [
                {"text": "Explain RAG in one sentence"}
            ]
        }
    ],
    inferenceConfig={"maxTokens": 200}
)

# 4. Fixed 'chat_response' spelling
print(
    "Nova Response: ",
    chat_response["output"]["message"]["content"][0]["text"]
)