from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routes import sessions, documents, chat, eval as eval_route

app = FastAPI(title="DocuChat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(eval_route.router)


@app.get("/")
def health_check():
    return {"status": "ok", "service": "DocuChat API"}