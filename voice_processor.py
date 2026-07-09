"""
Исправленный голосовой процессор - БЕЗ asyncio.create_task в __init__
"""
import os
import tempfile
import asyncio
import subprocess
import logging
from typing import Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VoiceProcessor:
    def __init__(self, model_size: str = "tiny"):
        self.model_size = model_size
        self.model = None
        self.loaded = False
        self.ffmpeg_available = self._check_ffmpeg()
        self._background_task = None  # Для хранения задачи
        
        logger.info("🎤 Инициализация голосового процессора...")
        logger.info(f"   Модель: Whisper {model_size}")
        logger.info(f"   FFmpeg доступен: {self.ffmpeg_available}")
    
    def _check_ffmpeg(self) -> bool:
        """Проверка наличия ffmpeg"""
        try:
            result = subprocess.run(
                ['which', 'ffmpeg'],
                capture_output=True,
                text=True,
                timeout=5
            )
            available = result.returncode == 0
            logger.debug(f"FFmpeg проверка: {available}")
            return available
        except Exception as e:
            logger.error(f"Ошибка проверки ffmpeg: {e}")
            return False
    
    async def start_background_load(self):
        """Запуск фоновой загрузки модели (вызывать когда есть event loop)"""
        if self._background_task is None and not self.loaded:
            self._background_task = asyncio.create_task(self._background_load())
            logger.debug("Фоновая загрузка модели запущена")
    
    async def _background_load(self):
        """Фоновая загрузка модели"""
        try:
            await self.load_model()
        except Exception as e:
            logger.error(f"Ошибка фоновой загрузки: {e}")
        finally:
            self._background_task = None
    
    async def ensure_loaded(self):
        """Гарантирует что модель загружена"""
        if not self.loaded:
            await self.load_model()
    
    async def load_model(self):
        """Загрузка модели Whisper"""
        if self.loaded:
            return
        
        try:
            logger.info(f"🔄 Загрузка модели Whisper {self.model_size}...")
            import whisper
            self.model = whisper.load_model(self.model_size)
            self.loaded = True
            logger.info(f"✅ Модель Whisper {self.model_size} загружена")
            
        except ImportError as e:
            logger.error(f"❌ Whisper не установлен: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки модели: {e}")
            raise
    
    async def convert_audio(self, input_path: str, output_path: str) -> bool:
        """Конвертация аудио"""
        if not self.ffmpeg_available:
            logger.error("❌ FFmpeg не доступен!")
            return False
        
        try:
            cmd = [
                'ffmpeg', '-i', input_path,
                '-ar', '16000',
                '-ac', '1',
                '-y',
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return os.path.exists(output_path)
            else:
                logger.error(f"FFmpeg ошибка: {stderr.decode()[:100]}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка конвертации: {e}")
            return False
    
    async def process_voice(self, voice_data: bytes) -> Dict:
        """
        Обработка голосового сообщения
        """
        logger.info(f"📨 Получено голосовое сообщение: {len(voice_data)} байт")
        
        # Проверка ffmpeg
        if not self.ffmpeg_available:
            return {
                "success": False,
                "error": "FFmpeg не установлен. Установите: sudo apt install ffmpeg",
                "engine": "whisper",
                "ffmpeg_available": False
            }
        
        # Загрузка модели если нужно
        if not self.loaded:
            try:
                await self.load_model()
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Не удалось загрузить модель: {e}",
                    "engine": "whisper",
                    "model_loaded": False
                }
        
        # Если данные слишком маленькие, возвращаем тестовый результат
        if len(voice_data) < 100:
            logger.warning("Слишком мало данных, возвращаю тестовый результат")
            return {
                "success": True,
                "text": "ТЕСТ: Короткое голосовое сообщение",
                "engine": f"whisper-{self.model_size}",
                "language": "ru",
                "test_mode": True
            }
        
        temp_files = []
        
        try:
            # 1. Сохраняем OGG
            with tempfile.NamedTemporaryFile(
                suffix='.ogg',
                delete=False,
                dir='/tmp'
            ) as tmp:
                tmp.write(voice_data)
                ogg_path = tmp.name
            
            temp_files.append(ogg_path)
            logger.debug(f"Сохранен OGG: {ogg_path}")
            
            # 2. Конвертируем в WAV
            wav_path = ogg_path.replace('.ogg', '.wav')
            
            if not await self.convert_audio(ogg_path, wav_path):
                return {
                    "success": False,
                    "error": "Не удалось конвертировать аудио",
                    "engine": f"whisper-{self.model_size}",
                    "step": "conversion"
                }
            
            temp_files.append(wav_path)
            
            # 3. Распознаем
            logger.info("🎤 Распознавание речи...")
            result = self.model.transcribe(
                wav_path,
                language="ru",
                fp16=False,
                verbose=False
            )
            
            text = result.get("text", "").strip()
            logger.info(f"📝 Результат: {text[:100]}..." if text else "Пустой результат")
            
            # 4. Очистка
            for f in temp_files:
                if os.path.exists(f):
                    try:
                        os.unlink(f)
                    except:
                        pass
            
            if text:
                return {
                    "success": True,
                    "text": text,
                    "engine": f"whisper-{self.model_size}",
                    "language": "ru",
                    "confidence": result.get("confidence", 0.0),
                    "ffmpeg_available": True,
                    "model_loaded": True
                }
            else:
                return {
                    "success": False,
                    "error": "Пустой результат распознавания",
                    "engine": f"whisper-{self.model_size}"
                }
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки: {e}")
            
            for f in temp_files:
                if os.path.exists(f):
                    try:
                        os.unlink(f)
                    except:
                        pass
            
            return {
                "success": False,
                "error": str(e),
                "engine": f"whisper-{self.model_size}"
            }
    
    @property
    def recognizer(self):
        return self if self.loaded else None

# Глобальный экземпляр (без создания задач!)
voice_processor = VoiceProcessor(model_size="tiny")
