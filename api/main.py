from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, File, UploadFile, Header, Request, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn
import psycopg2
import logging
import os, json, uuid, base64, aiohttp, time
import jwt
from typing import Optional
from voice_processor import voice_processor
from schemas import *
from logger import logger
from dotenv import load_dotenv
from rag_enrich import enrich_with_rag_system
from database_utils import add_text_to_database
from fastapi.responses import HTMLResponse

load_dotenv()

# Configurations
GIGACHAT_API_URL = 'https://gigachat.devices.sberbank.ru/api/v1/chat/completions'
GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
CURRENT_TOKEN = ''
TOKEN_EXPIRES_AT = 0
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Logging setup
logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

JINJA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "templates"))
templates = Jinja2Templates(directory=JINJA_DIR)

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
    allow_origins=["*"],  # Для теста можно *, потом ограничить
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

# ========== ИСПРАВЛЕННАЯ ФУНКЦИЯ ПОЛУЧЕНИЯ ТОКЕНА ==========
async def get_access_token():
    global CURRENT_TOKEN, TOKEN_EXPIRES_AT
    current_time = time.time()
    
    # Если токен еще действителен, возвращаем его
    if CURRENT_TOKEN and current_time < TOKEN_EXPIRES_AT:
        logger.info("Token still valid, using existing")
        return CURRENT_TOKEN
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {SECRET_KEY}"
    }
    data = {
        "scope": "GIGACHAT_API_PERS"
    }
    
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.post(GIGACHAT_AUTH_URL, headers=headers, data=data) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                logger.error(f"Failed to get token: {resp.status} - {error_text}")
                raise HTTPException(status_code=500, detail=f"Token error: {resp.status}")
            
            response = await resp.json()
            logger.info(f"Token response received, keys: {list(response.keys())}")
            
            # Получаем токен
            CURRENT_TOKEN = response.get("access_token")
            if not CURRENT_TOKEN:
                raise HTTPException(status_code=500, detail="No access_token in response")
            
            # Получаем expires_in (с значением по умолчанию)
            expires_in = response.get("expires_in", 3600)  # По умолчанию 1 час
            TOKEN_EXPIRES_AT = current_time + expires_in
            
            logger.info(f"Token obtained successfully, expires in {expires_in} seconds")
            return CURRENT_TOKEN

# ========== ИСПРАВЛЕННЫЙ ЭНДПОИНТ ==========
@app.post("/gigachat/generate_answer")
async def process_voice(query: Query):
    """
    Обрабатывает запрос от Telegram-бота, применяя RAG-систему и перенаправляя в Гигачат.
    """
    try:
        # Логируем входящий запрос
        logger.info(f"✅ Received request with rquid: {query.rquid}, User query: {query.user_query}")
        
        # Обогащаем запрос с помощью RAG-системы
        enriched_query = enrich_with_rag_system(query.user_query)
        logger.info(f"Enriched query: {enriched_query}")
        
        # Получаем токен для GigaChat
        token = await get_access_token()
        logger.info("Token obtained successfully")
        
        # Правильный формат запроса для GigaChat API
        gigachat_payload = {
            "model": "GigaChat-2",
            "messages": [
                {
                    "role": "user",
                    "content": enriched_query
                }
            ],
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        # Отправляем запрос в Гигачат
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "RqUID": query.rquid,
                "Authorization": f"Bearer {token}"
            }
            
            logger.info(f"Sending request to GigaChat API")
            
            async with session.post(GIGACHAT_API_URL, headers=headers, json=gigachat_payload) as resp:
                logger.info(f"GigaChat response status: {resp.status}")
                
                if resp.status == 200:
                    response = await resp.json()
                    logger.info("Successfully received response from GigaChat")
                    
                    # Извлекаем ответ
                    answer = response['choices'][0]['message']['content']
                    logger.info(f"Answer received (length: {len(answer)} chars)")
                    
                    return {"result": answer}
                else:
                    error_text = await resp.text()
                    logger.error(f"GigaChat error {resp.status}: {error_text}")
                    return {"error": f"GigaChat error: {resp.status}, details: {error_text}"}
                    
    except KeyError as e:
        logger.error(f"KeyError parsing GigaChat response: {e}")
        return {"error": f"Unexpected response format from GigaChat: {str(e)}"}
    except Exception as e:
        logger.exception(f"Exception in process_voice: {e}")
        return {"error": str(e)}

# ========== ОСТАЛЬНЫЕ ЭНДПОИНТЫ (без изменений) ==========

# Login route
@app.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username == "admin" and form_data.password == "password":
        access_token_expires = ACCESS_TOKEN_EXPIRE_MINUTES * 60
        access_token = create_access_token(
            data={"sub": form_data.username},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        return {"access_token": access_token, "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="Incorrect username or password")

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

@app.post("/add-text/", response_class=HTMLResponse)
async def submit_text(request: Request, text: str = Form(...)):
    try:
        logger.info(f"Input text:\n {text.encode('utf-8')}")
        file_name = "input.txt"
        file_size = len(text.encode('utf-8'))
        file_type = "text/plain"
        
        logger.info(f"Adding text to DB")
        num_chunks = add_text_to_database(text, file_name, file_size, file_type)
        
        logger.info("Successfully add text to DB")
        return templates.TemplateResponse("index.html", {"request": request, "num_chunks": num_chunks})
    except Exception as e:
        logger.error(f"Error - {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

@app.post("/api/v1/voice/recognize")
async def recognize_voice(voice_file: UploadFile = File(...)):
    try:
        voice_data = await voice_file.read()
        result = await voice_processor.process_voice(voice_data)
        return result
    except Exception as e:
        logger.error(f"Voice recognition error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    
@app.get("/api/v1/search")
async def search(request: Request):
    query_param = request.query_params.get("q")
    logger.info(f"Get request {query_param}")
    return enrich_with_rag_system(query_param)

# Run the server
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)