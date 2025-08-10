# main.py
from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/webhook/gmail")
async def gmail_webhook(request: Request):
    envelope = await request.json()     # Pub/Sub sends an envelope JSON
    print("ENVELOPE:", envelope)        # look in Cloud Run logs
    return {"status": "ok"}             # 200 OK tells Pub/Sub “delivered”
