"""
Упрощенный голосовой процессор для тестирования
"""
import asyncio
import logging
from typing import Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VoiceProcessor:
    def __init__(self):
        self.loaded = True
        self.ffmpeg_available = False  # Для совместимости
        self.model_size = "test"
        logger.info("✅ Голосовой процессор инициализирован (тестовый режим)")
    
    async def process_voice(self, voice_data: bytes) -> Dict:
        """
        Тестовый метод - возвращает фиктивный текст инцидента
        """
        await asyncio.sleep(0.5)  # Имитация обработки
        
        # Разные тексты для разных размеров данных
        if len(voice_data) < 100:
            text = "Короткое голосовое сообщение"
        else:
            text = """ИНЦИДЕНТ: IM0220463101
СЕРВИС: МегаЦУКС
ВРЕМЯ: 10:30
ПРИОРИТЕТ: Средний
ПРОБЛЕМА: Дисковое пространство переполнено
ВЛИЯНИЕ: Возможны задержки обработки"""
        
        return {
            "success": True,
            "text": text,
            "engine": "test-mode",
            "language": "ru",
            "confidence": 0.9,
            "note": "Тестовый режим. Для реального распознавания установите ffmpeg и Whisper."
        }
    
    async def load_model(self):
        """Заглушка для совместимости"""
        self.loaded = True
        logger.info("Тестовый режим: модель не требуется")
    
    @property
    def recognizer(self):
        return self

# Глобальный экземпляр
voice_processor = VoiceProcessor()
