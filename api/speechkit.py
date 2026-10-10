"""Распознавание голосовых сообщений через Yandex SpeechKit (async API v2)."""
import os
import aiohttp
import asyncio
import time
import uuid
import boto3
import requests
from io import BytesIO
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

# ===== Настройки =====
API_KEY = os.getenv("YANDEX_API_KEY")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

FOLDER_ID = "b1g6us6gaf9rfot0osij"
BUCKET_NAME = "speechkit-bucket-ragsystem"

LANGUAGE_CODE = "ru-RU"
MODEL = "deferred-general"
PROFANITY_FILTER = False
LITERATURE_TEXT = True

POLL_INTERVAL = 5
POLL_MAX_ATTEMPTS = 120
HTTP_TIMEOUT = 30

STORAGE_ENDPOINT = "https://storage.yandexcloud.net"
STT_URL = "https://transcribe.api.cloud.yandex.net/speech/stt/v2/longRunningRecognize"
OPERATION_URL = "https://operation.api.cloud.yandex.net/operations/{op_id}"


class RecognitionError(Exception):
    """Ошибка распознавания (проблема на стороне SpeechKit)."""


class RecognitionTimeout(RecognitionError):
    """Операция распознавания не завершилась за отведённое время."""
    
class SpeechError(Exception):
    """Исключение для ошибок Speechkit"""
    pass


# ===== Object Storage =====
def get_s3_client():
    session = boto3.session.Session()
    return session.client(
        service_name="s3",
        endpoint_url=STORAGE_ENDPOINT,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name="ru-central1",
    )


def upload_to_storage(audio_bytes: bytes, object_key: str) -> str:
    """Загружает аудио из памяти в Object Storage, возвращает публичный URI."""
    s3 = get_s3_client()
    s3.upload_fileobj(BytesIO(audio_bytes), BUCKET_NAME, object_key)
    return f"{STORAGE_ENDPOINT}/{BUCKET_NAME}/{object_key}"


def delete_from_storage(object_key: str) -> None:
    """Удаляет объект из бакета (best-effort, не роняет основной поток)."""
    try:
        get_s3_client().delete_object(Bucket=BUCKET_NAME, Key=object_key)
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ Не удалось удалить {object_key}: {e}")
        
        
async def upload_to_storage_async(audio_bytes: bytes, object_key: str) -> str:
    return await asyncio.to_thread(upload_to_storage, audio_bytes, object_key)

async def delete_from_storage_async(object_key: str) -> None:
    await asyncio.to_thread(delete_from_storage, object_key)


# ===== SpeechKit =====
def _build_body(file_uri: str) -> dict:
    return {
        "config": {
            "specification": {
                "languageCode": LANGUAGE_CODE,
                "model": MODEL,
                "profanityFilter": PROFANITY_FILTER,
                "literature_text": LITERATURE_TEXT,
                # Для OggOpus формат и частоту указывать не нужно
            }
        },
        "audio": {"uri": file_uri},
    }


def _extract_text(op: dict) -> str:
    """Достаёт текст из ответа операции longRunningRecognize."""
    response = op.get("response", {})
    text_parts = []
    for chunk in response.get("chunks", []):
        for alternative in chunk.get("alternatives", []):
            text_parts.append(alternative.get("text", ""))
    return " ".join(text_parts).strip()


async def recognize_audio_speechkit(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    """
    Загружает аудио в Object Storage и запускает асинхронное распознавание.
    
    :param audio_bytes: содержимое аудиофайла
    :param filename: имя файла (используется для расширения/ключа объекта)
    :return: распознанный текст (пустая строка, если речь не распознана)
    :raises RecognitionTimeout: операция не завершилась вовремя
    :raises RecognitionError: SpeechKit вернул ошибку
    """
    if not audio_bytes:
        raise ValueError("Пустой аудиофайл")
    
    object_key = f"input/{uuid.uuid4().hex}_{filename}"
    
    # Загрузка в Object Storage (если тоже синхронная — нужна асинхронная версия)
    file_uri = await upload_to_storage_async(audio_bytes, object_key)
    
    headers = {
        "Authorization": f"Api-Key {API_KEY}",
        "Content-Type": "application/json",
    }
    
    try:
        # Используем aiohttp вместо requests
        async with aiohttp.ClientSession() as session:
            # 1. Запуск операции распознавания
            async with session.post(
                STT_URL, 
                headers=headers, 
                json=_build_body(file_uri), 
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RecognitionError(f"SpeechKit error: {resp.status} - {error_text}")
                
                data = await resp.json()
                operation_id = data["id"]
            
            # 2. Ожидание завершения операции
            op_url = OPERATION_URL.format(op_id=operation_id)
            op = None
            
            for _ in range(POLL_MAX_ATTEMPTS):
                async with session.get(
                    op_url, 
                    headers=headers, 
                    timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
                ) as r:
                    if r.status != 200:
                        error_text = await r.text()
                        raise RecognitionError(f"Operation error: {r.status} - {error_text}")
                    
                    op = await r.json()
                    
                    if op.get("done"):
                        break
                
                # Асинхронный sleep (не блокирует event loop!)
                await asyncio.sleep(POLL_INTERVAL)
            else:
                raise RecognitionTimeout("Превышено время ожидания распознавания")
            
            # 3. Проверка ошибок
            if "error" in op:
                raise RecognitionError(f"Ошибка распознавания: {op['error']}")
            
            return _extract_text(op)
    
    finally:
        # Удаление файла из хранилища
        await delete_from_storage_async(object_key)



def recognize_file(path: str) -> str:
    """Удобная обёртка: распознать локальный файл."""
    with open(path, "rb") as f:
        return recognize_audio(f.read(), filename=os.path.basename(path))


# ===== Ручной тест =====
if __name__ == "__main__":
    test_file = "/tmp/tmpxt6oprfp.ogg"
    if not os.path.exists(test_file):
        print(f"❌ Файл {test_file} не найден")
        exit(1)

    with open(test_file, "rb") as f:
        audio_bytes = f.read()

    print(f"📁 Файл загружен: {len(audio_bytes)} байт")

    result = recognize_audio_speechkit(audio_bytes, filename=os.path.basename(test_file))

    if result:
        print("\n" + "=" * 50)
        print("📝 РАСПОЗНАННЫЙ ТЕКСТ:")
        print("=" * 50)
        print(result)
        print("=" * 50)
    else:
        print("❌ Распознавание не дало результата")