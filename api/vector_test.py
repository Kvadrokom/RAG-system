import psycopg2
import numpy as np
from rag_enrich import encode_text
import os

# Подключение к БД
conn = psycopg2.connect(
    host="localhost",
    database="rag_system",
    user="rag_user",
    password=os.getenv("DB_PASSWORD")
)
cur = conn.cursor()

# Тестовые запросы
test_queries = [
    "инцидент",
    "шаблон оповещения",
    "регистрация инцидента",
    "низкий приоритет",
    "АС ОКЭй",
    "оповещение дежурного администратора"
]

for query in test_queries:
    # Вектор запроса
    q_vec = encode_text(query, is_query=True)
    q_vec_list = q_vec.tolist()
    q_vec_str = '[' + ','.join(str(x) for x in q_vec_list) + ']'
    
    # Ищем ближайшие чанки
    cur.execute("""
        SELECT chunk_text, embedding <=> %s::vector as distance
        FROM chunks 
        ORDER BY embedding <=> %s::vector 
        LIMIT 3
    """, (q_vec_str, q_vec_str))
    
    results = cur.fetchall()
    print(f"\n📝 Запрос: '{query}'")
    print(f"   Найдено: {len(results)} чанков")
    for i, (text, dist) in enumerate(results, 1):
        print(f"   {i}. Расстояние: {dist:.4f} | {text[:80]}...")