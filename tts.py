import time, pyttsx3, sounddevice as sd
import datetime, time
from threading import Thread, Lock, Timer
from queue import Queue
import traceback
import re
from Accent import*

import torch

Speakers = [ "aidar", "baya", "kseniya", "xenia", "random"]

language = 'ru'
model_id = "v5_1_ru"
sample_rate = 48000 # 48000
speaker = Speakers[1] #aidar, baya, kseniya, xenia, eugene, random
name = "large_fast"
put_accent = True
put_yo = True

device = torch.device("cpu") # cpu или cuda

modelTTS, _ = torch.hub.load(repo_or_dir='snakers4/silero-models',
						  model='silero_tts',
						  language=language,
						  speaker=model_id,
						  name = name)
modelTTS.to(device)

Accenter = SSMLGenerator("http://localhost:8786/v1")

def numbers_to_words(text: str) -> str:
    """
    Преобразует цифры в тексте в числительные на русском языке
    
    Args:
        text: Текст с цифрами
        
    Returns:
        Текст с замененными цифрами на числительные
        
    Example:
        "У меня 5 яблок и 123 рубля" -> "У меня пять яблок и сто двадцать три рубля"
    """
    # Словари для преобразования
    ones = {
        '0': 'ноль', '1': 'один', '2': 'два', '3': 'три', '4': 'четыре',
        '5': 'пять', '6': 'шесть', '7': 'семь', '8': 'восемь', '9': 'девять'
    }
    
    teens = {
        '10': 'десять', '11': 'одиннадцать', '12': 'двенадцать', '13': 'тринадцать',
        '14': 'четырнадцать', '15': 'пятнадцать', '16': 'шестнадцать',
        '17': 'семнадцать', '18': 'восемнадцать', '19': 'девятнадцать'
    }
    
    tens = {
        '2': 'двадцать', '3': 'тридцать', '4': 'сорок', '5': 'пятьдесят',
        '6': 'шестьдесят', '7': 'семьдесят', '8': 'восемьдесят', '9': 'девяносто'
    }
    
    hundreds = {
        '1': 'сто', '2': 'двести', '3': 'триста', '4': 'четыреста',
        '5': 'пятьсот', '6': 'шестьсот', '7': 'семьсот', '8': 'восемьсот', '9': 'девятьсот'
    }
    
    def number_to_words(num_str: str) -> str:
        """
        Преобразует число в строку в числительное
        
        Args:
            num_str: Строка с числом
            
        Returns:
            Числительное на русском языке
        """
        num = int(num_str)
        
        # Ноль
        if num == 0:
            return ones['0']
        
        # 1-9
        if num < 10:
            return ones[str(num)]
        
        # 10-19
        if num < 20:
            return teens[str(num)]
        
        # 20-99
        if num < 100:
            ten = num // 10
            one = num % 10
            if one == 0:
                return tens[str(ten)]
            return f"{tens[str(ten)]} {ones[str(one)]}"
        
        # 100-999
        if num < 1000:
            hundred = num // 100
            remainder = num % 100
            if remainder == 0:
                return hundreds[str(hundred)]
            return f"{hundreds[str(hundred)]} {number_to_words(str(remainder))}"
        
        # 1000-9999
        if num < 10000:
            thousand = num // 1000
            remainder = num % 1000
            if remainder == 0:
                if thousand == 1:
                    return "одна тысяча"
                elif thousand == 2:
                    return "две тысячи"
                elif thousand in [3, 4]:
                    return f"{number_to_words(str(thousand))} тысячи"
                else:
                    return f"{number_to_words(str(thousand))} тысяч"
            if thousand == 1:
                return f"одна тысяча {number_to_words(str(remainder))}"
            elif thousand == 2:
                return f"две тысячи {number_to_words(str(remainder))}"
            elif thousand in [3, 4]:
                return f"{number_to_words(str(thousand))} тысячи {number_to_words(str(remainder))}"
            else:
                return f"{number_to_words(str(thousand))} тысяч {number_to_words(str(remainder))}"
        
        # Для больших чисел просто возвращаем как есть (можно расширить)
        return num_str
    
    # Ищем все числа в тексте (целые числа)
    def replace_number(match):
        num_str = match.group(0)
        return number_to_words(num_str)
    
    # Заменяем числа на числительные (ищем последовательности цифр)
    result = re.sub(r'\b\d+\b', replace_number, text)
    
    return result

def transliterate_english(text: str) -> str:
    """
    Транслитерирует английские слова в русские буквы с учетом диграфов
    
    Args:
        text: Текст с возможными английскими словами
        
    Returns:
        Текст с транслитерированными английскими словами
        
    Example:
        "Hello world" -> "Хелло ворлд"
        "Привет hello" -> "Привет хелло"
        "shoot" -> "шут"
        "think" -> "зинк"
    """
    text = text.replace('_', ' ')
    
    # Словарь диграфов (двухбуквенные комбинации) - обрабатываются первыми
    digraphs = {
        'sh': 'ш', 'ch': 'ч', 'th': 'з', 'ph': 'ф', 'zh': 'ж',
        'ts': 'ц', 'ck': 'к', 'ng': 'нг', 'qu': 'кв',
        'Sh': 'Ш', 'Ch': 'Ч', 'Th': 'З', 'Ph': 'Ф', 'Zh': 'Ж',
        'Ts': 'Ц', 'Ck': 'К', 'Ng': 'Нг', 'Qu': 'Кв',
        'SH': 'Ш', 'CH': 'Ч', 'TH': 'З', 'PH': 'Ф', 'ZH': 'Ж',
        'TS': 'Ц', 'CK': 'К', 'NG': 'Нг', 'QU': 'Кв'
    }
    
    # Словарь одиночных букв
    translit_map = {
        'a': 'а', 'b': 'б', 'c': 'к', 'd': 'д', 'e': 'е', 'f': 'ф',
        'g': 'г', 'h': 'х', 'i': 'и', 'j': 'дж', 'k': 'к', 'l': 'л',
        'm': 'м', 'n': 'н', 'o': 'о', 'p': 'п', 'q': 'к', 'r': 'р',
        's': 'с', 't': 'т', 'u': 'у', 'v': 'в', 'w': 'в', 'x': 'кс',
        'y': 'й', 'z': 'з',
        'A': 'А', 'B': 'Б', 'C': 'К', 'D': 'Д', 'E': 'Е', 'F': 'Ф',
        'G': 'Г', 'H': 'Х', 'I': 'И', 'J': 'Дж', 'K': 'К', 'L': 'Л',
        'M': 'М', 'N': 'Н', 'O': 'О', 'P': 'П', 'Q': 'К', 'R': 'Р',
        'S': 'С', 'T': 'Т', 'U': 'У', 'V': 'В', 'W': 'В', 'X': 'Кс',
        'Y': 'Й', 'Z': 'З'
    }
    
    def transliterate_word(match):
        """
        Транслитерирует одно английское слово с учетом диграфов
        """
        word = match.group(0)
        result = ''
        i = 0
        
        while i < len(word):
            # Проверяем диграфы (двухбуквенные комбинации)
            if i < len(word) - 1:
                digraph = word[i:i+2]
                if digraph in digraphs:
                    result += digraphs[digraph]
                    i += 2  # Пропускаем обе буквы
                    continue
            
            # Обрабатываем одиночную букву
            char = word[i]
            if char in translit_map:
                result += translit_map[char]
            else:
                result += char  # Оставляем как есть, если не латинская буква
            i += 1
        
        return result
    
    # Ищем английские слова (последовательности латинских букв) и транслитерируем их
    result = re.sub(r'\b[a-zA-Z]+\b', transliterate_word, text)
    
    return result

def дозапись(x: str, path_to_file):
	pass
	#Thread(target=__Append, args=(x, path_to_file)).run Не думаю что стоит это возвращать в код
def __Append(x:str, path_to_file):
	try:
		with open(path_to_file, "r", encoding="utf-8") as file:
			q = file.read()
		with open(path_to_file, "w", encoding="utf-8") as file:
			file.write(q + f"\n{x}")
	except:
		with open(path_to_file, "w") as file:
			file.write("Start file")
class tts:
	"""
	Класс для синтеза речи с поддержкой асинхронного воспроизведения
	"""
	def __init__(self):
		"""
		Инициализация класса TTS
		"""
		self.async_mode = True
		self.model = "silero"#win
		self._activeTimers: list[Timer] = []  # Список активных таймеров
		self._loopLock = Lock()  # Блокировка для синхронизации доступа к таймерам
		self._isPlaying = False  # Флаг воспроизведения аудио
		self._messageQueue = Queue()  # Очередь сообщений для воспроизведения (потокобезопасна)
		self._processingLock = Lock()  # Блокировка для предотвращения одновременного запуска обработки очереди
	def ospeak(self, text, print_audio = True):
		text = numbers_to_words(text)
		if self.model == "win":
			if self.async_mode:
				Thread(target=self.ospeak_n_a, args=(text, print_audio)).run()
			else:
				self.ospeak_n_a(text, print_audio)
		elif self.model == "silero":
			self.nar_speak(text, print_audio)
	def ospeak_n_a(self, text, print_audio = True):
		try:
			if print_audio:
				print(str(datetime.datetime.now().time())[:8] + " Бот: " + text)
			дозапись("Бот: " + text, "history.txt")
			ttss = pyttsx3.init()
			ttss.setProperty('voice', 'ru')
			ttss.say(text)
			ttss.runAndWait()
		except:
			print("[INFO] Поток tts загружен")
	def setTimeout(self, callback, delay: float) -> Timer:
		"""
		Аналог setTimeout из JavaScript - выполняет функцию через указанное время
		
		Args:
			callback: Функция для выполнения
			delay: Задержка в секундах
			
		Returns:
			Объект Timer, который можно отменить через cancel()
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
		
		timer = Timer(delay, wrapper)
		timer.daemon = True  # Поток завершится вместе с основным
		
		with self._loopLock:
			self._activeTimers.append(timer)
		
		timer.start()
		return timer
	
	def nar_speak(self, text: str, print_audio=True):
		"""
		Добавляет текст в очередь для воспроизведения через синтез речи Silero
		
		Args:
			text: Текст для озвучивания
			print_audio: Выводить ли текст в консоль
		"""
		# Добавляем сообщение в очередь (Queue потокобезопасна)
		self._messageQueue.put((text, print_audio))
		
		# Если сейчас ничего не воспроизводится, запускаем обработку очереди
		# Используем блокировку, чтобы избежать запуска нескольких обработчиков одновременно
		with self._processingLock:
			if not self._isPlaying:
				self._isPlaying = True
				Thread(target=self._process_queue, daemon=True).start()
	
	def _process_queue(self):
		"""
		Обрабатывает очередь сообщений, воспроизводя их последовательно
		"""
		global modelTTS, speaker, sample_rate, put_accent, put_yo
		
		# Продолжаем обработку, пока очередь не пуста
		while True:
			try:
				# Получаем сообщение из очереди
				# Используем get_nowait, чтобы не блокироваться, если очередь пуста
				try:
					text, print_audio = self._messageQueue.get_nowait()
				except Exception:
					# Очередь пуста, завершаем обработку
					break
				
				# Воспроизводим текущее сообщение
				try:
					# Транслитерируем английские слова перед отправкой в TTS
					transliterated_text = transliterate_english(text)

					ssml = None
					if self._messageQueue.qsize() < 3:
						ssml = Accenter.text_to_ssml(text, use_fallback=True, style="cheerful")

					if ssml is None or ssml and ssml.startswith("<speak>"):
						try:
							audio = modelTTS.apply_tts(ssml_text=ssml,
								speaker=speaker,
								sample_rate=sample_rate
							)
							if print_audio:
								print(ssml)
						except:
							print("Exeption:\n")
							print(f"\n{ssml}\n")
							traceback.print_exc()
							# Генерируем аудио
							audio = modelTTS.apply_tts(text=transliterated_text+"...   ",
								speaker=speaker,
								sample_rate=sample_rate,
								put_accent=put_accent,
								put_yo=put_yo
							)
							if print_audio:
								print(text)
					else:
						# Генерируем аудио
						audio = modelTTS.apply_tts(text=transliterated_text+"...   ",
							speaker=speaker,
							sample_rate=sample_rate,
							put_accent=put_accent,
							put_yo=put_yo
						)
						if print_audio:
							print(text)
					
					
					# Воспроизводим аудио
					sd.play(audio, sample_rate * 1.05)
					
					# Вычисляем длительность воспроизведения
					duration = (len(audio) / sample_rate) + 0.1
					
					# Ждем завершения воспроизведения (блокирующее ожидание)
					time.sleep(duration)
					
					# Останавливаем воспроизведение
					sd.stop()
					
				except Exception as e:
					print(f"❌ Ошибка при воспроизведении: {e}")
					print(traceback.format_exc())
				
				# Помечаем задачу как выполненную
				self._messageQueue.task_done()
				
			except Exception as e:
				print(f"❌ Ошибка при обработке очереди: {e}")
				print(traceback.format_exc())
				break
		
		# Когда очередь пуста, сбрасываем флаг воспроизведения
		with self._processingLock:
			self._isPlaying = False
	
	def _stop_audio(self):
		"""
		Останавливает воспроизведение аудио
		"""
		try:
			sd.stop()
			self._isPlaying = False
		except Exception as e:
			print(f"⚠️ Ошибка при остановке аудио: {e}")
	def SaveToFile(self, text):
		ttss = pyttsx3.init()
		ttss.setProperty('voice', 'ru')
		ttss.save_to_file(text, "data.mp3")
		ttss.runAndWait()
		ttss.stop()
		self.ospeak("Выполнено")
if __name__ == "__main__":
	Mtts = tts()
	while 1:
		Mtts.ospeak(input("Введите текст: "))