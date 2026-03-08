import psycopg2
import numpy as np
from transformers import AutoTokenizer, AutoModel
import torch
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Global variables
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
tokenizer = None
model = None

def init_model():
    """Инициализирует трансформерную модель."""
    global tokenizer, model
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModel.from_pretrained(MODEL_NAME)

def mean_pooling(model_output, attention_mask):
    """Средний пуллинг эмбеддингов"""
    token_embeddings = model_output.last_hidden_state.detach().cpu().numpy()
    input_mask_expanded = np.broadcast_to(np.expand_dims(attention_mask.cpu(), -1), token_embeddings.shape)
    sum_embeddings = np.sum(token_embeddings * input_mask_expanded, axis=1)
    sum_mask = np.clip(input_mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
    return sum_embeddings / sum_mask

def encode_text(text):
    """Преобразует текст в векторное представление."""
    inputs = tokenizer([text], padding=True, truncation=True, max_length=512, return_tensors="pt")
    outputs = model(**inputs)
    embeddings = mean_pooling(outputs, inputs["attention_mask"])
    return embeddings.flatten()

def fetch_relevant_chunks(embedding_vector):
    """Поиск релевантных фрагментов текста по векторному представлению."""
    connection = psycopg2.connect(
        host="localhost",
        database="rag_system",
        user="rag_user",
        password=os.getenv("DB_PASSWORD"),
    )
    cursor = connection.cursor()
    
    # Запрос к векторной базе данных для поиска близких соседей
    cursor.execute("""
        SELECT chunk_text 
        FROM chunks 
        ORDER BY embedding <=> %s LIMIT 5
    """, (embedding_vector,))
    
    relevant_chunks = cursor.fetchall()
    cursor.close()
    connection.close()
    
    return [chunk[0] for chunk in relevant_chunks]

def enrich_with_rag_system(user_query):
    """Функция для обогащения запроса с помощью RAG-системы."""
    # Инициализируем модель, если она ещё не инициализирована
    global tokenizer, model
    if tokenizer is None or model is None:
        init_model()
    
    # Преобразуем запрос в векторное представление
    embedding_vector = encode_text(user_query)
    
    # Ищем ближайшие соседи (релевантные фрагменты текста)
    relevant_chunks = fetch_relevant_chunks(embedding_vector)
    
    # Объединяем исходный запрос с релевантными фрагментами
    enriched_query = "\n\n".join(relevant_chunks + [user_query])
    
    return enriched_query