import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Backend configuration belongs beside the backend entry point. Environment
# variables supplied by the process/container still take precedence because
# python-dotenv does not override existing values by default.
backend_env = Path(__file__).resolve().parent / ".env"

if backend_env.exists():
    load_dotenv(dotenv_path=backend_env)
else:
    load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

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
CLERK_ALLOW_NATIVE_CLIENTS = os.getenv("CLERK_ALLOW_NATIVE_CLIENTS", "false").lower() == "true"
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
