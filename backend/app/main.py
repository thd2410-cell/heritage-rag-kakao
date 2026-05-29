from fastapi import FastAPI
from app.api.kakao import router as kakao_router
from app.api.rag import router as rag_router

app = FastAPI(title="Heritage RAG Kakao MK0", version="0.1.0")
app.include_router(kakao_router)
app.include_router(rag_router)


@app.get("/health")
def health():
    return {"ok": True}
