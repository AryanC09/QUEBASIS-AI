from functools import lru_cache  # Imports a helper that can cache a function's result.
from pydantic_settings import BaseSettings, SettingsConfigDict  # Imports tools for loading and validating app settings.


class Settings(BaseSettings):  # Defines the application's configuration values.
    # 1. Fixed 'env_files' -> 'env_file'
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")  # Reads settings from .env and ignores unknown settings.

    aws_region: str = ""  # Stores the AWS region; empty means no value is set by default.
    aws_access_key_id: str = ""  # Stores the AWS access key ID.
    aws_secret_access_key: str = ""  # Stores the AWS secret access key.
    s3_bucket: str = ""  # Stores the name of the S3 bucket used by the app.
    database_url: str = ""  # Stores the connection URL for the database.
    bedrock_embed_model: str = ""  # Stores the Amazon Bedrock model name used to create embeddings.
    bedrock_chat_model: str = ""  # Stores the Amazon Bedrock model name used for chat responses.
    embed_dim: int = 1024  # Sets the expected number of values in an embedding.
    max_upload_bytes: int = 10485760  # Sets the maximum upload size to 10 MiB in bytes.
    pinecone_api_key: str = ""  # Stores the API key used to access Pinecone.
    pinecone_index_name: str = "quebasis-ai-index"  # Sets the default name of the Pinecone index.
    pinecone_cloud: str = "aws"  # Sets the cloud provider where the Pinecone index runs.
    pinecone_region: str = "us-east-1"  # Sets the default region for the Pinecone index.
    pinecone_ready_timeout: int = 180  # Sets how many seconds to wait for Pinecone to be ready.
    min_relevance: float = 0.25  # Sets the minimum relevance score for results to be accepted.
    hitl_enabled: bool = True  # Enables human review in the app by default.
    # 2. Fixed '=' -> ':' for type annotation
    memory_turns: int = 6  # Sets how many conversation turns the app keeps in memory.


# Complete the lru_cache pattern to instantiate Settings once
@lru_cache  # Caches the settings object so repeated calls reuse the same instance.
def settings()->Settings:  # Defines a function that returns the app's Settings object.
    return Settings()  # Creates and returns the settings loaded from environment variables or .env.
