import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/smartrouteai")

AUTH_PROVIDER = os.getenv("AUTH_PROVIDER", "clerk").lower()
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "")
CLERK_ISSUER = os.getenv("CLERK_ISSUER", "")
CLERK_AUDIENCE = os.getenv("CLERK_AUDIENCE", "")

if AUTH_PROVIDER == "clerk" and (not CLERK_JWKS_URL or not CLERK_ISSUER):
    print(
        "FATAL: AUTH_PROVIDER=clerk requires CLERK_JWKS_URL and CLERK_ISSUER.",
        file=sys.stderr,
    )
    sys.exit(1)
