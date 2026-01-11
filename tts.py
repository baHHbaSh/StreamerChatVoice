import time, pyttsx3, sounddevice as sd
import datetime, time
from threading import Thread
import traceback
import re

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
	def __init__(self):
		self.async_mode = True
		self.model = "silero"#win
	def ospeak(self, text, print_audio = True):
		text = numbers_to_words(text).replace("+", " плюс ").replace("%", " проц ").replace('*', " Звёздочка ").replace("  ", ' ')
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
	def nar_speak(self, text: str, print_audio=True):
		global modelTTS, speaker, sample_rate, put_accent, put_yo
		try:
			audio = modelTTS.apply_tts(text=text+"...   ",
									speaker=speaker,
									sample_rate=sample_rate,
									put_accent=put_accent,
									put_yo=put_yo)
			if print_audio:
				print(text)
			sd.play(audio, sample_rate * 1.05)
			time.sleep((len(audio) / sample_rate) + 0.5)
			sd.stop()
		except:print(traceback.format_exc())
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