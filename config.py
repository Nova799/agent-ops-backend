import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("AGENT_OPS_API_KEY")  # None => dev mode (no auth)
DATABASE_URL = os.getenv("AGENT_OPS_DATABASE_URL", "sqlite:///./agent_ops.db")
HOST = os.getenv("AGENT_OPS_HOST", "0.0.0.0")
PORT = int(os.getenv("AGENT_OPS_PORT", "8001"))
CORS_ORIGINS = [o.strip() for o in os.getenv("AGENT_OPS_CORS", "*").split(",") if o.strip()]
RETENTION_DAYS = int(os.getenv("AGENT_OPS_RETENTION_DAYS", "0"))  # 0 disables
RATE_LIMIT_PER_MIN = int(os.getenv("AGENT_OPS_RATE_LIMIT", "120"))