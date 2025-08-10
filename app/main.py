from fastapi import FastAPI, Request
import base64
import json

app = FastAPI()

@app.post("/webhook/gmail")
async def gmail_webhook(request: Request):
    envelope = await request.json() 
    msg = envelope.get('message', {})
    data_b64 = msg.get('data')

    if not data_b64:
        return {"status": "ignored"}

    payload_str = base64.b64decode(data_b64).decode("utf-8")
    payload = json.loads(payload_str)

    print(f"Received Gmail webhook: {payload}")

    return {"status": "ok"}