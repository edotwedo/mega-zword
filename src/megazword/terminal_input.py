"""Keyboard events and buffered VT protocol for the owned Windows console only."""
import ctypes
import os
import re
import time


def _wintypes():
    if os.name != "nt":
        raise OSError("Windows console input is unavailable")
    from ctypes import wintypes
    return wintypes


def key_text(vk, char='', state=0, repeat=1):
    ctrl, alt, shift = bool(state & 0xC), bool(state & 3), bool(state & 0x10)
    mod = 1 + shift + 2 * alt + 4 * ctrl
    if vk == 8:
        text = '\x08' if ctrl else '\x7f'  # Ctrl+H is word erase in these TUIs.
        if alt and not ctrl:
            text = '\x1b' + text
    elif vk == 9 and shift:
        text = '\x1b[Z'
    elif vk in (37, 38, 39, 40, 36, 35):
        final = {37:'D', 38:'A', 39:'C', 40:'B', 36:'H', 35:'F'}[vk]
        text = f'\x1b[1;{mod}{final}' if mod > 1 else f'\x1b[{final}'
    elif vk in (45, 46, 33, 34):
        number = {45:2, 46:3, 33:5, 34:6}[vk]
        text = f'\x1b[{number};{mod}~' if mod > 1 else f'\x1b[{number}~'
    elif 112 <= vk <= 115:
        final = 'PQRS'[vk-112]
        text = f'\x1b[1;{mod}{final}' if mod > 1 else '\x1bO' + final
    elif 116 <= vk <= 123:
        number = [15,17,18,19,20,21,23,24][vk-116]
        text = f'\x1b[{number};{mod}~' if mod > 1 else f'\x1b[{number}~'
    else:
        text = char if char != '\x00' else ''
        if not text and ctrl and vk == 32:
            text = '\x00'
        # AltGr produces printable text with Ctrl+Alt set; it is not an Alt shortcut.
        if text and alt and not ctrl and vk != 27:
            text = '\x1b' + text
    return text * max(1, min(repeat, 256))


class VTStream:
    """Yield complete escape sequences, never prefixes of a reply."""
    def __init__(self):
        self.buffer = ''
        self.since = 0

    def feed(self, text):
        tokens = []
        for char in text:
            if not self.buffer and char != '\x1b':
                tokens.append(char)
                continue
            if not self.buffer:
                self.since = time.monotonic()
            self.buffer += char
            value = self.buffer
            if value == '\x1b':
                continue
            if value.startswith(('\x1b]', '\x1bP', '\x1b_', '\x1b^')):
                complete = value.endswith(('\x07', '\x1b\\'))
            elif value.startswith('\x1b['):
                complete = len(value) >= 3 and '@' <= value[-1] <= '~'
            elif value.startswith('\x1bO'):
                complete = len(value) >= 3
            else:
                complete = True
            if complete:
                tokens.append(value)
                self.buffer = ''
            elif len(value) > 65536:
                self.buffer = ''  # malformed protocol must not become editor input
        return tokens

    def escape(self, now):
        if self.buffer == '\x1b' and now - self.since >= .08:
            self.buffer = ''
            return '\x1b'
        return ''


def protocol_reply(token):
    return (token.startswith(('\x1b]', '\x1bP', '\x1b_', '\x1b^'))
            or bool(re.fullmatch(r'\x1b\[[?>]?[0-9;:]*[ -/]*[Rcnty]', token))
            or bool(re.fullmatch(r'\x1b\[\?[0-9;]*u', token))
            or token in ('\x1b[I', '\x1b[O'))


class InputFilter:
    def __init__(self):
        self.stream = VTStream()
        self.paste = False

    def feed(self, text):
        result = []
        for token in self.stream.feed(text):
            if token == '\x1b[200~':
                self.paste = True
            if self.paste or not protocol_reply(token):
                result.append(token)
            if token == '\x1b[201~':
                self.paste = False
        return result


class OutputFilter:
    """Handle child queries locally, so Windows Terminal never types replies back."""
    def __init__(self, cursor=lambda: (1, 1)):
        self.stream = VTStream()
        self.cursor = cursor
        self.bracketed = False

    def feed(self, text):
        display, replies = [], []
        for token in self.stream.feed(text):
            reply = None
            if token in ('\x1b[c', '\x1b[0c'):
                reply = '\x1b[?1;2c'
            elif token in ('\x1b[>c', '\x1b[>0c'):
                reply = '\x1b[>0;0;0c'
            elif token == '\x1b[5n':
                reply = '\x1b[0n'
            elif token == '\x1b[6n':
                row, col = self.cursor()
                reply = f'\x1b[{row};{col}R'
            elif token == '\x1b[?u':
                reply = '\x1b[?0u'  # enhanced keyboard protocol is not advertised
            elif re.fullmatch(r'\x1b\](10|11|12);\?(?:\x07|\x1b\\)', token):
                code = token[2:4]
                rgb = '0c0c/0c0c/0c0c' if code == '11' else 'cccc/cccc/cccc'
                reply = f'\x1b]{code};rgb:{rgb}\x1b\\'
            elif re.fullmatch(r'\x1b\[\?[0-9]+\$p', token):
                reply = token[:-2] + ';0$y'  # mode not advertised by the relay
            if reply is not None:
                replies.append(reply)
            else:
                if token == '\x1b[?2004h':
                    self.bracketed = True
                elif token == '\x1b[?2004l':
                    self.bracketed = False
                display.append(token)
        return ''.join(display), replies


class ConsoleInput:
    """Raw events from this process's console; no global hooks or synthetic input."""
    def __enter__(self):
        wt = _wintypes()
        class Key(ctypes.Structure):
            _fields_ = [('down', wt.BOOL), ('repeat', wt.WORD), ('vk', wt.WORD),
                        ('scan', wt.WORD), ('char', wt.WCHAR), ('state', wt.DWORD)]
        class Event(ctypes.Union):
            _fields_ = [('key', Key), ('padding', ctypes.c_byte * 16)]
        class Record(ctypes.Structure):
            _fields_ = [('kind', wt.WORD), ('event', Event)]
        self.Record = Record
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.GetStdHandle.argtypes = [wt.DWORD]
        self.api.GetStdHandle.restype = wt.HANDLE
        self.api.GetConsoleMode.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
        self.api.SetConsoleMode.argtypes = [wt.HANDLE, wt.DWORD]
        self.api.GetNumberOfConsoleInputEvents.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
        self.api.ReadConsoleInputW.argtypes = [wt.HANDLE, ctypes.POINTER(Record), wt.DWORD, ctypes.POINTER(wt.DWORD)]
        self.input = self.api.GetStdHandle(wt.DWORD(-10).value)
        self.output = self.api.GetStdHandle(wt.DWORD(-11).value)
        self.input_mode, self.output_mode = wt.DWORD(), wt.DWORD()
        if not self.api.GetConsoleMode(self.input, ctypes.byref(self.input_mode)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not self.api.GetConsoleMode(self.output, ctypes.byref(self.output_mode)):
            raise ctypes.WinError(ctypes.get_last_error())
        mode = (self.input_mode.value & ~(1 | 2 | 4 | 0x40 | 0x200)) | 0x80 | 8
        if not self.api.SetConsoleMode(self.input, mode):
            raise ctypes.WinError(ctypes.get_last_error())
        if not self.api.SetConsoleMode(self.output, self.output_mode.value | 4):
            self.api.SetConsoleMode(self.input, self.input_mode.value)
            raise ctypes.WinError(ctypes.get_last_error())
        self.surrogate = ''
        return self

    def pending(self):
        wt = _wintypes()
        count = wt.DWORD()
        if not self.api.GetNumberOfConsoleInputEvents(self.input, ctypes.byref(count)):
            raise ctypes.WinError(ctypes.get_last_error())
        return count.value

    def read(self):
        wt = _wintypes()
        count = min(self.pending(), 256)
        if not count:
            return ''
        records = (self.Record * count)()
        read = wt.DWORD()
        if not self.api.ReadConsoleInputW(self.input, records, count, ctypes.byref(read)):
            raise ctypes.WinError(ctypes.get_last_error())
        text = []
        for record in records[:read.value]:
            if record.kind != 1 or not record.event.key.down:
                continue
            key = record.event.key
            char = key.char
            if char and 0xD800 <= ord(char) <= 0xDBFF:
                self.surrogate = char
                continue
            if self.surrogate:
                if char and 0xDC00 <= ord(char) <= 0xDFFF:
                    char = (self.surrogate + char).encode('utf-16-le', errors='surrogatepass').decode('utf-16-le')
                self.surrogate = ''
            text.append(key_text(key.vk, char, key.state, key.repeat))
        return ''.join(text)

    def cursor(self):
        wt = _wintypes()
        class Coord(ctypes.Structure):
            _fields_ = [('x', wt.SHORT), ('y', wt.SHORT)]
        class Rect(ctypes.Structure):
            _fields_ = [('left', wt.SHORT), ('top', wt.SHORT), ('right', wt.SHORT), ('bottom', wt.SHORT)]
        class Info(ctypes.Structure):
            _fields_ = [('size', Coord), ('position', Coord), ('attributes', wt.WORD), ('window', Rect), ('maximum', Coord)]
        self.api.GetConsoleScreenBufferInfo.argtypes = [wt.HANDLE, ctypes.POINTER(Info)]
        info = Info()
        if self.api.GetConsoleScreenBufferInfo(self.output, ctypes.byref(info)):
            return max(1, info.position.y - info.window.top + 1), max(1, info.position.x + 1)
        return 1, 1

    def __exit__(self, *exc):
        self.api.SetConsoleMode(self.input, self.input_mode.value)
        self.api.SetConsoleMode(self.output, self.output_mode.value)
