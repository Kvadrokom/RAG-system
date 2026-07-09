#!/usr/bin/env python3
"""
Безопасный тест голосового процессора
"""

import asyncio
import sys
import os

# Очистка кэша
if "voice_processor" in sys.modules:
    del sys.modules["voice_processor"]

sys.path.insert(0, os.path.dirname(__file__))


async def main():
    print("🚀 Безопасный тест голосового процессора")
    print("=" * 50)

    # Импортируем внутри async функции
    import voice_processor

    print("✅ Модуль загружен")
    vp = voice_processor.voice_processor

    print("\n📋 Свойства объекта:")
    print(f"   ffmpeg_available: {vp.ffmpeg_available}")
    print(f"   loaded: {vp.loaded}")
    print(f"   model_size: {vp.model_size}")

    # Запускаем фоновую загрузку
    print("\n🔄 Запуск фоновой загрузки...")
    await vp.start_background_load()

    # Тест 1: Быстрый тест
    print("\n🧪 Тест 1: Быстрая проверка...")
    result1 = await vp.process_voice(b"tiny test")
    print(f"   Успех: {result1.get('success')}")
    print(f"   Текст: {result1.get('text', 'N/A')[:50]}")

    # Ждем немного для фоновой загрузки
    import time

    time.sleep(1)

    # Тест 2: С большими данными
    print("\n🧪 Тест 2: С имитацией голосовых данных...")
    fake_audio = b"fake ogg audio data " * 50  # 1000+ байт
    result2 = await vp.process_voice(fake_audio)

    print(f"   Успех: {result2.get('success')}")
    print(f"   Ошибка: {result2.get('error', 'Нет ошибки')}")
    if result2.get("success") and result2.get("text"):
        print(f"   Текст: {result2.get('text')[:100]}...")

    # Проверяем загрузилась ли модель
    print("\n📊 Финальный статус:")
    print(f"   loaded: {vp.loaded}")
    print(f"   model: {'✅ есть' if vp.model else '❌ нет'}")

    return result1.get("success", False) or result2.get("success", False)


if __name__ == "__main__":
    success = asyncio.run(main())

    print("\n" + "=" * 50)
    if success:
        print("🎉 ГОЛОСОВОЙ ПРОЦЕССОР РАБОТАЕТ!")
    else:
        print("⚠️  Есть проблемы, требуется отладка")
    print("=" * 50)
