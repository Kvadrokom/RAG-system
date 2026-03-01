#!/usr/bin/env python3
import importlib
import sys
import os

# Удаляем старый модуль из кэша
if 'voice_processor' in sys.modules:
    print("🗑️ Удаляю старый voice_processor из кэша...")
    del sys.modules['voice_processor']

# Также удаляем если есть в подмодулях
modules_to_delete = []
for mod_name in sys.modules:
    if 'voice_processor' in mod_name:
        modules_to_delete.append(mod_name)

for mod_name in modules_to_delete:
    del sys.modules[mod_name]
    print(f"🗑️ Удален: {mod_name}")

# Принудительно перезагружаем
print("🔄 Принудительная перезагрузка модуля...")
import voice_processor
importlib.reload(voice_processor)

# Теперь тестируем
print(f"\n✅ Перезагружен: {voice_processor}")
print(f"   Объект: {voice_processor.voice_processor}")
print(f"   Атрибуты: {dir(voice_processor.voice_processor)}")

# Проверяем ffmpeg_available
if hasattr(voice_processor.voice_processor, 'ffmpeg_available'):
    print(f"   ffmpeg_available: {voice_processor.voice_processor.ffmpeg_available}")
else:
    print("   ❌ ffmpeg_available НЕ НАЙДЕН!")
