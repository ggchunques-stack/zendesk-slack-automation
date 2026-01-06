from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from app.webhook import router as webhook_router
from app.debug import router as debug_router

app = FastAPI(title="Zendesk Automation MVP", version="0.1.0")

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(webhook_router, prefix="/webhooks", tags=["webhooks"])
app.include_router(debug_router, prefix="/debug", tags=["debug"])