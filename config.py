import telethon
import json

config_struct = set((
    "api_id",
    "api_hash",
    "bot_token",
))

config = None

def read_config():
    global config

    config_filename = 'config.json'
    try:
        open(config_filename, "r")
    except FileNotFoundError:
        open(config_filename, "w")

    with open(config_filename) as f:
        try:
            config = json.load(f)
            if not set(config.keys()).issuperset(config_struct):
                raise Exception()
        except Exception:
            print(f"Ошибка: Файл {config_filename} задан неверно.")
            return False

    return True

if not read_config():
    exit(1)