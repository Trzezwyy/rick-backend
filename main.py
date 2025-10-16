# main.py
import os
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from supabase import create_client

app = FastAPI()

# 🔒 w trakcie dev zostawiamy *, po deployu zwężamy do konkretnego frontu
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # docelowo: ["http://localhost:3000", "https://twoj-front.vercel.app"]
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE")
RICK_API_SECRET = os.getenv("RICK_API_SECRET")

client = OpenAI(api_key=OPENAI_API_KEY)
sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE)

SYSTEM_PROMPT = (
    "Jesteś Rick – spokojny, refleksyjny partner-mentor (Alfred vibe). "
    "Dostarczasz jasność i logiczne plany. Zero 'AI-owości'."
)
QUALITY = (
    "- Sedno 2–5 zdań\n"
    "- 1–3 kroki\n"
    "- Założenia/ryzyka\n"
    "- Alternatywa B (jeśli ma sens)\n"
    "- Max 1–2 pytania tylko gdy brakuje kluczowych danych"
)

class Msg(BaseModel):
    message: str
    conversation_id: str | None = None
    mode: str | None = "balanced"

@app.get("/health")
def health():
    return {"ok": True}

def need_questions(txt: str) -> bool:
    low = txt.lower()
    missing = any(k not in low for k in ["cel","kpi","budżet","horyzont"])
    ambig = ("?" in low) or ("nie wiem" in low)
    return missing or ambig

def chat(messages, temperature=0.4):
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=temperature
    )
    return r.choices[0].message.content

@app.post("/api/reply")
def api_reply(data: Msg, authorization: str = Header(default="")):
    if authorization != f"Bearer {RICK_API_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    sys = {"role":"system","content":SYSTEM_PROMPT}

    if need_questions(data.message):
        q = chat([sys, {"role":"user","content":
             f"Zanim odpowiesz, zapytaj o max 1–2 brakujące informacje. Użytkownik: {data.message}"}], 0.3)
        return {"type":"questions","content":q, "conversation_id": data.conversation_id}

    draft = chat([sys, {"role":"user","content":
        "Użyj pętli MZDS i odpowiedz wg formatu "
        "(Sedno/Plan/Założenia i ryzyka/Alternatywa B/Pytanie jeśli trzeba). "
        f"Użytkownik: {data.message}"}], 0.4)

    final = chat([sys, {"role":"user","content": draft + "\n\n[Sprawdź jakość i podaj wersję finalną.]\n" + QUALITY}], 0.2)

    return {"type":"answer","content":final, "conversation_id": data.conversation_id}
