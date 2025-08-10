from fastapi import FastAPI, Request, HTTPException
from google.oauth2 import id_token
from google.auth.transport import requests as grequests
import json, base64, os

app = FastAPI()

PUSH_AUDIENCE = os.getenv("PUSH_AUDIENCE")
PUSH_SA_EMAIL = os.getenv("PUSH_SA_EMAIL")

def verify_pubsub_jwt(auth_header: str):
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth_header.split(" ", 1)[1]
    info = id_token.verify_oauth2_token(token, grequests.Request(), audience=PUSH_AUDIENCE)
    # Confirm it was minted for your push SA and by Google
    if info.get("email") != PUSH_SA_EMAIL:
        raise HTTPException(status_code=401, detail="Wrong token subject")
    if info.get("iss") not in ("https://accounts.google.com", "accounts.google.com"):
        raise HTTPException(status_code=401, detail="Bad issuer")

@app.post("/webhook/gmail")
async def gmail_webhook(request: Request):
    verify_pubsub_jwt(request.headers.get("Authorization"))
    envelope = await request.json()
    msg = envelope.get("message", {})
    data_b64 = msg.get("data")
    if not data_b64:
        return {"status": "ignored"}
    payload = json.loads(base64.b64decode(data_b64).decode("utf-8"))
    # payload looks like: {"emailAddress":"...","historyId":"123456"}
    # hand off to your Gmail handler here
    return {"status": "ok"}
