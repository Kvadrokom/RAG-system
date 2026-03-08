from datetime import datetime, timedelta, time, json, uuid, base64, aiohttp, httpx
from fastapi import FastAPI, Depends, HTTPException, File, UploadFile, Header, Request, Form, HTMLResponse
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
from rag_enrich import enrich_with_rag_system
from database_utils import add_text_to_database


load_dotenv()

# Configurations
GIGACHAT_API_URL = 'https://gigachat.devices.sberbank.ru/api/v1/chat/completions'
CURRENT_TOKEN = ''
TOKEN_EXPIRES_AT = time.time()
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
DB_PASSWORD = os.getenv("DB_PASSWORD")
GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

# Logging setup
#logging.basicConfig(level=logging.INFO)
#logger = logging.getLogger(__name__)

JINJA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "templates"))
templates = Jinja2Templates(directory=JINJA_DIR)


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
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {SECRET_KEY}"
    }
    data = {
        "scope": "GIGACHAT_API_PERS"
    }
    if CURRENT_TOKEN == '' or current_time > TOKEN_EXPIRES_AT:
        connector = aiohttp.TCPConnector(verify_ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(GIGACHAT_AUTH_URL, headers=headers, data=data) as resp:
                response = await resp.json()
                if resp.status == 200:
                    token_data = response
                    CURRENT_TOKEN = token_data["access_token"]
                    TOKEN_EXPIRES_AT = current_time + token_data['expires_in']


# Маршрут для генерации ответа с использованием RAG
@app.post("/gigachat/generate_answer")
async def process_voice(query: Query):
    """
    Обрабатывает запрос от Telegram-бота, применяя RAG-систему и перенаправляя в Гигачат.
    """
    try:
        # Логируем входящий запрос
        logger.info(f"Received request with rquid: {query.rquid}, User query: {query.user_query}")

        # Обогащаем запрос с помощью RAG-системы (пример условный, зависит от вашей реализации)
        enriched_query = enrich_with_rag_system(query.user_query)

        # Готовим запрос для Гигачата
        gigachat_payload = {
            "enriched_query": enriched_query
        }

        # Отправляем запрос в Гигачат
        await get_access_token()

        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            headers = {
                "Content-Type":  "application/json",
                "Accept": "application/json",
                "RqUID": query.rquid,
                "Authorization": f"Bearer {CURRENT_TOKEN}"
            }
            async with session.post(GIGACHAT_API_URL, headers=headers, json=gigachat_payload) as resp:
                response = await resp.json()

            # Проверяем статус ответа от Гигачата
            if response.status_code == 200:
                answer = resp.text
                logger.info(f"GigaChat responded successfully: {answer}")
                return {"result": answer}
            else:
                logger.error(f"GigaChat returned error: {resp.status}, {resp.text}")
                return {"error": "Failed to process the request"}

    except Exception as e:
        logger.exception(e)
        return {"error": str(e)}



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

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# Маршрут для обработки формы
@app.post("/add-text/", response_class=HTMLResponse)
async def submit_text(request: Request, text: str = Form(...)):
    try:
        # Информация о документе
        file_name = "input.txt"
        file_size = len(text.encode('utf-8'))
        file_type = "text/plain"

        # Добавляем текст в базу данных
        num_chunks = add_text_to_database(text, file_name, file_size, file_type)

        # Выводим сообщение о результатах
        return templates.TemplateResponse("index.html", {"request": request, "num_chunks": num_chunks})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
