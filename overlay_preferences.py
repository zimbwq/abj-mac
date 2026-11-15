"""Validated, non-secret appearance preferences and portable layout math."""
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

MODIFIERS = (1 << 17) | (1 << 18) | (1 << 19) | (1 << 20)
TRIGGERS = {'triple': 'Тройной клик', 'keyboard': 'Клавиша / сочетание', 'both': 'Оба способа'}
POSITIONS = {'bottom-right': 'Справа внизу', 'bottom-left': 'Слева внизу',
             'top-right': 'Справа вверху', 'top-left': 'Слева вверху',
             'bottom-center': 'По центру внизу', 'top-center': 'По центру вверху',
             'center': 'По центру'}


@dataclass(frozen=True)
class OverlayPreferences:
    duration: int = 25  # 0 means until dismissed
    position: str = 'bottom-right'
    font_size: int = 16
    color: str = '#898989'
    opacity: float = 1.0
    width: int = 440
    margin: int = 24
    key_code: int = 53
    key_modifiers: int = 0
    key_label: str = 'Esc'
    trigger_mode: str = 'triple'
    trigger_code: int = 49
    trigger_modifiers: int = (1 << 17) | (1 << 20)
    trigger_label: str = '⇧⌘Space'

    def __post_init__(self):
        for name, low, high in [('duration', 0, 300), ('font_size', 10, 72),
                                ('width', 180, 1200), ('margin', 0, 200), ('key_code', 0, 127),
                                ('trigger_code', 0, 127)]:
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError('Некорректная настройка: ' + name)
        if self.position not in POSITIONS:
            raise ValueError('Некорректное положение.')
        if (not isinstance(self.color, str) or len(self.color) != 7 or self.color[0] != '#'
                or any(c not in '0123456789abcdefABCDEF' for c in self.color[1:])):
            raise ValueError('Некорректный цвет.')
        if type(self.opacity) not in (int, float) or not math.isfinite(self.opacity) or not 0.15 <= self.opacity <= 1:
            raise ValueError('Некорректная прозрачность.')
        if type(self.key_modifiers) is not int or self.key_modifiers & ~MODIFIERS:
            raise ValueError('Некорректное сочетание клавиш.')
        if not isinstance(self.key_label, str) or not 1 <= len(self.key_label) <= 40 or not self.key_label.isprintable():
            raise ValueError('Некорректное название клавиши.')
        if self.trigger_mode not in TRIGGERS:
            raise ValueError('Некорректный способ запуска.')
        if type(self.trigger_modifiers) is not int or self.trigger_modifiers & ~MODIFIERS:
            raise ValueError('Некорректный бинд запуска.')
        if not isinstance(self.trigger_label, str) or not 1 <= len(self.trigger_label) <= 40 or not self.trigger_label.isprintable():
            raise ValueError('Некорректное название бинда.')
        if self.trigger_mode != 'triple' and (self.key_code, self.key_modifiers) == (self.trigger_code, self.trigger_modifiers):
            raise ValueError('Запуск и скрытие должны использовать разные клавиши.')

    def matches(self, key_code, flags):
        return self.key_code == key_code and self.key_modifiers == flags & MODIFIERS

    def matches_trigger(self, key_code, flags):
        return (self.trigger_mode in ('keyboard', 'both') and self.trigger_code == key_code
                and self.trigger_modifiers == flags & MODIFIERS)

    def uses_mouse(self):
        return self.trigger_mode in ('triple', 'both')


def shortcut_label(key_code, characters, flags):
    special = {53: 'Esc', 36: 'Return', 76: 'Enter', 49: 'Space', 48: 'Tab', 51: 'Delete',
               117: 'Forward Delete', 123: '←', 124: '→', 125: '↓', 126: '↑',
               122: 'F1', 120: 'F2', 99: 'F3', 118: 'F4', 96: 'F5', 97: 'F6',
               98: 'F7', 100: 'F8', 101: 'F9', 109: 'F10', 103: 'F11', 111: 'F12'}
    name = special.get(key_code)
    if name is None:
        name = characters.upper() if characters and characters.isprintable() else f'Key {key_code}'
    prefix = ''.join(symbol for mask, symbol in [(1 << 18, '⌃'), (1 << 19, '⌥'),
                                                (1 << 17, '⇧'), (1 << 20, '⌘')] if flags & mask)
    return (prefix + name)[:40]


def layout_frame(prefs, screen, text_height):
    x, y, sw, sh = screen
    margin = min(prefs.margin, max(0, (min(sw, sh) - 40) / 2))
    width = min(prefs.width, sw - 2 * margin)
    height = min(max(30, text_height), sh - 2 * margin)
    left = x + margin if 'left' in prefs.position else x + sw - margin - width
    if 'center' in prefs.position:
        left = x + (sw - width) / 2
    bottom = y + sh - margin - height if 'top' in prefs.position else y + margin
    if prefs.position == 'center':
        bottom = y + (sh - height) / 2
    return left, bottom, width, height


class PreferenceStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path.home() / 'Library/Application Support/abj/overlay.json'

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            return OverlayPreferences(**data)
        except FileNotFoundError:
            return OverlayPreferences()
        except (OSError, ValueError, TypeError):
            raise RuntimeError('Не удалось прочитать настройки текста. Используются стандартные значения.') from None

    def save(self, prefs):
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             prefix='.overlay-', delete=False) as file:
                temporary = file.name
                json.dump(asdict(prefs), file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        except OSError:
            raise RuntimeError('Не удалось сохранить настройки текста. Проверьте доступ к папке abj.') from None
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
