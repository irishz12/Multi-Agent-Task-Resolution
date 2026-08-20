import os

os.environ.setdefault("DATABASE_URL", "postgresql://user:password@localhost:5432/test")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("BEDROCK_BASE_URL", "https://example.invalid")
os.environ.setdefault("BEDROCK_API_KEY", "test-key")
os.environ.setdefault("BEDROCK_MODEL", "test-model")
