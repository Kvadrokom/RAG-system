import logging
import os
import sys

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

logger = setup_logger()