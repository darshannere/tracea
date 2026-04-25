"""Auth module — no-op, API key requirement removed."""
from fastapi import Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)


async def bearer_auth(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> str:
    """No-op auth — always succeeds."""
    return "dev-mode"
