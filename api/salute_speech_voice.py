"""
Модуль для работы с SaluteSpeech API.
Содержит только логику распознавания речи через прямой API-вызов.
"""

import tempfile
import logging
from pathlib import Path
import aiohttp
import os

# Импортируем функцию получения токена из auth.py
from auth import get_salute_token

logger = logging.getLogger(__name__)


class SaluteSpeechError(Exception):
    """Исключение для ошибок SaluteSpeech"""
    pass


async def _recognize_via_api(token: str, file_path: str, language: str) -> str:
    """
    Прямой вызов API SaluteSpeech (синхронное распознавание).
    
    Args:
        token: Bearer токен для авторизации
        file_path: Путь к аудиофайлу
        language: Язык распознавания ('ru-RU', 'en-US')
    
    Returns:
        Распознанный текст
    """
    # Правильный эндпоинт для синхронного распознавания
    recognize_url = "https://smartspeech.sber.ru/rest/v1/speech:recognize"
    
    # Читаем аудиофайл
    with open(file_path, 'rb') as f:
        audio_data = f.read()
    
    # Определяем Content-Type по расширению файла
    ext = Path(file_path).suffix.lower()
    content_types = {
        '.ogg': 'audio/ogg;codecs=opus',
        '.mp3': 'audio/mpeg',
        '.opus': 'audio/ogg;codecs=opus',
        '.wav': 'audio/x-pcm;bit=16;rate=16000',
        '.m4a': 'audio/mp4'
    }
    content_type = content_types.get(ext, 'audio/ogg;codecs=opus')
    
    # Параметры передаются через query string
    params = {
        'language': language,
        'model': 'general'  # или 'callcenter' для телефонных разговоров
    }
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': content_type
    }
    
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.post(recognize_url, headers=headers, params=params, data=audio_data) as resp:
            if resp.status == 200:
                result = await resp.json()
                # Формат ответа: {"result": [{"text": "..."}]}
                return result
            else:
                error_text = await resp.text()
                raise Exception(f"API error {resp.status}: {error_text}")


async def recognize_audio(
    audio_bytes: bytes,
    filename: str = "audio.ogg",
    language: str = "ru-RU"
) -> str:
    """
    Распознает речь из аудио через SaluteSpeech API.
    
    Args:
        audio_bytes: Байты аудиофайла
        filename: Имя файла (для определения расширения)
        language: Язык ('ru-RU', 'en-US')
    
    Returns:
        Распознанный текст
    
    Raises:
        SaluteSpeechError: При ошибке распознавания
    """
    try:
        # Получаем актуальный токен
        token = await get_salute_token()
        logger.info("SaluteSpeech token obtained")
    except Exception as e:
        logger.error(f"Failed to get token: {e}")
        raise SaluteSpeechError(f"Authentication failed: {str(e)}")
    
    # Определяем расширение файла
    ext = Path(filename).suffix or ".ogg"
    
    # Сохраняем во временный файл
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    
    try:
        # Прямой вызов API
        result = await _recognize_via_api(token, tmp_path, language)
        
        if result:
            logger.info(f"Распознано: {result['result']}...")
        else:
            logger.warning("Распознавание вернуло пустой результат")
        
        return result['result'][0]
        
    except Exception as e:
        logger.error(f"Ошибка распознавания: {e}")
        raise SaluteSpeechError(f"Speech recognition failed: {str(e)}")
    
    finally:
        # Удаляем временный файл
        if Path(tmp_path).exists():
            Path(tmp_path).unlink()
            logger.debug(f"Временный файл удалён: {tmp_path}")


# ============================================================
# БЛОК ДЛЯ ТЕСТИРОВАНИЯ (выполняется только при прямом запуске)
# ============================================================
if __name__ == "__main__":
    import asyncio
    import sys
    
    # Настройка логов для тестирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    async def main():
        if len(sys.argv) < 2:
            print("=" * 60)
            print("Использование: python my_salute_speech.py <путь_к_аудиофайлу>")
            print("=" * 60)
            print(f"Пример: python my_salute_speech.py voice.ogg")
            print(f"Поддерживаемые форматы: .ogg, .mp3, .opus, .wav, .m4a")
            sys.exit(1)
        
        file_path = sys.argv[1]
        
        if not os.path.exists(file_path):
            print(f"❌ Файл не найден: {file_path}")
            sys.exit(1)
        
        print(f"🎤 Распознавание файла: {file_path}")
        print(f"📏 Размер: {os.path.getsize(file_path)} байт")
        print("-" * 60)
        
        try:
            with open(file_path, "rb") as f:
                audio_bytes = f.read()
            
            text = await recognize_audio(audio_bytes, Path(file_path).name)
            
            print(f"\n✅ Результат распознавания:")
            print("-" * 60)
            print(text)
            print("-" * 60)
            
        except SaluteSpeechError as e:
            print(f"\n❌ Ошибка: {e}\n")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Непредвиденная ошибка: {e}\n")
            sys.exit(1)
    
    asyncio.run(main())