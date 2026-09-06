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
CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY", "").strip()
APP_ENV = os.getenv("APP_ENV", "development").lower()
PROCESS_ROLE = os.getenv("PROCESS_ROLE", "api").lower()
ENABLE_TRACKING_BROADCAST = os.getenv("ENABLE_TRACKING_BROADCAST", "true").lower() == "true"
# Opt-in convenience for local/single-process dev: also run the periodic
# dispatch job (assigned -> arriving -> in_progress -> completed, etc.)
# inside the API process itself, instead of requiring a separate
# `python worker.py` process. Defaults to off so docker-compose's dedicated
# worker service (see docker-compose.yml) doesn't double-run these jobs.
ENABLE_BACKGROUND_JOBS_IN_API = os.getenv("ENABLE_BACKGROUND_JOBS_IN_API", "false").lower() == "true"
STADIA_API_KEY = os.getenv("STADIA_API_KEY", "").strip()
STADIA_GEOCODER_URL = os.getenv(
    "STADIA_GEOCODER_URL", "https://api.stadiamaps.com/geocoding/v1"
).rstrip("/")
STADIA_ROUTER_URL = os.getenv(
    "STADIA_ROUTER_URL", "https://api.stadiamaps.com/route/v1"
).rstrip("/")
STADIA_MATRIX_URL = os.getenv(
    "STADIA_MATRIX_URL", "https://api.stadiamaps.com/matrix/v1"
).rstrip("/")
STADIA_NEAREST_ROADS_URL = os.getenv(
    "STADIA_NEAREST_ROADS_URL", "https://api.stadiamaps.com/nearest_roads/v1"
).rstrip("/")
STADIA_MAP_MATCH_URL = os.getenv(
    "STADIA_MAP_MATCH_URL", "https://api.stadiamaps.com/map_match/v1"
).rstrip("/")
STADIA_ROUTING_COSTING = os.getenv("STADIA_ROUTING_COSTING", "auto").strip()
STADIA_TILES_URL = os.getenv(
    "STADIA_TILES_URL", "https://tiles.stadiamaps.com"
).rstrip("/")
STADIA_MAP_STYLE_PATH = os.getenv(
    "STADIA_MAP_STYLE_PATH", "styles/alidade_smooth.json"
).strip().lstrip("/")
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
