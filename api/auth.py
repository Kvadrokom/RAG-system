
"""
Модуль для работы с авторизацией в сервисах Сбера:
- GigaChat
- SaluteSpeech
"""

import time
import uuid
import logging
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Конфигурация
GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

# API ключи из переменных окружения
GIGACHAT_SECRET_KEY = os.getenv("GIGACHAT_SECRET_KEY")
SALUTE_SECRET_KEY = os.getenv("SALUTE_SPEECH_API_KEY")

# Проверка наличия ключей
if not GIGACHAT_SECRET_KEY:
    logger.warning("GIGACHAT_SECRET_KEY not set in environment variables")
if not SALUTE_SECRET_KEY:
    logger.warning("SALUTE_SPEECH_API_KEY not set in environment variables")

# Хранение токенов
_tokens = {
    "gigachat": {"token": None, "expires_at": 0},
    "salute": {"token": None, "expires_at": 0}
}


async def _get_token(service: str, secret_key: str, scope: str) -> str:
    """
    Внутренняя функция получения токена для сервиса.
    
    Args:
        service: Название сервиса ('gigachat' или 'salute')
        secret_key: Basic токен для авторизации
        scope: Область доступа
    
    Returns:
        access_token
    
    Raises:
        Exception: При ошибке авторизации
    """
    global _tokens
    
    current_time = time.time()
    
    # Если токен еще действителен, возвращаем его
    if _tokens[service]["token"] and current_time < _tokens[service]["expires_at"]:
        logger.info(f"{service.capitalize()} token still valid, expires in {_tokens[service]['expires_at'] - current_time:.0f} seconds")
        return _tokens[service]["token"]
    
    logger.info(f"Requesting new {service} token...")
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {secret_key}"
    }
    data = {"scope": scope}
    
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.post(GIGACHAT_AUTH_URL, headers=headers, data=data) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                logger.error(f"Failed to get {service} token: {resp.status} - {error_text}")
                raise Exception(f"Token error for {service}: {resp.status} - {error_text}")
            
            response = await resp.json()
            logger.debug(f"{service.capitalize()} token response: {list(response.keys())}")
            
            token = response.get("access_token")
            if not token:
                raise Exception(f"No access_token in response for {service}")
            
            expires_in = response.get("expires_in", 3600)
            _tokens[service]["token"] = token
            _tokens[service]["expires_at"] = current_time + expires_in
            
            logger.info(f"{service.capitalize()} token obtained, expires in {expires_in} seconds")
            return token


async def get_gigachat_token() -> str:
    """
    Получает токен для GigaChat.
    
    Returns:
        access_token для GigaChat
    
    Raises:
        ValueError: Если не задан GIGACHAT_SECRET_KEY
        Exception: При ошибке авторизации
    """
    if not GIGACHAT_SECRET_KEY:
        raise ValueError("GIGACHAT_SECRET_KEY not set in environment variables")
    
    return await _get_token("gigachat", GIGACHAT_SECRET_KEY, "GIGACHAT_API_PERS")


async def get_salute_token() -> str:
    """
    Получает токен для SaluteSpeech.
    
    Returns:
        access_token для SaluteSpeech
    
    Raises:
        ValueError: Если не задан SALUTE_SPEECH_API_KEY
        Exception: При ошибке авторизации
    """
    if not SALUTE_SECRET_KEY:
        raise ValueError("SALUTE_SPEECH_API_KEY not set in environment variables")
    
    return await _get_token("salute", SALUTE_SECRET_KEY, "SALUTE_SPEECH_PERS")


async def get_access_token() -> str:
    """
    Функция для совместимости с текстовым эндпоинтом.
    Возвращает токен GigaChat.
    
    Returns:
        access_token для GigaChat
    """
    return await get_gigachat_token()


def get_token_info() -> dict:
    """
    Возвращает информацию о текущих токенах (для отладки).
    """
    current_time = time.time()
    return {
        "gigachat": {
            "has_token": _tokens["gigachat"]["token"] is not None,
            "expires_at": _tokens["gigachat"]["expires_at"],
            "expires_in": max(0, _tokens["gigachat"]["expires_at"] - current_time)
        },
        "salute": {
            "has_token": _tokens["salute"]["token"] is not None,
            "expires_at": _tokens["salute"]["expires_at"],
            "expires_in": max(0, _tokens["salute"]["expires_at"] - current_time)
        }
    }


# ============================================================
# БЛОК ДЛЯ ТЕСТИРОВАНИЯ (выполняется только при прямом запуске)
# ============================================================
if __name__ == "__main__":
    import asyncio
    
    # Настройка логов для тестирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    async def test_auth():
        print("=" * 60)
        print("Тестирование авторизации в сервисах Сбера")
        print("=" * 60)
        
        # Тестируем получение токена для GigaChat
        try:
            print("\n1. Получение токена для GigaChat...")
            gigachat_token = await get_gigachat_token()
            print(f"   ✅ Токен получен: {gigachat_token[:50]}...")
            print(f"   📅 Информация: {get_token_info()['gigachat']}")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
        
        # Тестируем получение токена для SaluteSpeech
        try:
            print("\n2. Получение токена для SaluteSpeech...")
            salute_token = await get_salute_token()
            print(f"   ✅ Токен получен: {salute_token[:50]}...")
            print(f"   📅 Информация: {get_token_info()['salute']}")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
        
        # Тестируем повторное получение (должен вернуть кэшированный токен)
        print("\n3. Повторное получение (проверка кэширования)...")
        start = time.time()
        token2 = await get_gigachat_token()
        elapsed = time.time() - start
        print(f"   ⚡ Токен получен за {elapsed*1000:.2f} мс (из кэша)")
        
        print("\n" + "=" * 60)
        print("📊 Статус токенов:")
        info = get_token_info()
        print(f"   GigaChat: {'✅ активен' if info['gigachat']['has_token'] else '❌ отсутствует'}")
        print(f"   SaluteSpeech: {'✅ активен' if info['salute']['has_token'] else '❌ отсутствует'}")
        print("=" * 60)
    
    asyncio.run(test_auth())