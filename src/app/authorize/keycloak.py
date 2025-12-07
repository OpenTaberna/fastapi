from fastapi import HTTPException, Depends
from fastapi.security import OAuth2AuthorizationCodeBearer
from authlib.integrations.requests_client import OAuth2Session
import os
import json


# Setup environment variables
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "https://keycloak.example.com/auth/")
REALM = os.getenv("REALM", "YourRealm")
CLIENT_ID = os.getenv("CLIENT_ID", "your-client-id")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
JWKS_URL = f"{KEYCLOAK_URL}realms/{REALM}/protocol/openid-connect/certs"

# OAuth2 configuration
oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl=f"{KEYCLOAK_URL}realms/{REALM}/protocol/openid-connect/auth",
    tokenUrl=f"{KEYCLOAK_URL}realms/{REALM}/protocol/openid-connect/token",
)


async def validate_keycloak_token(user_token: str = Depends(oauth2_scheme)):
    auth = OAuth2Session(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
    result = auth.introspect_token(
        url=f"{KEYCLOAK_URL}realms/{REALM}/protocol/openid-connect/token/introspect",
        token=user_token,
    )

    # try:
    #     token_info = keycloak_openid.decode_token(token, key="RS256")
    # except KeycloakGetError as exc:
    #     raise HTTPException(
    #         status_code=401, detail="Token is invalid or expired") from exc

    token_info = json.loads(result.content.decode())
    print(token_info)
    if not token_info["active"]:
        raise HTTPException(status_code=401, detail="Token is invalid or expired")
    roles = token_info["realm_access"].get("roles")
    if "IT-Admin" in roles:
        return token_info

    raise HTTPException(status_code=403, detail="User does not have the required role")
