import hashlib
import psycopg2
from typing import List
from transformers import AutoTokenizer, AutoModel
import numpy as np
import os
from dotenv import load_dotenv
from logger import logger

# Загрузим переменные окружения
load_dotenv()

# Модель для векторизации
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
tokenizer = None
model = None
DB_PASSWORD = os.getenv("DB_PASSWORD")

# ИНИЦИАЛИЗИРУЕМ МОДЕЛЬ СРАЗУ ПРИ ЗАГРУЗКЕ МОДУЛЯ
logger.info("Инициализация модели при загрузке модуля...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModel.from_pretrained(MODEL_NAME)
logger.info("Модель успешно инициализирована")

def mean_pooling(model_output, attention_mask):
    """Средний пуллинг эмбеддингов."""
    token_embeddings = model_output.last_hidden_state.detach().cpu().numpy()
    input_mask_expanded = np.broadcast_to(np.expand_dims(attention_mask.cpu(), -1), token_embeddings.shape)
    sum_embeddings = np.sum(token_embeddings * input_mask_expanded, axis=1)
    sum_mask = np.clip(input_mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
    return sum_embeddings / sum_mask

def encode_text(text):
    """Преобразует текст в векторное представление."""
    try:
        logger.info(f"Кодирование текста длиной {len(text)} символов...")
        inputs = tokenizer([text], padding=True, truncation=True, max_length=512, return_tensors="pt")
        outputs = model(**inputs)
        embeddings = mean_pooling(outputs, inputs["attention_mask"])
        result = embeddings.flatten()
        logger.info(f"Получен вектор размерностью {result.shape}")
        return result
    except Exception as e:
        logger.error(f"Ошибка при кодировании текста: {e}")
        raise

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

    logger.info(f"Текст разделен на {len(chunks)} чанков")
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
    connection = None
    cursor = None
    try:
        logger.info(f"Подключение к БД для создания документа {file_name}")
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
        logger.info(f"Выполнение запроса: {insert_query} с values={values}")
        cursor.execute(insert_query, values)
        document_id = cursor.fetchone()[0]
        logger.info(f"Получен ID документа: {document_id}")

        connection.commit()
        return document_id
    except Exception as e:
        logger.error(f"Ошибка при создании записи документа: {e}")
        if connection:
            connection.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def save_chunks_to_db(chunks: List[str], document_id: int):
    """
    Сохраняет куски текста в базу данных.
    """
    connection = None
    cursor = None
    try:
        logger.info(f"Подключение к БД для сохранения чанков документа {document_id}")
        connection = psycopg2.connect(
            host="localhost",
            database="rag_system",
            user="rag_user",
            password=os.getenv("DB_PASSWORD"),
        )
        cursor = connection.cursor()
        
        logger.info(f"Начинаем сохранение {len(chunks)} чанков для документа {document_id}")
        
        for index, chunk in enumerate(chunks):
            try:
                logger.info(f"Обработка чанка {index + 1}/{len(chunks)}")
                logger.info(f"Текст чанка (первые 100 символов): {chunk[:100]}...")
                
                # Преобразуем кусок текста в векторное представление
                embedding_vector = encode_text(chunk)
                
                # Создаем хэш-чанк
                chunk_hash = calculate_md5_hash(chunk)
                logger.info(f"Хэш чанка: {chunk_hash}")
                
                # Преобразуем numpy array в список для psycopg2
                embedding_list = embedding_vector.tolist()
                logger.info(f"Размерность эмбеддинга: {len(embedding_list)}")
                
                # Подготовим запрос на вставку
                insert_query = """
                    INSERT INTO chunks (document_id, chunk_index, chunk_text, chunk_hash, embedding)
                    VALUES (%s, %s, %s, %s, %s);
                """
                
                values = (document_id, index, chunk, chunk_hash, embedding_list)
                logger.info(f"Выполнение INSERT для чанка {index + 1}")
                cursor.execute(insert_query, values)
                logger.info(f"Чанк {index + 1} успешно вставлен")
                
            except Exception as e:
                logger.error(f"Ошибка при сохранении чанка {index + 1}: {e}")
                raise

        connection.commit()
        logger.info(f"Все {len(chunks)} чанков успешно сохранены в БД")
        
    except Exception as e:
        logger.error(f"Ошибка при сохранении чанков в БД: {e}")
        if connection:
            connection.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def add_text_to_database(text: str, file_name: str, file_size: int, file_type: str, user_id: int = 1):
    """
    Основной интерфейс для добавления текста в базу данных.
    """
    try:
        logger.info(f"=== НАЧАЛО ОБРАБОТКИ ФАЙЛА: {file_name} ===")
        logger.info(f"Размер текста: {len(text)} символов")
        
        # Разделение текста на куски
        chunks = split_into_chunks(text)
        logger.info(f"Получено {len(chunks)} чанков")

        # Создаем запись в таблице documents
        logger.info("Создание записи в таблице documents...")
        document_id = create_document_record(file_name, file_size, file_type, user_id=user_id)
        logger.info(f"Создан документ с ID: {document_id}")

        # Сохраняем куски в базу данных
        logger.info("Сохранение чанков в базу данных...")
        save_chunks_to_db(chunks, document_id)
        
        logger.info(f"=== УСПЕШНО ЗАВЕРШЕНО: добавлено {len(chunks)} чанков для документа {document_id} ===")
        return len(chunks)
        
    except Exception as e:
        logger.error(f"КРИТИЧЕСКАЯ ОШИБКА в add_text_to_database: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise