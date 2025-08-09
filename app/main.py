from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/webhook/gmail")
async def gmail_webhook(request: Request):
    envelope = await request.json()   
    print("Got Pub/Sub push:", envelope)
    return {"status": "ok"}           