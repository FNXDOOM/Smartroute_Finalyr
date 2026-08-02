import os
import sys
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/smartrouteai")

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    # Refuse to start with an empty or missing secret key — a leaked/guessable
    # key allows arbitrary JWT forgery.
    print(
        "FATAL: SECRET_KEY environment variable is not set. "
        "Set a strong random value in your .env file before starting the server.",
        file=sys.stderr,
    )
    sys.exit(1)

ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
