import psycopg2
import sys
import os
from dotenv import load_dotenv


print("🔧 Создание полной структуры RAG системы...")

ENV_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.env"))
load_dotenv(ENV_DIR)

try:
    conn = psycopg2.connect(
        host="localhost",
        database="rag_system",
        user="rag_user",
        password=os.getenv("DB_PASSWORD"),
    )

    cursor = conn.cursor()

    # 1. Проверить и создать таблицу users если нет
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            username VARCHAR(100),
            first_name VARCHAR(100),
            last_name VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            settings JSONB DEFAULT '{}'
        )
    """)

    # 2. Обновить таблицу documents если нужно
    # Сначала проверим структуру
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'documents'
    """)

    existing_columns = [row[0] for row in cursor.fetchall()]

    # Если таблицы нет или она базовая - пересоздать
    if not existing_columns or "user_id" in existing_columns:
        print("⚠️  Обновляю структуру documents...")

        # Создать временную таблицу если есть данные
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents_new (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id) ON DELETE CASCADE,
                telegram_chat_id BIGINT,
                file_name VARCHAR(500) NOT NULL,
                file_path TEXT,
                file_hash VARCHAR(64) UNIQUE,
                file_type VARCHAR(50),
                file_size BIGINT,
                status VARCHAR(50) DEFAULT 'uploaded',
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                metadata JSONB DEFAULT '{}',
                total_chunks INTEGER DEFAULT 0
            )
        """)

        # Создать admin пользователя для связи
        cursor.execute("""
            INSERT INTO users (telegram_id, username) 
            VALUES (0, 'system_admin')
            ON CONFLICT (telegram_id) DO NOTHING
        """)

    # 3. Таблица chunks с индексами
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            chunk_hash VARCHAR(64) NOT NULL,
            embedding vector(384),
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT unique_doc_chunk UNIQUE(document_id, chunk_index)
        )
    """)

    # 4. Создать индексы если их нет
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_embedding 
        ON chunks USING ivfflat (embedding vector_cosine_ops) 
        WITH (lists = 100)
    """)

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(chunk_hash)")

    conn.commit()
    cursor.close()
    conn.close()

    print("✅ Структура базы данных готова!")

except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
