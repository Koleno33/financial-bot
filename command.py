import re
import datetime
from log import logger

reserved = ["/start", "доход", "удали", "раздел ", "разделы", "валюта ", "валюты"]

regexp = {
    "time":   re.compile(r'^\b\d{1,2}[.:]\d{2}\b$'),
    "number": re.compile(r'^[+]?\d+(?:[.,]\d+)?$'), # float r'^\b[0-9]+\b$'
    "date":   re.compile(r'^\b(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\bпозавчера|\bвчера|\bсегодня|\bзавтра|\bпослезавтра)\b$'),
    "text":   re.compile(r'[\w]'),
}

def get_date(text: str):
    match text:
        case "позавчера":
            return datetime.datetime.now().date() - datetime.timedelta(days=2)
        case "вчера":
            return datetime.datetime.now().date() - datetime.timedelta(days=1)
        case "сегодня":
            return datetime.datetime.now().date()
        case "завтра":
            return datetime.datetime.now().date() + datetime.timedelta(days=1)
        case "послезавтра":
            return datetime.datetime.now().date() + datetime.timedelta(days=2)

    try:
        if text[:2].isdigit():
            limiter = text[2]
        else:
            limiter = text[1]
        if len(text[text.rfind(limiter) + 1:]) == 4:
            year = "Y"
        else:
            year = "y"
        date = datetime.datetime.strptime(text, f'%d{limiter}%m{limiter}%{year}')
        return date.date()
    except Exception as e:
        logger.debug("error parsing date: ", e, text)
        return None

def get_time(text: str):
    try:
        limiter = text[-3]
        time = datetime.datetime.strptime(text, f'%H{limiter}%M')
        return time.time()
    except Exception as e:
        logger.debug("error parsing time: ", e, text)
        return None

def get_matched_type(arg):
    for reg in regexp:
        if regexp[reg].match(arg):
            return reg
    return "unknown"

class Arg:
    def __init__(self, value: str, type: str, orig: str):
        self.value = value
        self.type = type
        self.original_value = orig

class Command:
    def __init__(self, full_command: str):
        command = full_command.lower().split()
        full_command = full_command.split()
        if command[0] in [r.strip() for r in reserved]:
            self.instruction = command[0]
            full_command.remove(full_command[0])
            command.remove(command[0])
        else:
            self.instruction = None
        self.args = list()
        for index, arg in enumerate(command):
            self.args.append(Arg(arg, get_matched_type(arg), full_command[index]))

