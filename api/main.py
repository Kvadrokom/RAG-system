from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, File, UploadFile, Header, Request, Form, Query
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
from logger import logger, create_logging_middleware
from dotenv import load_dotenv
from rag_enrich import enrich_with_rag_system
from database_utils import add_text_to_database
from fastapi.responses import HTMLResponse

# Импортируем функции авторизации из отдельного файла
from auth import get_access_token, get_gigachat_token, get_salute_token

# Импортируем функцию распознавания из my_salute_speech.py
from salute_speech_voice import recognize_audio, SaluteSpeechError

load_dotenv()

# Configurations
GIGACHAT_API_URL = 'https://gigachat.devices.sberbank.ru/api/v1/chat/completions'
TOKEN_EXPIRES_AT = 0
GIGACHAT_SECRET_KEY = os.getenv("GIGACHAT_SECRET_KEY")
SALUTE_SECRET_KEY = os.getenv("SALUTE_SPEECH_API_KEY")  
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
DB_PASSWORD = os.getenv("DB_PASSWORD")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")

# Logging setup
logging.basicConfig(level=logging.INFO)

JINJA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "templates"))
templates = Jinja2Templates(directory=JINJA_DIR)

# FastAPI initialization
app = FastAPI(
    title="RAG System API",
    description="API для Telegram бота с векторным поиском",
    version="2.0.0"
)

STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "static"))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# CORS policy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


# ========== ПОДКЛЮЧАЕМ MIDDLEWARE ==========
app.middleware("http")(create_logging_middleware(logger))



def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


# JWT Authentication
def verify_jwt(token: str = Header(None)):
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return decoded
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid credentials")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С GIGACHAT (ДЛЯ ГОЛОСА) ==========

async def enrich_voice_with_rag(recognized_text: str) -> dict:
    """
    Обогащает распознанный текст через RAG-систему.
    """
    try:
        # Используем существующую функцию enrich_with_rag_system
        enriched = enrich_with_rag_system(recognized_text)
        
        # Формируем контекст для GigaChat
        if enriched != recognized_text:  # Если были найдены документы
            context = f"""Вот релевантная информация из базы знаний:

{enriched}

Вопрос пользователя (распознан из голоса): {recognized_text}

Ответь, используя эти документы. Обрати внимание на эмоции в голосе пользователя."""
            has_context = True
        else:
            context = f"""Вопрос пользователя (распознан из голоса): {recognized_text}

Релевантных документов не найдено. Ответь, основываясь на своих знаниях."""
            has_context = False
        
        return {"context": context, "has_context": has_context}
        
    except Exception as e:
        logger.error(f"Ошибка в RAG: {e}")
        return {
            "context": f"Вопрос пользователя: {recognized_text}",
            "has_context": False
        }


# ========== ЭНДПОИНТЫ ==========

@app.post("/gigachat/generate_answer/rag_system")
async def process_voice(query: Query):
    """Обрабатывает текстовый запрос с RAG и отправляет в GigaChat."""
    try:
        logger.info(f"✅ Received request with rquid: {query.rquid}, User query: {query.user_query}")
        
        enriched_query = enrich_with_rag_system(query.user_query)
        logger.info(f"Enriched query: {enriched_query[:200]}...")
        
        token = await get_access_token()
        logger.info("Token obtained successfully")
        
        gigachat_payload = {
            "model": "GigaChat-2",
            "messages": [{"role": "user", "content": enriched_query}],
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "RqUID": query.rquid,
                "Authorization": f"Bearer {token}"
            }
            
            async with session.post(GIGACHAT_API_URL, headers=headers, json=gigachat_payload) as resp:
                if resp.status == 200:
                    response = await resp.json()
                    answer = response['choices'][0]['message']['content']
                    logger.info(f"Answer received (length: {len(answer)} chars)")
                    return {"result": answer}
                else:
                    error_text = await resp.text()
                    logger.error(f"GigaChat error {resp.status}: {error_text}")
                    return {"error": f"GigaChat error: {resp.status}, details: {error_text}"}
                    
    except Exception as e:
        logger.exception(f"Exception in process_voice: {e}")
        return {"error": str(e)}



@app.post("/gigachat/generate_answer")
async def process_voice(query: Query):
    """Обрабатывает текстовый запрос и отправляет в GigaChat."""
    try:
        logger.info(f"✅ Received request with rquid: {query.rquid}, User query: {query.user_query}")
        
        # enriched_query = enrich_with_rag_system(query.user_query)
        # logger.info(f"Enriched query: {enriched_query[:200]}...")
        
        token = await get_access_token()
        logger.info("Token obtained successfully")
        
        gigachat_payload = {
            "model": "GigaChat-2",
            "messages": [{"role": "user", "content": query.user_query}],
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "RqUID": query.rquid,
                "Authorization": f"Bearer {token}"
            }
            
            async with session.post(GIGACHAT_API_URL, headers=headers, json=gigachat_payload) as resp:
                if resp.status == 200:
                    response = await resp.json()
                    answer = response['choices'][0]['message']['content']
                    logger.info(f"Answer received (length: {len(answer)} chars)")
                    return {"result": answer}
                else:
                    error_text = await resp.text()
                    logger.error(f"GigaChat error {resp.status}: {error_text}")
                    return {"error": f"GigaChat error: {resp.status}, details: {error_text}"}
                    
    except Exception as e:
        logger.exception(f"Exception in process_voice: {e}")
        return {"error": str(e)}


@app.post("/api/v1/voice/recognize")
async def recognize_voice(voice_file: UploadFile = File(...)):
    """
    Обрабатывает голосовое сообщение:
    1. Распознает речь через SaluteSpeech
    """
    logger.info(f"🎤 Получен голосовой запрос: {voice_file.filename}")
    
    try:
        # 1. Читаем аудио файл
        voice_data = await voice_file.read()
        logger.info(f"📦 Размер аудио: {len(voice_data)} байт")
        
        # 2. Распознаем речь через SaluteSpeech
        recognized_text = await recognize_audio(
            audio_bytes=voice_data,
            filename=voice_file.filename,
            language="ru-RU"
        )
        logger.info(f"📝 Распознанный текст: {recognized_text[:100]}...")
        
        if not recognized_text or not recognized_text.strip():
            return {"text": "Не удалось распознать голосовое сообщение"}
        
        # # 3. Отправляем распознанный текст в существующий эндпоинт!
        # query = Query(
        #     rquid=str(uuid.uuid4()),
        #     user_query=recognized_text
        # )
        return recognized_text
        # result = await process_voice(query)
        
        # # 4. Возвращаем ответ
        # if "result" in result:
        #     return {"text": result["result"]}
        # else:
        #     return {"text": f"Ошибка: {result.get('error', 'Неизвестная ошибка')}"}
        
    
    except SaluteSpeechError as e:
        logger.error(f"❌ Ошибка распознавания: {e}")
        return {"text": f"Ошибка распознавания речи: {str(e)}"}
    
    except Exception as e:
        logger.error(f"❌ Voice recognition error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/voice/recognize/local")
async def recognize_voice_local(voice_file: UploadFile = File(...)):
    """Старый эндпоинт (локальный voice_processor) для обратной совместимости."""
    logger.info(f"🎤 Получен голосовой запрос (local): {voice_file.filename}")
    try:
        voice_data = await voice_file.read()
        result = await voice_processor.process_voice(voice_data)
        return result
    except Exception as e:
        logger.error(f"Voice recognition error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Login route
@app.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username == "admin" and form_data.password == "password":
        access_token = create_access_token(data={"sub": form_data.username})
        return {"access_token": access_token, "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="Incorrect username or password")


@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/add-text/", response_class=HTMLResponse)
async def submit_text(request: Request, text: str = Form(...)):
    try:
        logger.info(f"Input text length: {len(text)} chars")
        num_chunks = add_text_to_database(text, "input.txt", len(text.encode('utf-8')), "text/plain")
        logger.info(f"Successfully added to DB, chunks: {num_chunks}")
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
        cursor.close()
        conn.close()
        return {
            "status": "healthy",
            "database": "connected",
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
        cursor.execute("SELECT COUNT(*) FROM documents")
        docs_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM chunks")
        chunks_count = cursor.fetchone()[0]
        cursor.execute("SELECT pg_size_pretty(pg_database_size('rag_system'))")
        db_size = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return {
            "docs_count": docs_count,
            "chunks_count": chunks_count,
            "db_size": db_size,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/search")
async def search(q: str):
    logger.info(f"Search request: {q}")
    result = enrich_with_rag_system(q)
    return {"results": result}


# Run the server
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)