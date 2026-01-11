#Низкоуровневое API, написано LLM, с коррекцией.
"""
Парсер чата YouTube стрима через прямое подключение (без официального API)
Использует внутренние эндпоинты YouTube для получения сообщений чата в реальном времени
"""

import requests
import json
import re
import time
import threading
from typing import Optional, Dict, List, Callable, Set
from urllib.parse import urlparse, parse_qs
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ChatMessage:
    """
    Структура данных для сообщения из чата YouTube
    
    Attributes:
        Author: Имя автора сообщения
        Message: Текст сообщения
        Timestamp: Временная метка в микросекундах (Unix timestamp)
        TimestampFormatted: Отформатированная временная метка (строка)
        VideoId: ID видео/стрима
        MessageId: Уникальный идентификатор сообщения (если доступен)
    """
    Author: str
    Message: str
    Timestamp: int
    TimestampFormatted: str
    VideoId: str
    MessageId: Optional[str] = None
    
    def __str__(self) -> str:
        """
        Строковое представление сообщения
        
        Returns:
            Отформатированная строка сообщения
        """
        return f"[{self.TimestampFormatted}] {self.Author}: {self.Message}"
    
    def to_dict(self) -> Dict:
        """
        Преобразует сообщение в словарь
        
        Returns:
            Словарь с данными сообщения
        """
        return {
            'author': self.Author,
            'message': self.Message,
            'timestamp': self.Timestamp,
            'timestamp_formatted': self.TimestampFormatted,
            'video_id': self.VideoId,
            'message_id': self.MessageId
        }


class YouTubeChatParser:
    """
    Класс для парсинга чата YouTube стрима через прямое подключение
    """
    
    def __init__(self, video_url: str):
        """
        Инициализация парсера
        
        Args:
            video_url: URL YouTube видео/стрима
        """
        self.VideoUrl = video_url
        self.VideoId = self._extract_video_id(video_url)
        self.ContinuationToken: Optional[str] = None
        self.Session = requests.Session()
        self.Session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': f'https://www.youtube.com/watch?v={self.VideoId}',
        })
        self.IsRunning = False
        self._subscribers: Set[Callable[[ChatMessage], None]] = set()
        self._messageCounter = 0
        self._activeTimers: List[threading.Timer] = []
        self._loopLock = threading.Lock()
        self._stopEvent = threading.Event()
        self._startTime: Optional[int] = None  # Время запуска парсера (Unix timestamp в секундах)
        
    def _extract_video_id(self, url: str) -> str:
        """
        Извлекает ID видео из URL
        
        Args:
            url: URL YouTube видео
            
        Returns:
            ID видео
        """
        parsed = urlparse(url)
        if parsed.hostname in ['youtu.be']:
            return parsed.path[1:]
        elif parsed.hostname in ['www.youtube.com', 'youtube.com', 'm.youtube.com']:
            if parsed.path == '/watch':
                return parse_qs(parsed.query)['v'][0]
            elif parsed.path.startswith('/embed/'):
                return parsed.path.split('/')[2]
            elif parsed.path.startswith('/v/'):
                return parsed.path.split('/')[2]
        raise ValueError(f"Не удалось извлечь ID видео из URL: {url}")
    
    def _get_initial_data(self) -> Optional[Dict]:
        """
        Получает начальные данные страницы, включая continuation token для чата
        
        Returns:
            Словарь с данными страницы или None при ошибке
        """
        try:
            url = f"https://www.youtube.com/watch?v={self.VideoId}"
            response = self.Session.get(url)
            response.raise_for_status()
            
            html = response.text
            
            # Способ 1: Ищем ytInitialData
            patterns = [
                r'var ytInitialData = ({.+?});',
                r'window\["ytInitialData"\] = ({.+?});',
                r'ytInitialData\s*=\s*({.+?});',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        return data
                    except json.JSONDecodeError:
                        continue
            
            # Способ 2: Ищем ytInitialPlayerResponse (может содержать данные чата)
            patterns_player = [
                r'var ytInitialPlayerResponse = ({.+?});',
                r'window\["ytInitialPlayerResponse"\] = ({.+?});',
                r'ytInitialPlayerResponse\s*=\s*({.+?});',
            ]
            
            for pattern in patterns_player:
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    try:
                        player_data = json.loads(match.group(1))
                        # Пробуем найти continuation в player response
                        if player_data:
                            return {'playerResponse': player_data}
                    except json.JSONDecodeError:
                        continue
            
            # Способ 3: Ищем встроенные JSON данные в script тегах
            script_matches = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
            for script_content in script_matches:
                # Ищем JSON объекты, содержащие "liveChat"
                if 'liveChat' in script_content or 'continuation' in script_content:
                    json_matches = re.findall(r'\{[^{}]*"liveChat"[^{}]*\}', script_content)
                    for json_str in json_matches:
                        try:
                            data = json.loads(json_str)
                            if data:
                                return data
                        except:
                            continue
                
            return None
        except Exception as e:
            print(f"❌ Ошибка при получении начальных данных: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _extract_continuation_token(self, initial_data: Dict) -> Optional[str]:
        """
        Извлекает continuation token для чата из начальных данных
        
        Args:
            initial_data: Начальные данные страницы
            
        Returns:
            Continuation token или None
        """
        def find_token_recursive(obj, depth=0, max_depth=10):
            """
            Рекурсивно ищет continuation token в структуре данных
            
            Args:
                obj: Объект для поиска
                depth: Текущая глубина рекурсии
                max_depth: Максимальная глубина поиска
                
            Returns:
                Найденный token или None
            """
            if depth > max_depth:
                return None
            
            if isinstance(obj, dict):
                # Проверяем ключи, связанные с continuation
                for key in ['continuation', 'reloadContinuationData', 'timedContinuationData', 
                           'invalidationContinuationData', 'liveChatContinuation']:
                    if key in obj:
                        value = obj[key]
                        if isinstance(value, str) and len(value) > 50:  # Token обычно длинный
                            return value
                        elif isinstance(value, dict) and 'continuation' in value:
                            token = value['continuation']
                            if isinstance(token, str) and len(token) > 50:
                                return token
                
                # Ищем liveChatRenderer
                if 'liveChatRenderer' in obj:
                    live_chat = obj['liveChatRenderer']
                    continuations = live_chat.get('continuations', [])
                    if continuations:
                        for cont in continuations:
                            for cont_type in ['reloadContinuationData', 'timedContinuationData', 
                                            'invalidationContinuationData']:
                                if cont_type in cont:
                                    token = cont[cont_type].get('continuation')
                                    if token and len(token) > 50:
                                        return token
                
                # Рекурсивно ищем в значениях словаря
                for value in obj.values():
                    result = find_token_recursive(value, depth + 1, max_depth)
                    if result:
                        return result
                        
            elif isinstance(obj, list):
                # Рекурсивно ищем в элементах списка
                for item in obj:
                    result = find_token_recursive(item, depth + 1, max_depth)
                    if result:
                        return result
            
            return None
        
        try:
            # Проверяем, есть ли playerResponse (альтернативный формат)
            if 'playerResponse' in initial_data:
                player_data = initial_data['playerResponse']
                # Ищем в playerResponse
                token = find_token_recursive(player_data)
                if token:
                    return token
            
            # Стандартные пути через contents
            contents = initial_data.get('contents', {})
            two_column_watch = contents.get('twoColumnWatchNextResults', {})
            results = two_column_watch.get('results', {})
            results_content = results.get('results', {})
            contents_list = results_content.get('contents', [])
            
            for content in contents_list:
                live_chat = content.get('liveChatRenderer', {})
                if live_chat:
                    continuations = live_chat.get('continuations', [])
                    if continuations:
                        for cont in continuations:
                            for cont_type in ['reloadContinuationData', 'timedContinuationData', 
                                            'invalidationContinuationData']:
                                if cont_type in cont:
                                    token = cont[cont_type].get('continuation')
                                    if token:
                                        return token
            
            # Вариант 2: через secondaryResults
            secondary = results_content.get('secondaryResults', {})
            secondary_results = secondary.get('secondaryResults', {})
            secondary_results_list = secondary_results.get('results', [])
            
            for result in secondary_results_list:
                live_chat = result.get('liveChatRenderer', {})
                if live_chat:
                    continuations = live_chat.get('continuations', [])
                    if continuations:
                        for cont in continuations:
                            for cont_type in ['reloadContinuationData', 'timedContinuationData', 
                                            'invalidationContinuationData']:
                                if cont_type in cont:
                                    token = cont[cont_type].get('continuation')
                                    if token:
                                        return token
            
            # Вариант 3: рекурсивный поиск по всей структуре
            print("🔍 Выполняется глубокий поиск continuation token...")
            token = find_token_recursive(initial_data)
            if token:
                return token
            
            # Вариант 4: пробуем получить через отдельный запрос к live_chat
            print("🔍 Пробуем альтернативный способ получения token...")
            # Можно попробовать получить через эндпоинт видео информации
            return None
        except Exception as e:
            print(f"⚠️ Ошибка при извлечении continuation token: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _fetch_chat_messages(self, continuation_token: str) -> tuple[Optional[List[Dict]], Optional[str]]:
        """
        Получает сообщения чата используя continuation token
        
        Args:
            continuation_token: Токен для продолжения получения сообщений
            
        Returns:
            Кортеж (список сообщений, новый continuation token)
        """
        try:
            # Используем внутренний эндпоинт YouTube для получения чата
            url = "https://www.youtube.com/youtubei/v1/live_chat/get_live_chat"
            
            payload = {
                "context": {
                    "client": {
                        "clientName": "WEB",
                        "clientVersion": "2.20231219.00.00",
                        "hl": "ru",
                        "gl": "RU"
                    }
                },
                "continuation": continuation_token
            }
            
            response = self.Session.post(
                url,
                json=payload,
                headers={
                    'Content-Type': 'application/json',
                }
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Извлекаем сообщения
            actions = data.get('continuationContents', {}).get('liveChatContinuation', {}).get('actions', [])
            messages = []
            
            for action in actions:
                if 'addChatItemAction' in action:
                    item = action['addChatItemAction'].get('item', {})
                    if 'liveChatTextMessageRenderer' in item:
                        renderer = item['liveChatTextMessageRenderer']
                        author = renderer.get('authorName', {}).get('simpleText', 'Неизвестно')
                        message_text = ''
                        
                        # Извлекаем текст сообщения (может быть с эмодзи и форматированием)
                        runs = renderer.get('message', {}).get('runs', [])
                        for run in runs:
                            if 'text' in run:
                                message_text += run['text']
                        
                        timestamp = renderer.get('timestampUsec', '0')
                        
                        messages.append({
                            'author': author,
                            'message': message_text,
                            'timestamp': timestamp
                        })
            
            # Получаем новый continuation token
            continuations = data.get('continuationContents', {}).get('liveChatContinuation', {}).get('continuations', [])
            new_token = None
            if continuations:
                new_token = continuations[0].get('timedContinuationData', {}).get('continuation')
                if not new_token:
                    new_token = continuations[0].get('invalidationContinuationData', {}).get('continuation')
            
            return messages, new_token
            
        except Exception as e:
            print(f"❌ Ошибка при получении сообщений: {e}")
            return None, None
    
    def setTimeout(self, callback: Callable, delay: float) -> threading.Timer:
        """
        Аналог setTimeout из JavaScript - выполняет функцию через указанное время
        
        Args:
            callback: Функция для выполнения
            delay: Задержка в секундах
            
        Returns:
            Объект Timer, который можно отменить через cancel()
            
        Example:
            timer = parser.setTimeout(lambda: print("Привет!"), 2.5)
            # timer.cancel()  # Отменить выполнение
        """
        def wrapper():
            try:
                callback()
            except Exception as e:
                print(f"⚠️ Ошибка в setTimeout callback: {e}")
            finally:
                # Удаляем таймер из списка активных
                with self._loopLock:
                    if timer in self._activeTimers:
                        self._activeTimers.remove(timer)
        
        timer = threading.Timer(delay, wrapper)
        timer.daemon = True  # Поток завершится вместе с основным
        
        with self._loopLock:
            self._activeTimers.append(timer)
        
        timer.start()
        return timer
    
    def _fetch_loop(self):
        """
        Основной цикл получения сообщений (выполняется асинхронно)
        """
        if not self.IsRunning:
            return
        
        if not self.ContinuationToken:
            print("⚠️ Continuation token отсутствует. Остановка парсера.")
            self.IsRunning = False
            return
        
        messages, new_token = self._fetch_chat_messages(self.ContinuationToken)
        
        if messages:
            for raw_msg in messages:
                # Создаем структурированный объект сообщения
                chat_message = self._create_message_object(raw_msg)
                
                # Пропускаем исторические сообщения (отправленные до запуска парсера)
                if self._startTime is not None:
                    message_time_seconds = chat_message.Timestamp // 1000000  # Конвертируем из микросекунд в секунды
                    if message_time_seconds < self._startTime:
                        continue  # Пропускаем историческое сообщение
                
                # Уведомляем всех подписчиков только о новых сообщениях
                if self._subscribers:
                    self._notify_subscribers(chat_message)
                else:
                    # Если нет подписчиков, выводим в консоль (для обратной совместимости)
                    print(str(chat_message))
        
        if new_token:
            self.ContinuationToken = new_token
            # Планируем следующую итерацию через 2 секунды
            self.setTimeout(self._fetch_loop, 2.0)
        else:
            print("⚠️ Новый continuation token не получен. Повторная попытка через 5 секунд...")
            # Планируем повторную попытку через 5 секунд
            self.setTimeout(self._fetch_loop, 5.0)
    
    def start(self):
        """
        Запускает парсинг чата
        """
        print(f"🚀 Запуск парсера чата для видео: {self.VideoId}")
        print(f"📺 URL: {self.VideoUrl}\n")
        
        # Получаем начальные данные
        print("🔍 Получение начальных данных...")
        initial_data = self._get_initial_data()
        
        if not initial_data:
            print("❌ Не удалось получить начальные данные")
            return
        
        # Извлекаем continuation token
        print("🔑 Извлечение continuation token...")
        self.ContinuationToken = self._extract_continuation_token(initial_data)
        
        if not self.ContinuationToken:
            print("❌ Не удалось найти continuation token. Возможно, стрим не активен или чат недоступен.")
            return
        
        print("✅ Парсер запущен! Ожидание сообщений...\n")
        self.IsRunning = True
        self._stopEvent.clear()
        self._startTime = int(time.time())  # Запоминаем время запуска для фильтрации истории
        
        # Запускаем первый цикл сразу (без задержки)
        self._fetch_loop()
        
        # Ожидаем остановки (неблокирующее ожидание)
        self._wait_for_stop()
    
    def on(self, callback: Callable[[ChatMessage], None]) -> None:
        """
        Подписывается на новые сообщения из чата
        
        Args:
            callback: Функция-колбэк, которая будет вызываться при получении нового сообщения.
                     Принимает один аргумент типа ChatMessage
                     
        Example:
            def on_new_message(message: ChatMessage):
                print(f"Новое сообщение: {message}")
            
            parser.on(on_new_message)
        """
        if not callable(callback):
            raise TypeError("callback должен быть вызываемым объектом (функцией)")
        self._subscribers.add(callback)
        print(f"✅ Добавлена подписка на новые сообщения. Всего подписок: {len(self._subscribers)}")
    
    def off(self, callback: Callable[[ChatMessage], None]) -> None:
        """
        Отписывается от получения новых сообщений
        
        Args:
            callback: Функция-колбэк, от которой нужно отписаться
        """
        if callback in self._subscribers:
            self._subscribers.discard(callback)
            print(f"✅ Подписка удалена. Осталось подписок: {len(self._subscribers)}")
        else:
            print("⚠️ Указанная подписка не найдена")
    
    def clear(self) -> None:
        """
        Удаляет все подписки на новые сообщения
        """
        count = len(self._subscribers)
        self._subscribers.clear()
        print(f"✅ Все подписки удалены (было: {count})")
    
    def _notify_subscribers(self, message: ChatMessage) -> None:
        """
        Уведомляет всех подписчиков о новом сообщении
        
        Args:
            message: Объект сообщения для отправки подписчикам
        """
        for callback in self._subscribers.copy():  # Используем копию, чтобы избежать изменений во время итерации
            try:
                callback(message)
            except Exception as e:
                print(f"⚠️ Ошибка в подписке при обработке сообщения: {e}")
    
    def _create_message_object(self, raw_message: Dict) -> ChatMessage:
        """
        Создает объект ChatMessage из сырых данных
        
        Args:
            raw_message: Словарь с данными сообщения из API
            
        Returns:
            Объект ChatMessage
        """
        timestamp = int(raw_message.get('timestamp', '0'))
        timestamp_seconds = timestamp // 1000000 if timestamp > 0 else int(time.time())
        timestamp_formatted = time.strftime('%H:%M:%S', time.gmtime(timestamp_seconds))
        
        # Генерируем уникальный ID сообщения, если его нет
        message_id = raw_message.get('message_id') or f"{self.VideoId}_{timestamp}_{self._messageCounter}"
        self._messageCounter += 1
        
        return ChatMessage(
            Author=raw_message.get('author', 'Неизвестно'),
            Message=raw_message.get('message', ''),
            Timestamp=timestamp,
            TimestampFormatted=timestamp_formatted,
            VideoId=self.VideoId,
            MessageId=message_id
        )
    
    def _wait_for_stop(self):
        """
        Ожидает остановки парсера (неблокирующее ожидание через Event)
        """
        if not self.IsRunning:
            return
        
        # Ждем сигнала остановки (с таймаутом для периодической проверки)
        while not self._stopEvent.wait(timeout=0.1):
            if not self.IsRunning:
                break
    
    def stop(self):
        """
        Останавливает парсинг чата и отменяет все активные таймеры
        """
        self.IsRunning = False
        
        # Отменяем все активные таймеры
        with self._loopLock:
            for timer in self._activeTimers:
                timer.cancel()
            self._activeTimers.clear()
        
        # Сигнализируем о остановке
        self._stopEvent.set()
        
        print("\n🛑 Парсер остановлен")
