from fastapi import FastAPI, Request, HTTPException, Body
from pydantic import BaseModel
import os
from agent.graph import build_graph
from agent.kb import add_texts
from google.oauth2 import id_token
from google.auth.transport import requests as grequests
import base64, json, os, binascii
from google.cloud import storage
import json, time, os
from fastapi import APIRouter
from gmail.gmail_utils import gmail_authentication

app = FastAPI()
router = APIRouter()

GRAPH = build_graph(os.getenv("CHECKPOINT_DB", "data/sqlite/checkpoints.db"), use_memory=True)
PROJECT_ID   = os.getenv("PROJECT_ID")
TOPIC_ID     = os.getenv("TOPIC_ID")
STATE_BUCKET = os.getenv("STATE_BUCKET")
STATE_OBJECT = os.getenv("STATE_OBJECT")
PUSH_AUDIENCE = os.getenv("PUSH_AUDIENCE")
PUSH_SA_EMAIL = os.getenv("PUSH_SA_EMAIL")


class RunInput(BaseModel):
    gmail_message_id: str
    thread_id: str | None = None  # reserved for future
    resume: bool = False          # if you want to resume from checkpoint later

class KBAddBody(BaseModel):
    texts: list[str]

def _gcs_client():
    return storage.Client(project=PROJECT_ID)

def load_state() -> dict:
    try:
        b = _gcs_client().bucket(STATE_BUCKET)
        blob = b.blob(STATE_OBJECT)
        if not blob.exists():
            return {}
        data = blob.download_as_text() or "{}"
        return json.loads(data)
    except Exception:
        return {}

def save_state(state: dict):
    b = _gcs_client().bucket(STATE_BUCKET)
    blob = b.blob(STATE_OBJECT)
    blob.upload_from_string(json.dumps(state, indent=2), content_type="application/json")

def verify_pubsub_jwt(auth_header: str):
    # comment out temporarily if you're still testing unauthenticated
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    jwt = auth_header.split(" ", 1)[1]
    info = id_token.verify_oauth2_token(jwt, grequests.Request(), audience=PUSH_AUDIENCE)
    if info.get("iss") not in ("https://accounts.google.com", "accounts.google.com"):
        raise HTTPException(status_code=401, detail="Bad issuer")
    expected_email = os.getenv("PUSH_SA_EMAIL")
    expected_sub   = os.getenv("PUSH_SA_SUB")
    if info.get("email") and expected_email:
        if info["email"] != expected_email:
            raise HTTPException(status_code=401, detail="Wrong token subject (email)")
    elif expected_sub and info.get("sub"):
        if info["sub"] != expected_sub:
            raise HTTPException(status_code=401, detail="Wrong token subject (sub)")
    else:
        raise HTTPException(status_code=401, detail="Insufficient token claims")

@app.post("/agent/run")
def agent_run(inp: RunInput):
    initial_state = {"gmail_message_id": inp.gmail_message_id}
    # For now we just run straight-through; memory is attached for future resumptions
    final = GRAPH.invoke(initial_state)
    return {"ok": True, "state": {k: final.get(k) for k in ("gmail_message_id","draft","confidence","done")}}

@app.post("/kb/add-text")
def kb_add_text(body: KBAddBody):
    n = add_texts(body.texts)
    return {"ok": True, "added": n}

@app.get("/ping")
def ping():
    return {"ok": True}

@router.post("/admin/gmail/watch")
def start_or_renew_watch():
    service = gmail_authentication()
    topic_name = f"projects/{PROJECT_ID}/topics/{TOPIC_ID}"
    body = {
        "topicName": topic_name,
        "labelIds": ["INBOX"],             # only INBOX changes
        "labelFilterBehavior": "INCLUDE"   # include only listed labels
    }
    resp = service.users().watch(userId="me", body=body).execute()
    # resp: { "historyId": "...", "expiration": 172... (ms epoch) }
    state = load_state()
    state["last_history_id"] = int(resp["historyId"])
    state["watch_expiration_ms"] = int(resp["expiration"])
    state["watch_expiration_iso"] = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.gmtime(int(resp["expiration"]) / 1000)
    )
    save_state(state)
    return {"ok": True, "state": state}

# (optional) quick GET to see current state
@router.get("/admin/gmail/state")
def get_state():
    return load_state()

@app.post("/webhook/gmail")
async def gmail_webhook(request: Request):
    verify_pubsub_jwt(request.headers.get("Authorization"))  # enable once OIDC is wired

    raw = await request.body()
    # Try to parse as JSON
    try:
        body = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        # If payload unwrapping is ON, Pub/Sub may send raw bytes; treat as text JSON
        body = {}

    # Case A: payload unwrapping OFF (default) → envelope with message.data (base64)
    if isinstance(body, dict) and "message" in body:
        msg = body.get("message", {})
        data_b64 = msg.get("data") or ""
        if not data_b64.strip():
            print("Pub/Sub push with EMPTY data; ignoring.")
            return {"status": "ignored"}

        # Base64 can be URL-safe; add padding just in case
        try:
            decoded = base64.urlsafe_b64decode(data_b64 + "===")
        except binascii.Error as e:
            print("Base64 decode failed:", e, "data_len=", len(data_b64))
            return {"status": "ignored"}

        payload_str = decoded.decode("utf-8", "replace").strip()
        if not payload_str:
            print("Decoded data is empty string; ignoring.")
            return {"status": "ignored"}

        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError as e:
            print("JSON decode failed; preview:", repr(payload_str[:120]))
            return {"status": "ignored"}

    # Case B: payload unwrapping ON → body is the payload already
    else:
        payload = body
        if not payload:
            print("No envelope and empty body; ignoring.")
            return {"status": "ignored"}

    print("GMAIL PAYLOAD:", payload)  # should be {'emailAddress': '...', 'historyId': '...'}
    return {"status": "ok"}
@app.get("/where")
def where():
    return {"routes": [r.path for r in app.router.routes]}

app.include_router(router)