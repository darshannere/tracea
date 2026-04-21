import os
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_api_key: str | None = None


def get_api_key() -> str:
    global _api_key
    if _api_key is None:
        key_file = os.getenv("TRACEA_API_KEY_FILE", "/data/api_key.txt")
        if os.path.exists(key_file):
            _api_key = open(key_file).read().strip()
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
    # Allow any Bearer token when no API key is configured (dev mode)
    if not expected_key:
        return "dev-mode"
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})
    if credentials.credentials != expected_key:
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})
    return expected_key
