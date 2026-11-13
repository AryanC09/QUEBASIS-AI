from app.config import settings

s=settings() #INTIALISING AN OBJECT OF THE SETTINGS CLASS
print(s.aws_secret_access_key)
print(s.bedrock_chat_model)