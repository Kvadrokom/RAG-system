import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="rag_system",
    user="rag_user",
    password="StrongRAGpassword123"
)

cursor = conn.cursor()

# Создать таблицы
cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        file_name VARCHAR(500) NOT NULL,
        file_path TEXT,
        file_type VARCHAR(50),
        file_size BIGINT,
        status VARCHAR(50) DEFAULT 'uploaded',
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        metadata JSONB DEFAULT '{}'
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS chunks (
        id SERIAL PRIMARY KEY,
        document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
        chunk_index INTEGER NOT NULL,
        chunk_text TEXT NOT NULL,
        embedding vector(384),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

conn.commit()
cursor.close()
conn.close()

print("✅ Таблицы созданы!")
