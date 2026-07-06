import logging
import os
import sys
from fastapi import Request
from fastapi.responses import JSONResponse
import traceback

def setup_logger(log_dir='/var/log/rag_system_log', log_file="rag_system.log", name=__name__):
    """
    Настройка логгера
    """
    
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Настраиваем корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Очищаем существующие обработчики
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    logger = logging.getLogger(name)
    
    # Если логгер уже настроен - возвращаем его
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.INFO)
    logger.propagate = False  # НЕ передаем логи родительскому логгеру
    
    formatter = logging.Formatter(
        '%(levelname)s (%(asctime)s): %(message)s (Line: %(lineno)d) [%(filename)s]',
        datefmt='%d/%m/%Y %H:%M:%S'
    )
    
    # Файловый обработчик
    file_handler = logging.FileHandler(
        os.path.join(log_dir, log_file), 
        mode='a', 
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # Консольный обработчик (только ошибки)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.ERROR)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Отключаем логи сторонних библиотек
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('transformers').setLevel(logging.WARNING)
    
    # Перенаправляем все логи из других модулей в файл
    for handler in root_logger.handlers:
        root_logger.removeHandler(handler)
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.INFO)
    
    return logger


def create_logging_middleware(logger):
    """
    Создает middleware для логирования HTTP ошибок.
    """
    
    async def logging_middleware(request: Request, call_next):
        try:
            response = await call_next(request)
            
            if response.status_code == 404 and any(scan_path in request.url.path for scan_path in ['.env', 'wp-config', 'docker-compose']):
                return response  # Не логируем сканирование
            # Логируем ТОЛЬКО ошибки (4xx и 5xx)
            elif response.status_code >= 400:
                client_ip = request.client.host if request.client else 'unknown'
                logger.warning(
                    f"HTTP {response.status_code} | "
                    f"{request.method} {request.url.path} | "
                    f"Client: {client_ip}"
                )
            
            return response
            
        except Exception as e:
            logger.error(
                f"Unhandled exception in {request.method} {request.url.path}\n"
                f"Error: {str(e)}\n"
                f"Traceback:\n{traceback.format_exc()}"
            )
            
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"}
            )
    
    return logging_middleware


logger = setup_logger()