from fastapi import FastAPI, Request
import base64
import json

app = FastAPI()


@app.post("/webhook/gmail")
async def gmail_webhook(request: Request):
    # verify_pubsub_jwt(request.headers.get("Authorization"))  # enable once OIDC is wired

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