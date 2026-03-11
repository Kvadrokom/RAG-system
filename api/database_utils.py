import hashlib
import psycopg2
from typing import List
from transformers import AutoTokenizer, AutoModel
import torch
import numpy as np
import os
from dotenv import load_dotenv

# Загрузим переменные окружения
load_dotenv()

# Модель для векторизации
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
tokenizer = None
model = None
DB_PASSWORD = os.getenv("DB_PASSWORD")

def init_model():
    """Инициализирует трансформерную модель."""
    global tokenizer, model
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModel.from_pretrained(MODEL_NAME)

def mean_pooling(model_output, attention_mask):
    """Средний пуллинг эмбеддингов."""
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

def split_into_chunks(text: str, chunk_size: int = 500) -> List[str]:
    """
    Разделяет текст на равные куски размером примерно chunk_size символов.
    """
    words = text.split()
    chunks = []
    current_chunk = []
    word_count = 0

    for word in words:
        current_chunk.append(word)
        word_count += len(word)
        if word_count > chunk_size:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
            word_count = 0

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks

def calculate_md5_hash(text: str) -> str:
    """
    Вычисляет MD5-хэш строки.
    """
    md5_hasher = hashlib.md5()
    md5_hasher.update(text.encode('utf-8'))
    return md5_hasher.hexdigest()

def create_document_record(file_name: str, file_size: int, file_type: str, user_id: int = 1) -> int:
    """
    Создает запись в таблице documents и возвращает её id.
    """
    connection = psycopg2.connect(
        host="localhost",
        database="rag_system",
        user="rag_user",
        password=os.getenv("DB_PASSWORD"),
    )
    cursor = connection.cursor()

    # Создаем запись в таблице documents
    insert_query = """
        INSERT INTO documents (user_id, file_name, file_size, file_type)
        VALUES (%s, %s, %s, %s)
        RETURNING id;
    """
    values = (user_id, file_name, file_size, file_type)
    cursor.execute(insert_query, values)
    document_id = cursor.fetchone()[0]

    connection.commit()
    cursor.close()
    connection.close()

    return document_id

def save_chunks_to_db(chunks: List[str], document_id: int):
    """
    Сохраняет куски текста в базу данных.
    """
    connection = psycopg2.connect(
        host="localhost",
        database="rag_system",
        user="rag_user",
        password=os.getenv("DB_PASSWORD"),
    )
    cursor = connection.cursor()

    for index, chunk in enumerate(chunks):
        # Преобразуем кусок текста в векторное представление
        embedding_vector = encode_text(chunk)

        # Создаем хэш-чанк
        chunk_hash = calculate_md5_hash(chunk)

        # Подготовим запрос на вставку
        insert_query = """
            INSERT INTO chunks (document_id, chunk_index, chunk_text, chunk_hash, embedding)
            VALUES (%s, %s, %s, %s, %s);
        """

        values = (document_id, index, chunk, chunk_hash, embedding_vector)
        cursor.execute(insert_query, values)

    connection.commit()
    cursor.close()
    connection.close()

def add_text_to_database(text: str, file_name: str, file_size: int, file_type: str, user_id: int = 1):
    """
    Основной интерфейс для добавления текста в базу данных.
    """
    # Разделение текста на куски
    chunks = split_into_chunks(text)

    # Создаем запись в таблице documents
    document_id = create_document_record(file_name, file_size, file_type, user_id=user_id)

    # Сохраняем куски в базу данных
    save_chunks_to_db(chunks, document_id)

    return len(chunks)