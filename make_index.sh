#!/bin/bash

# 1. Создать индекс для RAG
curl -ku admin:"4rtKMp5HzCRX1YI=" -X PUT "https://localhost:9200/rag-logs" \
  -H "Content-Type: application/json" \
  -d '{
    "settings": { "number_of_shards": 1, "number_of_replicas": 0 },
    "mappings": {
      "properties": {
        "@timestamp": { "type": "date" },
        "source": { "type": "keyword" },
        "host": { "type": "keyword" },
        "error_severity": { "type": "keyword" },
        "message_text": { "type": "text" },
        "file": { "type": "keyword" },
        "line": { "type": "integer" }
      }
    }
  }'

sleep 5

# 2. Создать индекс для PostgreSQL
curl -ku admin:"4rtKMp5HzCRX1YI=" -X PUT "https://localhost:9200/postgresql-logs" \
  -H "Content-Type: application/json" \
  -d '{
    "settings": { "number_of_shards": 1, "number_of_replicas": 0 },
    "mappings": {
      "properties": {
        "@timestamp": { "type": "date" },
        "source": { "type": "keyword" },
        "host": { "type": "keyword" },
        "error_severity": { "type": "keyword" },
        "message_text": { "type": "text" },
        "database_name": { "type": "keyword" },
        "user_name": { "type": "keyword" }
      }
    }
  }'

