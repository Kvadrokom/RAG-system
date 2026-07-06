# rag_enrich.py
from sentence_transformers import SentenceTransformer
import psycopg2
import numpy as np
import os
from dotenv import load_dotenv
from logger import logger

load_dotenv()

MODEL_NAME = "deepvk/USER-base"
_model = None

def get_model():
    global _model
    if _model is None:
        logger.info(f"Загрузка модели {MODEL_NAME}...")
        _model = SentenceTransformer(MODEL_NAME, device="cpu")
        logger.info("Модель загружена")
    return _model

def encode_text(text: str, is_query: bool = True) -> np.ndarray:
    """
    Преобразует текст в векторное представление.
    
    Args:
        text: Текст для кодирования
        is_query: True для поисковых запросов ("query: "),
                  False для документов в БД ("passage: ")
    """
    model = get_model()
    prefix = "query: " if is_query else "passage: "
    text_with_prefix = prefix + text
    embedding = model.encode(text_with_prefix, normalize_embeddings=True)
    return embedding


def fetch_relevant_chunks(embedding_vector):
    """Поиск релевантных фрагментов текста."""
    connection = psycopg2.connect(
        host="localhost",
        database="rag_system",
        user="rag_user",
        password=os.getenv("DB_PASSWORD"),
    )
    cursor = connection.cursor()
    
    if isinstance(embedding_vector, np.ndarray):
        embedding_list = embedding_vector.tolist()
        embedding_str = '[' + ','.join(str(x) for x in embedding_list) + ']'
    else:
        embedding_str = str(embedding_vector)
    
    query = """
        SELECT chunk_text 
        FROM chunks 
        ORDER BY embedding <=> %s::vector 
        LIMIT 5
    """
    
    cursor.execute(query, (embedding_str,))
    relevant_chunks = cursor.fetchall()
    
    cursor.close()
    connection.close()
    
    return [chunk[0] for chunk in relevant_chunks]


def enrich_with_rag_system(user_query):
    """Функция для обогащения запроса с помощью RAG-системы."""
    try:
        logger.info(f"Преобразуем запрос {user_query} в векторное представление")
        embedding_vector = encode_text(user_query, is_query=True)
        
        relevant_chunks = fetch_relevant_chunks(embedding_vector)
        logger.info(f"Найдено {len(relevant_chunks)} релевантных фрагментов")
        
        if relevant_chunks:
            enriched_query = "\n\n".join(relevant_chunks + [user_query])
        else:
            enriched_query = user_query
        
        return enriched_query
        
    except Exception as e:
        logger.error(f"Ошибка в RAG: {e}")
        return user_query