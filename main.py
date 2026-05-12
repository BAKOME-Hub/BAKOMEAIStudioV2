#!/usr/bin/env python3
"""
BAKOME AI Studio V2 – Alternative Open Source à Jasper AI
Backend complet avec FastAPI, SQLite, Ollama, templates, projets, exports
Version: 2.0.0
Auteur: Bakome Fabrice Kitoko
Licence: MIT
"""

import os
import json
import uuid
import hashlib
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Depends, status, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import aiohttp
import aiofiles
import markdown
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from docx import Document
import httpx

# ============================================================================
# CONFIGURATION
# ============================================================================

DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "studio.db"
TEMPLATES_DIR = DATA_DIR / "templates"
EXPORTS_DIR = DATA_DIR / "exports"

for d in [TEMPLATES_DIR, EXPORTS_DIR]:
    d.mkdir(exist_ok=True, parents=True)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "llama3.2:3b")
JWT_SECRET = os.getenv("JWT_SECRET", "bakome-super-secret-key-change-me")
SESSION_TIMEOUT_HOURS = 24

# ============================================================================
# DATABASE
# ============================================================================

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                created_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS generations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                project_id TEXT,
                template_id TEXT,
                prompt TEXT NOT NULL,
                model TEXT NOT NULL,
                parameters TEXT,
                result TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                system_prompt TEXT NOT NULL,
                user_prompt_template TEXT NOT NULL,
                example_input TEXT,
                created_at TEXT NOT NULL,
                is_premium INTEGER DEFAULT 0
            );
        """)
        # Insert default templates (100+ – abrégé ici pour lisibilité)
        conn.execute("DELETE FROM templates")
        default_templates = [
            ("blog_post", "Blog Post", "marketing",
             "You are a professional marketing writer. Write in English.",
             "Write a blog post about: {{topic}}. Style: {{style}}. Length: {{length}} words.",
             '{"topic": "open source AI", "style": "professional", "length": 800}'),
            ("landing_page", "Landing Page", "marketing",
             "You are a conversion copywriter.",
             "Generate full landing page copy for: {{product}}. Target: {{audience}}. Benefits: {{benefits}}.",
             '{"product": "BAKOME Studio", "audience": "developers", "benefits": "local, free, private"}'),
            ("email_newsletter", "Email Newsletter", "marketing",
             "You are an email marketing expert.",
             "Create an email announcing: {{announcement}}. Tone: {{tone}}. Call to action: {{cta}}.",
             '{"announcement": "new version 2.0", "tone": "enthusiastic", "cta": "Download now"}'),
            ("linkedin_post", "LinkedIn Post", "social",
             "You are a tech influencer. Write a concise, engaging post.",
             "Write a LinkedIn post about: {{topic}}. Mention: {{hashtags}}. Call to action: {{cta}}.",
             '{"topic": "open source", "hashtags": "#dev #oss", "cta": "Share your thoughts"}'),
        ]
        for tid, name, cat, sys_prompt, user_tpl, example in default_templates:
            conn.execute("""
                INSERT INTO templates (id, name, category, system_prompt, user_prompt_template, example_input, created_at, is_premium)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (tid, name, cat, sys_prompt, user_tpl, example, datetime.utcnow().isoformat(), 0))
        conn.commit()

init_db()

# ============================================================================
# MODELS
# ============================================================================

class UserCreate(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    email: str
    password: str

class GenerationRequest(BaseModel):
    project_id: Optional[str] = None
    template_id: Optional[str] = None
    prompt: str
    model: str = DEFAULT_MODEL
    parameters: Dict[str, Any] = Field(default_factory=dict)

class ProjectCreate(BaseModel):
    name: str

class TemplateCreate(BaseModel):
    name: str
    category: str
    system_prompt: str
    user_prompt_template: str
    example_input: Optional[str] = None

# ============================================================================
# SECURITY
# ============================================================================

security = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if not credentials:
        return None
    token = credentials.credentials
    with get_db() as conn:
        row = conn.execute("SELECT user_id, expires_at FROM sessions WHERE token = ?", (token,)).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid session")
        if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
            raise HTTPException(status_code=401, detail="Session expired")
        user = conn.execute("SELECT id, email, full_name FROM users WHERE id = ?", (row["user_id"],)).fetchone()
        return dict(user)

# ============================================================================
# OLLAMA CLIENT
# ============================================================================

async def ollama_generate(model: str, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
    async with httpx.AsyncClient(timeout=120.0) as client:
        payload = {
            "model": model,
            "prompt": user_prompt,
            "system": system_prompt,
            "temperature": temperature,
            "stream": False
        }
        resp = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Ollama error: {resp.text}")
        data = resp.json()
        return data.get("response", "")

def render_template(template_str: str, variables: Dict[str, Any]) -> str:
    for key, val in variables.items():
        template_str = template_str.replace("{{"+key+"}}", str(val))
    return template_str

# ============================================================================
# EXPORTS
# ============================================================================

async def export_to_pdf(content: str, filename: str) -> Path:
    filepath = EXPORTS_DIR / filename
    doc = SimpleDocTemplate(str(filepath), pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    html = markdown.markdown(content)
    story.append(Paragraph(html, styles["Normal"]))
    doc.build(story)
    return filepath

async def export_to_docx(content: str, filename: str) -> Path:
    filepath = EXPORTS_DIR / filename
    doc = Document()
    doc.add_paragraph(content)
    doc.save(str(filepath))
    return filepath

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(title="BAKOME AI Studio V2", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/")
async def root():
    return {"message": "BAKOME AI Studio V2 API", "status": "operational", "docs": "/docs"}

@app.post("/auth/register")
async def register(user: UserCreate):
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (user.email,)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Email already used")
        user_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users (id, email, password_hash, full_name, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, user.email, hash_password(user.password), user.full_name, datetime.utcnow().isoformat())
        )
        conn.commit()
    return {"id": user_id, "email": user.email}

@app.post("/auth/login")
async def login(user: UserLogin):
    with get_db() as conn:
        row = conn.execute("SELECT id, email, full_name, password_hash FROM users WHERE email = ?", (user.email,)).fetchone()
        if not row or not verify_password(user.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        token = str(uuid.uuid4())
        expires = (datetime.utcnow() + timedelta(hours=SESSION_TIMEOUT_HOURS)).isoformat()
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (token, row["id"], expires))
        conn.commit()
        return {"access_token": token, "token_type": "bearer", "user": {"id": row["id"], "email": row["email"], "full_name": row["full_name"]}}

@app.get("/templates")
async def list_templates(category: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        if category:
            rows = conn.execute("SELECT * FROM templates WHERE category = ? ORDER BY name", (category,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM templates ORDER BY category, name").fetchall()
        return [dict(r) for r in rows]

@app.post("/templates")
async def create_template(tpl: TemplateCreate, current_user: dict = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=403, detail="Authentication required")
    tid = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute("""
            INSERT INTO templates (id, name, category, system_prompt, user_prompt_template, example_input, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (tid, tpl.name, tpl.category, tpl.system_prompt, tpl.user_prompt_template, tpl.example_input, datetime.utcnow().isoformat()))
        conn.commit()
    return {"id": tid}

@app.post("/generate")
async def generate(request: GenerationRequest, current_user: Optional[dict] = Depends(get_current_user)):
    system = "You are a helpful AI assistant. Respond in the same language as the user."
    user_prompt = request.prompt
    if request.template_id:
        with get_db() as conn:
            tpl = conn.execute("SELECT * FROM templates WHERE id = ?", (request.template_id,)).fetchone()
            if tpl:
                system = tpl["system_prompt"]
                if tpl["user_prompt_template"] and "{{" in tpl["user_prompt_template"]:
                    user_prompt = render_template(tpl["user_prompt_template"], request.parameters)
    result_text = await ollama_generate(request.model, system, user_prompt)
    user_id = current_user["id"] if current_user else "anonymous"
    gen_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute("""
            INSERT INTO generations (id, user_id, project_id, template_id, prompt, model, parameters, result, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (gen_id, user_id, request.project_id, request.template_id, request.prompt, request.model,
              json.dumps(request.parameters), result_text, datetime.utcnow().isoformat()))
        conn.commit()
    return {"id": gen_id, "result": result_text, "model": request.model}

@app.post("/export/pdf")
async def export_pdf(request: GenerationRequest, current_user: Optional[dict] = Depends(get_current_user)):
    gen = await generate(request, current_user)
    result_text = gen["result"]
    filename = f"export_{uuid.uuid4().hex}.pdf"
    filepath = await export_to_pdf(result_text, filename)
    return FileResponse(str(filepath), media_type="application/pdf", filename=filename)

@app.post("/export/docx")
async def export_docx(request: GenerationRequest, current_user: Optional[dict] = Depends(get_current_user)):
    gen = await generate(request, current_user)
    result_text = gen["result"]
    filename = f"export_{uuid.uuid4().hex}.docx"
    filepath = await export_to_docx(result_text, filename)
    return FileResponse(str(filepath), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=filename)

@app.post("/projects")
async def create_project(proj: ProjectCreate, current_user: dict = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=403, detail="Authentication required")
    pid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute("INSERT INTO projects (id, user_id, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                     (pid, current_user["id"], proj.name, now, now))
        conn.commit()
    return {"id": pid, "name": proj.name}

@app.get("/projects")
async def list_projects(current_user: dict = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=403, detail="Authentication required")
    with get_db() as conn:
        rows = conn.execute("SELECT id, name, created_at FROM projects WHERE user_id = ? ORDER BY updated_at DESC", (current_user["id"],)).fetchall()
        return [dict(r) for r in rows]

@app.get("/history")
async def get_history(limit: int = 50, current_user: dict = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=403, detail="Authentication required")
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, project_id, template_id, substr(prompt,1,100) as prompt_preview, model, substr(result,1,200) as result_preview, created_at
            FROM generations WHERE user_id = ? ORDER BY created_at DESC LIMIT ?
        """, (current_user["id"], limit)).fetchall()
        return [dict(r) for r in rows]

@app.get("/models")
async def list_models():
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                return [{"name": m["name"], "size": m.get("size"), "modified": m.get("modified")} for m in data.get("models", [])]
    except:
        pass
    return [{"name": DEFAULT_MODEL, "size": "unknown"}]

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
