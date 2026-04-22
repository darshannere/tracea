import os
import secrets
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_api_key: str | None = None


def get_api_key() -> str:
    global _api_key
    if _api_key is None:
        key_file = os.getenv("TRACEA_API_KEY_FILE", "/data/api_key.txt")
        if os.path.exists(key_file):
            with open(key_file) as f:
                _api_key = f.read().strip()
        else:
            _api_key = os.getenv("TRACEA_API_KEY", "")
    return _api_key


security = HTTPBearer(auto_error=False)


async def bearer_auth(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})
    expected_key = get_api_key()
    # Dev mode only when explicitly enabled AND no API key is configured
    if not expected_key and os.getenv("TRACEA_DEV_MODE") == "1":
        return "dev-mode"
    if not expected_key:
        raise HTTPException(status_code=401, detail={"error": "unauthorized", "message": "No API key configured"})
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})
    if not secrets.compare_digest(credentials.credentials, expected_key):
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})
    return expected_key
