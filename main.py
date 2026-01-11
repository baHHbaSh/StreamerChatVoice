from Parser import YouTubeChatParser, ChatMessage
from tts import tts

TTS = tts()

def log(message: ChatMessage):
    """
    Обработчик новых сообщений из чата
    
    Args:
        message: Объект сообщения с данными
    """
    # Можно использовать структурированные данные
    print(f"💬 [{message.TimestampFormatted}] {message.Author}: {message.Message}\n")

def Sound(message: ChatMessage):
    TTS.ospeak(message.Message, False)

def main():
    """
    Главная функция для запуска парсера с подпиской на сообщения
    """
    # Пример использования
    video_url = input("Введите URL YouTube стрима: ").strip()
    
    if not video_url:
        print("❌ URL не может быть пустым!")
        return
    
    parser = YouTubeChatParser(video_url)
    
    # Подписываемся на новые сообщения
    parser.on(log)
    parser.on(Sound)
    
    # Можно добавить несколько подписок
    # parser.on(lambda msg: print(f"Другая подписка: {msg.Message}"))
    
    try:
        parser.start()
        #На ctrl + c, похер
        #пользователь должен знать почему всё выключилось, если написал ctrl+ c
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        parser.stop()
    finally:
        # Очищаем подписки только при реальном завершении программы
        # Вызываем clear() только после того, как пользователь подтвердит завершение
        input("Нажмите Enter для завершения")
        parser.clear()


if __name__ == "__main__":
    main()