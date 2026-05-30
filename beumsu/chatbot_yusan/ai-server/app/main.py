from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.api.routes import admin, chat, eval, health, ingest
from app.core.logging import configure_logging
from app.db.repository import HeritageRepository

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    HeritageRepository.init_schema()
    yield


app = FastAPI(title="National Heritage AI Docent Chatbot", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(ingest.router)
app.include_router(eval.router)
app.include_router(admin.router)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """
    <!doctype html>
    <html lang="ko">
      <head>
        <meta charset="utf-8" />
        <title>국가유산 AI 해설 챗봇</title>
        <style>
          body { font-family: system-ui, sans-serif; max-width: 880px; margin: 40px auto; line-height: 1.5; }
          textarea { width: 100%; min-height: 96px; font: inherit; }
          button { padding: 8px 14px; margin-top: 8px; }
          pre { white-space: pre-wrap; background: #f4f4f4; padding: 16px; }
        </style>
      </head>
      <body>
        <h1>국가유산 AI 해설 챗봇</h1>
        <textarea id="q">경북궁 설명해줘</textarea>
        <br />
        <button onclick="ask()">질문하기</button>
        <pre id="out"></pre>
        <script>
          async function ask() {
            const response = await fetch('/chat', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({query: document.getElementById('q').value, audience: 'general'})
            });
            document.getElementById('out').textContent = JSON.stringify(await response.json(), null, 2);
          }
        </script>
      </body>
    </html>
    """
