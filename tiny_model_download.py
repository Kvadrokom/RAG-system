import whisper
import os

print(f'Домашняя директория: {os.path.expanduser(\"~\")}')
print(f'Кэш путь: {os.path.expanduser(\"~/.cache/whisper\")}')

# Пробуем скачать
try:
    print('🔄 Скачиваю модель tiny...')
    model = whisper.load_model('tiny')
    print('✅ Модель скачана!')
    
    # Проверьте файл
    model_path = os.path.expanduser('~/.cache/whisper/tiny.pt')
    if os.path.exists(model_path):
        size = os.path.getsize(model_path) / 1024 / 1024
        print(f'Файл: {model_path}')
        print(f'Размер: {size:.1f} MB')
    else:
        print('❌ Файл не найден в ожидаемом месте')
        
except Exception as e:
    print(f'❌ Ошибка: {e}')
    import traceback
    traceback.print_exc()
