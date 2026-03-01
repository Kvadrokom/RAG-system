from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, File, UploadFile, Header, Request, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn
import psycopg2
import logging
import os
import jwt
from typing import Optional
from voice_processor import voice_processor
from schemas import *
from logger import logger
from dotenv import load_dotenv


load_dotenv()

# Configurations
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Logging setup
#logging.basicConfig(level=logging.INFO)
#logger = logging.getLogger(__name__)

JINJA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "templates"))
templates = Jinja2Templates(directory=JINJA_DIR)


# Функция для подключения к базе данных
def get_db_connection():
    return psycopg2.connect(host="localhost", database="rag_system", user="rag_user", password=DB_PASSWORD)


# Получение RqUID из заголовков
def extract_rqid(request: Request):
    return request.headers.get("RqUID", "")


# Логирование с использованием RqUID
def log_with_rqid(rqid, message):
    logger.info(f"[RqUID={rqid}] {message}")


# FastAPI initialization
app = FastAPI(
    title="RAG System API",
    description="API для Telegram бота с векторным поиском",
    version="1.0.0"
)

STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "static"))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# CORS policy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://185.114.72.54", "https://185.114.72.54"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB connection config
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'rag_system',
    'user': 'rag_user',
    'password': DB_PASSWORD
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


# JWT Authentication
def verify_jwt(token: str = Header(None)):
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return decoded
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid credentials")


# Главная страница административной панели
@app.get("/admin/add_article")
async def admin_page(request: Request):
    return templates.TemplateResponse("add_article.html", {"request": request})


# Маршрут для сохранения статьи
@app.post("/admin/save_article")
async def save_article(request: Request, title: str = Form(...), desc: str = Form(...), text: str = Form(...)):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO knowledge_articles (title, description, content) VALUES (%s, %s, %s)", (title, desc, text))
    conn.commit()


@app.post("/save_knowledge")
async def save_knowledge(knowledge: KnowledgeSchema):
    # Добавляем запись в базу данных
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO knowledge_articles (title, description, content) VALUES (%s, %s, %s)", (knowledge.title, knowledge.desc, knowledge.text))
    conn.commit()
    cur.close()
    conn.close()
    return {"success": True}


@app.middleware("http")
async def add_token_middleware(request: Request, call_next):
    if request.url.path.startswith("/gigachat"):
        await get_access_token()
        request.scope["headers"]["Authorization"] = f"Bearer {CURRENT_TOKEN}".encode()
    response = await call_next(request)
    return response


# Получение токена для GigaChat
async def get_access_token():
    global CURRENT_TOKEN, TOKEN_EXPIRES_AT
    current_time = time.time()
    async with LOCK:
        if current_time > TOKEN_EXPIRES_AT:
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": str(uuid.uuid4()),
                "Authorization": f"Basic {base64.b64encode(AUTH_KEY.encode()).decode()}"
            }
            data = {
                "grant_type": "client_credentials",
                "scope": "GIGACHAT_API_PERS"
            }
            response = requests.post(GIGACHAT_AUTH_URL, headers=headers, data=data)
            if response.status_code == 200:
                token_data = response.json()
                CURRENT_TOKEN = token_data["access_token"]



# Маршрут для генерации ответа с использованием RAG
@app.post("/gigachat/generate_answer")
async def generate_answer(query: Query):
    rqid = extract_rqid(request)
    log_with_rqid(rqid, "Начало обработки запроса")

    # Шаг 1: Получаем контекст из RAG-системы
    try:
        rag_response = requests.get(f"{RAGSYSTEM_URL}/retrieve_context", params={"query": query.query}).json()
        rag_response.raise_for_status()  # Проверка статуса ответа
        rag_json = rag_response.json()
        enriched_query = f"{rag_response['context']} {query.query}"
    
    except requests.HTTPError as err:
        log_with_rqid(rqid, f"Ошибка при запросе к RAG-системе: {err.response.status_code}, {err.response.text}")
        return {"error": "Ошибка при обработке запроса"}

    # Шаг 2: Отправляем запрос в GigaChat
    headers = {"Authorization": f"Bearer {CURRENT_TOKEN}", "RqUID": rqid}
    try:
        response = requests.post(f"{GIGACHAT_BASE_URL}/api/v1/messages", json={"query": enriched_query}, headers=headers).json()
        response.raise_for_status()  # Проверка статуса ответа
        response_json = response.json()
        log_with_rqid(rqid, "Запрос обработан успешно")
        return {"answer": response["generated_answer"]}

    except requests.HTTPError as err:
        log_with_rqid(rqid, f"Ошибка при запросе к GigaChat: {err.response.status_code}, {err.response.text}")
        return {"error": "Ошибка при обработке запроса"}



# Login route
@app.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    # Simple authentication (replace this with real authentication mechanism)
    if form_data.username == "admin" and form_data.password == "password":
        access_token_expires = ACCESS_TOKEN_EXPIRE_MINUTES * 60
        access_token = create_access_token(
            data={"sub": form_data.username},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        return {"access_token": access_token, "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="Incorrect username or password")

# Helper functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Root endpoint
@app.get("/")
async def root():
    return {
        "service": "RAG API for PostgreSQL + pgvector",
        "status": "running",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }

# Health-check endpoint
@app.get("/health")
async def health():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        tables = ["users", "documents", "chunks"]
        cursor.execute(f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name IN ({','.join(map(repr, tables))})")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return {
            "status": "healthy",
            "database": "connected",
            "tables_ready": count == len(tables),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# Stats endpoint
@app.get("/api/v1/stats")
async def get_stats():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        users_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM documents")
        docs_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM chunks")
        chunks_count = cursor.fetchone()[0]
        cursor.execute("SELECT pg_size_pretty(pg_database_size('rag_system'))")
        db_size = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return {
            "users_count": users_count,
            "docs_count": docs_count,
            "chunks_count": chunks_count,
            "db_size": db_size,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Voice recognition endpoint
@app.post("/api/v1/voice/recognize")
async def recognize_voice(voice_file: UploadFile = File(...)):
    try:
        voice_data = await voice_file.read()
        result = await voice_processor.process_voice(voice_data)
        return result
    except Exception as e:
        logger.error(f"Voice recognition error: {e}")
        raise HTTPException(status_code=500, detail=str(e))




# Run the server
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
