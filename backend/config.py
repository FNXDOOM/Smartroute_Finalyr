import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Attempt loading from root .env or local .env
root_env = Path(__file__).resolve().parent.parent / ".env"
local_env = Path(__file__).resolve().parent / ".env"

if root_env.exists():
    load_dotenv(dotenv_path=root_env)
if local_env.exists():
    load_dotenv(dotenv_path=local_env, override=True)
if not root_env.exists() and not local_env.exists():
    load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/smartrouteai")

ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

AUTH_PROVIDER = os.getenv("AUTH_PROVIDER", "clerk").lower()
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "")
CLERK_ISSUER = os.getenv("CLERK_ISSUER", "")
CLERK_AUDIENCE = os.getenv("CLERK_AUDIENCE", "")
_raw_authorized_parties = os.getenv("CLERK_AUTHORIZED_PARTIES", "")
CLERK_AUTHORIZED_PARTIES = [
    origin.strip().rstrip("/")
    for origin in _raw_authorized_parties.split(",")
    if origin.strip()
]

if AUTH_PROVIDER == "clerk" and (not CLERK_JWKS_URL or not CLERK_ISSUER):
    print(
        "WARNING: AUTH_PROVIDER=clerk requires CLERK_JWKS_URL and CLERK_ISSUER in environment.",
        file=sys.stderr,
    )
