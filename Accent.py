"""
Минимальный модульный генератор SSML для LM Studio.
Совместим с Silero TTS (поддерживает только <speak>, <prosody>, <break>).
При недоступности LM Studio функционал блокируется до перезапуска приложения.
"""

import requests
import re
import json
from typing import Optional, Tuple, List, Dict
from html.parser import HTMLParser

class SSMLValidator(HTMLParser):
    """Парсер для валидации и исправления SSML с учетом ограничений Silero."""
    
    # Теги, поддерживаемые Silero TTS
    SILERO_SUPPORTED_TAGS = {'speak', 'prosody', 'break'}
    
    def __init__(self):
        super().__init__()
        self.tags_stack: List[Tuple[str, Dict[str, str]]] = []
        self.fixed_parts: List[str] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []
        
    def fix_ssml(self, ssml_text: str, for_silero: bool = True) -> Tuple[str, List[str], List[str]]:
        """Исправляет SSML, адаптируя для Silero если нужно."""
        self.reset()
        self.tags_stack = []
        self.fixed_parts = []
        self.errors = []
        self.warnings = []
        
        # Предварительная обработка
        ssml_text = self._preprocess_ssml(ssml_text)
        
        try:
            self.feed(ssml_text)
        except Exception as e:
            self.errors.append(f"Ошибка парсинга: {e}")
        
        # Закрываем незакрытые теги
        self._close_unclosed_tags()
        
        # Сборка результата
        result = ''.join(self.fixed_parts)
        
        # Постобработка для Silero
        if for_silero:
            result = self._adapt_for_silero(result)
        
        result = self._postprocess_ssml(result)
        
        return result, self.errors, self.warnings
    
    def _preprocess_ssml(self, ssml: str) -> str:
        """Предварительная обработка SSML."""
        # Удаляем очевидно лишние символы
        ssml = re.sub(r'[)>]+$', '>', ssml)
        
        # Исправляем распространенные ошибки
        corrections = {
            r'<spea(\s|>)': '<speak ',
            r'</spea(\s|>)': '</speak>',
            r'<prosod(\s|>)': '<prosody ',
            r'</prosod(\s|>)': '</prosody>',
            r'<emphasi(\s|>)': '<prosody rate="fast" ',  # Заменяем на prosody
            r'</emphasi(\s|>)': '</prosody>',
            r'<emphasis': '<prosody rate="fast" ',  # Заменяем на prosody
            r'</emphasis>': '</prosody>',
        }
        
        for pattern, replacement in corrections.items():
            ssml = re.sub(pattern, replacement, ssml)
        
        # Исправляем атрибуты
        ssml = re.sub(r'(\w+)=(["\'])([^"\']*)=None\2', r'\1="\3"', ssml)
        ssml = re.sub(r'(\w+)=(["\'])\s*([^"\']*)\s*\2', r'\1="\3"', ssml)
        
        return ssml
    
    def handle_starttag(self, tag, attrs):
        """Обработка открывающего тега."""
        tag = tag.lower()
        
        # Проверяем поддержку тега в Silero
        if tag not in self.SILERO_SUPPORTED_TAGS:
            self.warnings.append(f"Тег <{tag}> не поддерживается Silero. Заменяю на <prosody>.")
            tag = 'prosody'  # Заменяем на prosody
        
        # Нормализуем атрибуты
        normalized_attrs = self._normalize_attributes(tag, attrs)
        
        # Формируем тег
        attrs_str = ''
        if normalized_attrs:
            attrs_parts = [f'{k}="{v}"' for k, v in normalized_attrs.items()]
            attrs_str = ' ' + ' '.join(attrs_parts)
        
        if tag == 'break':
            self.fixed_parts.append(f'<{tag}{attrs_str}/>')
        else:
            self.tags_stack.append((tag, normalized_attrs))
            self.fixed_parts.append(f'<{tag}{attrs_str}>')
    
    def handle_endtag(self, tag):
        """Обработка закрывающего тега."""
        tag = tag.lower()
        
        if tag == 'break':
            return  # break не имеет закрывающего тега
        
        # Для совместимости с Silero
        if tag not in self.SILERO_SUPPORTED_TAGS:
            tag = 'prosody'
        
        if self.tags_stack and self.tags_stack[-1][0] == tag:
            self.tags_stack.pop()
            self.fixed_parts.append(f'</{tag}>')
        else:
            self.errors.append(f"Непарный закрывающий тег </{tag}>")
            self.fixed_parts.append(f'</{tag}>')
    
    def handle_data(self, data):
        """Обработка текстовых данных."""
        data = re.sub(r'\s+', ' ', data).strip()
        if data:
            self.fixed_parts.append(data)
    
    def _normalize_attributes(self, tag: str, attrs: List[Tuple[str, str]]) -> Dict[str, str]:
        """Нормализует атрибуты для Silero."""
        result = {}
        
        for attr, value in attrs:
            attr = attr.lower()
            value = value.strip()
            
            # Удаляем мусор
            if value.endswith('=None'):
                value = value[:-5]
            
            # Нормализуем значения
            if attr == 'time' and tag == 'break':
                match = re.search(r'(\d+)', value)
                if match:
                    value = f"{match.group(1)}ms"
                elif not value.endswith('ms'):
                    value = f"{value}ms"
            elif attr == 'rate' and tag == 'prosody':
                if value not in ['slow', 'medium', 'fast', 'x-slow', 'x-fast']:
                    value = 'medium'
            elif attr == 'level':  # Преобразуем level в rate для prosody
                if value == 'strong':
                    result['rate'] = 'fast'
                elif value == 'reduced':
                    result['rate'] = 'slow'
                else:
                    result['rate'] = 'medium'
                continue
            
            result[attr] = value
        
        return result
    
    def _close_unclosed_tags(self):
        """Закрывает все незакрытые теги."""
        while self.tags_stack:
            tag, _ = self.tags_stack.pop()
            self.fixed_parts.append(f'</{tag}>')
            self.errors.append(f"Добавлен недостающий тег </{tag}>")
    
    def _adapt_for_silero(self, ssml: str) -> str:
        """Адаптирует SSML для Silero TTS."""
        # Удаляем неподдерживаемые теги и атрибуты
        ssml = re.sub(r'<(/?)emphasis\b[^>]*>', r'<\1prosody>', ssml)
        
        # Удаляем лишние атрибуты (Silero поддерживает только rate для prosody)
        ssml = re.sub(r'<prosody\b([^>]*)>', 
                     lambda m: self._clean_prosody_attrs(m.group(1)), ssml)
        
        # Убираем лишние вложенности
        ssml = re.sub(r'<prosody[^>]*>\s*</prosody>', '', ssml)
        
        return ssml
    
    def _clean_prosody_attrs(self, attrs_str: str) -> str:
        """Очищает атрибуты тега prosody для Silero."""
        if not attrs_str.strip():
            return '<prosody>'
        
        # Ищем допустимые атрибуты для Silero
        allowed_attrs = {'rate': None, 'pitch': None, 'volume': None}
        found_attrs = {}
        
        # Извлекаем пары атрибут=значение
        attr_pattern = r'(\w+)\s*=\s*["\']([^"\']*)["\']'
        for match in re.finditer(attr_pattern, attrs_str):
            attr, value = match.groups()
            if attr in allowed_attrs:
                found_attrs[attr] = value
        
        # Собираем обратно
        if found_attrs:
            attrs = ' '.join([f'{k}="{v}"' for k, v in found_attrs.items()])
            return f'<prosody {attrs}>'
        else:
            return '<prosody>'
    
    def _postprocess_ssml(self, ssml: str) -> str:
        """Постобработка SSML."""
        # Гарантируем теги speak
        if not re.search(r'<speak[^>]*>', ssml, re.IGNORECASE):
            ssml = f'<speak>{ssml}'
        if not re.search(r'</speak>', ssml, re.IGNORECASE):
            ssml = f'{ssml}</speak>'
        
        # Убираем лишние пробелы
        ssml = re.sub(r'\s+', ' ', ssml)
        ssml = re.sub(r'>\s+<', '><', ssml)
        
        return ssml.strip()


class SSMLGenerator:
    """
    Генератор SSML разметки для русского текста.
    Автоматически адаптирует SSML для Silero TTS.
    """
    
    def __init__(self, base_url: str = "http://localhost:1234/v1"):
        self.base_url = base_url
        self._initialized = False
        self._available = False
        self._validator = SSMLValidator()
        
    def _ensure_initialized(self) -> None:
        """Однократная инициализация при первом использовании."""
        if not self._initialized:
            self._initialized = True
            self._available = self._check_lm_studio_available()
            
            if not self._available:
                self._print_warning()
    
    def _check_lm_studio_available(self) -> bool:
        """Проверка доступности LM Studio сервера."""
        try:
            response = requests.get(f"{self.base_url}/models", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def _print_warning(self) -> None:
        """Вывод предупреждения о недоступности LM Studio."""
        print("\n" + "="*60)
        print("⚠️  SSML ГЕНЕРАТОР: LM Studio не обнаружен")
        print("="*60)
        print("Функция text_to_ssml() будет возвращать None.")
        print("")
        print("Для активации генерации SSML:")
        print("1. Установите LM Studio: https://lmstudio.ai/")
        print("2. Загрузите модель (рекомендуется: Qwen2.5-Coder-1.5B-Instruct-GGUF)")
        print("3. Запустите Local Server во вкладке 'Local Server'")
        print("4. Перезапустите приложение")
        print("="*60 + "\n")
    
    def _generate_with_lm_studio(self, text: str, style: str = "neutral") -> Optional[str]:
        """Генерация SSML через LM Studio API с учетом ограничений Silero."""
        # Промпт с учетом ограничений Silero
        system_prompt = """Ты преобразуешь русский текст в SSML разметку для синтезатора речи Silero.

ВАЖНО: Silero поддерживает ТОЛЬКО эти теги:
- <speak>...</speak>
- <prosody rate="x-slow|slow|medium|fast|x-fast">...</prosody>  (только rate!)
- <break time="100ms|300ms|500ms|1s" strength="x-weak|weak|medium|strong|x-strong"/>

НЕ ИСПОЛЬЗУЙ:
- <emphasis> - НЕ ПОДДЕРЖИВАЕТСЯ!
- Любые другие теги
- Любые другие атрибуты для prosody кроме rate

ПРАВИЛА:
1. Всегда начинай с <speak> и заканчивай </speak>
2. Для акцентов используй <prosody rate="fast">текст</prosody>
3. Расставляй паузы:
   - Запятая: <break time="150ms"/>
   - Точка, !, ?: <break time="300ms"/>
   - Тире: <break time="500ms"/>
4. Числа произноси как цифры
5. Аббревиатуры произноси по буквам

Пример для Silero:
Текст: "Привет, мир! Это важно."
SSML: <speak><prosody rate="medium">Привет<break time="150ms"/> мир!</prosody><break time="300ms"/><prosody rate="fast">Это важно.</prosody></speak>

Теперь преобразуй следующий текст для Silero:"""
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                json={
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Стиль: {style}\nТекст: {text}"}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500,
                    "stop": ["</speak>", "\n\n", "```"],
                    "stream": False
                },
                timeout=30
            )
            
            if response.status_code != 200:
                return None
            
            result = response.json()
            ssml = result["choices"][0]["message"]["content"].strip()
            
            return self._clean_and_fix_ssml(ssml)
            
        except:
            return None
    
    def _clean_and_fix_ssml(self, ssml: str) -> str:
        """Очистка и адаптация SSML для Silero."""
        if not ssml:
            return ""
        
        # Убираем markdown блоки
        ssml = re.sub(r'```(?:xml|ssml)?\n?', '', ssml)
        ssml = re.sub(r'```', '', ssml)
        
        # Исправляем и адаптируем для Silero
        fixed_ssml, errors, warnings = self._validator.fix_ssml(ssml, for_silero=True)
        
        # Логирование проблем (опционально)
        if errors or warnings:
            issues = []
            if errors:
                issues.append(f"Ошибки: {len(errors)}")
            if warnings:
                issues.append(f"Предупреждения: {len(warnings)}")
            print(f"[SSML Исправления]: {', '.join(issues)}")
        
        return fixed_ssml
    
    def _simple_fallback(self, text: str) -> str:
        """Простая SSML разметка для Silero без использования LM Studio."""
        if not text:
            return '<speak></speak>'
        
        # Базовая расстановка пауз для Silero
        result = text
        
        # Простые замены с проверкой на существующие теги
        if '<' not in result and '>' not in result:
            # Добавляем паузы на знаках препинания
            result = re.sub(r'([.!?])\s+', r'\1<break time="300ms"/> ', result)
            result = re.sub(r',\s+', r'<break time="150ms"/> ', result)
            result = re.sub(r';\s+', r'<break time="200ms"/> ', result)
            result = re.sub(r':\s+', r'<break time="250ms"/> ', result)
            result = re.sub(r'—\s+', r'<break time="400ms"/> ', result)
        
        # Обертка в поддерживаемые теги Silero
        return f'<speak><prosody rate="medium">{result}</prosody></speak>'
    
    def text_to_ssml(self, 
                     text: str, 
                     style: str = "neutral", 
                     use_fallback: bool = False) -> Optional[str]:
        """
        Преобразование текста в SSML разметку для Silero TTS.
        
        Args:
            text: Русский текст для преобразования
            style: Стиль речи (neutral, cheerful, serious)
            use_fallback: Использовать простую SSML разметку если LM Studio недоступен
        
        Returns:
            SSML разметка совместимая с Silero или None
        """
        self._ensure_initialized()
        
        # Если LM Studio доступен - пытаемся сгенерировать
        if self._available:
            ssml = self._generate_with_lm_studio(text, style)
            if ssml:
                return ssml
        
        # Fallback или None
        if use_fallback:
            return self._simple_fallback(text)
        
        return None
    
    def validate_for_silero(self, ssml: str) -> Tuple[str, List[str], List[str]]:
        """
        Валидация и адаптация SSML для Silero TTS.
        
        Args:
            ssml: SSML разметка для проверки
        
        Returns:
            Tuple[исправленный_ssml, ошибки, предупреждения]
        """
        return self._validator.fix_ssml(ssml, for_silero=True)
    
    @property
    def is_available(self) -> bool:
        """Проверка доступности генератора SSML."""
        self._ensure_initialized()
        return self._available


# Утилитарная функция для быстрого использования
def text_to_ssml(text: str, style: str = "neutral", use_fallback: bool = False) -> Optional[str]:
    """
    Быстрая функция для преобразования текста в SSML для Silero.
    
    Args:
        text: Русский текст для преобразования
        style: Стиль речи
        use_fallback: Использовать простую SSML разметку если LM Studio недоступен
    
    Returns:
        SSML разметка совместимая с Silero или None
    """
    generator = SSMLGenerator()
    return generator.text_to_ssml(text, style, use_fallback)


# Альтернативная функция с гарантированным результатом
def ensure_ssml(text: str, style: str = "neutral") -> str:
    """
    Гарантированное получение SSML для Silero.
    Всегда возвращает валидный SSML (либо от LM Studio, либо fallback).
    
    Args:
        text: Русский текст для преобразования
        style: Стиль речи
    
    Returns:
        Гарантированно валидный SSML для Silero
    """
    generator = SSMLGenerator()
    ssml = generator.text_to_ssml(text, style, use_fallback=False)
    
    # Если нет SSML от LM Studio, используем fallback
    if not ssml:
        ssml = generator._simple_fallback(text)
    
    # Дополнительная валидация
    validated_ssml, errors, warnings = generator.validate_for_silero(ssml)
    
    # Логирование проблем (можно закомментировать)
    if errors or warnings:
        print(f"[SSML Валидация]: Исправлено {len(errors)} ошибок, {len(warnings)} предупреждений")
    
    return validated_ssml