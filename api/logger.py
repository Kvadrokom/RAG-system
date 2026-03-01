import logging
import os

def setup_logger(log_dir='/var/log/rag_system_log', log_file="rag_system.log", name=__name__):
    """
    Настройка логгера
    
    Args:
        log_dir: Директория для логов
        log_file: Имя файла логов
        name: Имя логгера
    """
    
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    logger = logging.getLogger(name)
    
    # Если логгер уже настроен - возвращаем его
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.INFO)
    
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
    
    # Консольный обработчик (только ошибки)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Отключаем логи сторонних библиотек
    logging.getLogger('urllib3').setLevel(logging.ERROR)
    
    return logger


logger = setup_logger()
