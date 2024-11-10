import telethon
import datetime
from sqlalchemy import select
from database import Session, engine, User
from config import read_config, config
from log import logger
from command import Command, Arg, reserved, get_date, get_time

bot = telethon.TelegramClient("bot", config["api_id"], config["api_hash"]).start(bot_token=config["bot_token"])


def check_pattern(args: list[Arg] | Arg, pattern: str):
    pattern = pattern.split()
    if type(args) is Arg:
        args = [args]
    if len(args) != len(pattern):
        return False
    for i in range(len(args)):
        if pattern[i] != args[i].type:
            return False
    return True

@bot.on(telethon.events.NewMessage(pattern='/start'))
async def handle_start_command(event):
    with Session(engine) as session:
        check_user = session.scalar(select(User).where(User.id == event.chat_id))
        if not check_user:
            new_user = User(id=event.chat_id, date=datetime.datetime.now())
            session.add(new_user)
            session.commit()
    await bot.send_message(event.chat_id, "Привет! Управление ботом происходит через следующие предложения, которые"
                                          " могут быть написаны как с заглавными, так и со строчными буквами:\n\n"
                                          "`(<дата>) (<время>) <сумма> <валюта> <раздел>` - добавить запись (по умолчанию текущие дата и время)\n"
                                          "`Доход (<раздел>)` - узнать сведения о доходах за этот месяц\n"
                                          "`Доход <дата> (<раздел>)` - узнать сведения о доходах за конкретный день\n"
                                          "`Доход <месяц> (<раздел>)` - узнать доход за конкретный месяц\n"
                                          "`Доход <месяц> <год> (<раздел>)` - узнать доход за конкретный месяц конкретного года\n"
                                          "`Удали` - удалить последнюю запись\n"
                                          "`Удали <дата> <время> <сумма> <валюта> <раздел>` - удалить конкретную запись\n"
                                          "`Удали <дата> (<раздел>)` - удалить записи за день\n"
                                          "`Удали <дата> <дата> (<раздел>)` - удалить записи за диапазон дней включительно\n"
                                          "`Разделы` - показать текущие разделы\n"
                                          "`Раздел <название раздела> <синоним>` - создание синонимов для разделов\n"
                                          "`Валюты` - показать текущие валюты\n"
                                          "`Валюта <название валюты> <синоним>` - создание синонимов для валют\n"
                                          "\n"
                                          "То, что находится в скобках () может упускаться. Например: `доход`"
                                          "- доход за все разделы, а `доход первая` - доход в конкретном разделе за этот месяц.\n\n"
                                          "`<дата>` - не только дата в формате ДД.ММ.ГГ, но и слова: позавчера, вчера, сегодня,"
                                          " завтра, послезавтра\n"
                                          "`<время>` - время в формате ЧЧ.ММ (например, 17.46).\n"
                                          "Вместо точек у даты и времени могут быть любые разделители кроме пробелов.",
                           parse_mode='md')

@bot.on(telethon.events.NewMessage(pattern='(?i)доход+'))
async def handle_income_command(event):
    await bot.send_message(event.chat_id, 'Доход')

@bot.on(telethon.events.NewMessage(pattern='(?i)удали+'))
async def handle_delete_command(event):
    await bot.send_message(event.chat_id, 'Удаление')

@bot.on(telethon.events.NewMessage(pattern='(?i)раздел +'))
async def handle_section_command(event):
    await bot.send_message(event.chat_id, 'Раздел')

@bot.on(telethon.events.NewMessage(pattern='(?i)^разделы$'))
async def handle_sections_command(event):
    await bot.send_message(event.chat_id, 'Разделы')

@bot.on(telethon.events.NewMessage(pattern='(?i)валюта +'))
async def handle_currency_command(event):
    await bot.send_message(event.chat_id, 'Валюта')

@bot.on(telethon.events.NewMessage(pattern='(?i)^валюты$'))
async def handle_currencies_command(event):
    await bot.send_message(event.chat_id, 'Валюты')

async def filter_another_commands(event):
    for word in reserved:
        if word in event.raw_text:
            return False
    return True

@bot.on(telethon.events.NewMessage(func=filter_another_commands))
async def handle_another_command(event):
    command = Command(event.raw_text)
    msg = ''

    if check_pattern(command.args[0], 'date'):
        date = get_date(command.args[0].value)
        if check_pattern(command.args[1:], 'time number text text'):
            msg = f'Добавил **{command.args[2].value} {command.args[3].value}** на дату **{command.args[0].value}** ' \
                  f'и время **{command.args[1].value}** в раздел **{command.args[4].value}**.'
            if date is None:
                msg = 'Неверно задан аргумент: дата. Он задаётся в формате ДД/ММ/ГГ или ДД/ММ/ГГГГ. Вместо ' \
                      'символа "`/`" может быть "`-`" либо "`.`".'
            time = get_time(command.args[1].value)
            if time is None: # datetime.datetime.combine(datetime.datetime.now().date(), datetime.datetime.now().time())
                if msg: msg += '\n'
                msg += 'Неверно задан аргумент: время. Он задаётся в формате ЧЧ.ММ. Вместо ' \
                      'символа "`.`" может быть "`:`".'
        elif check_pattern(command.args[1:], 'number text text'):
            now = datetime.datetime.now()
            msg = f'Добавил **{command.args[1].value} {command.args[2].value}** на дату **{command.args[0].value}** ' \
                  f'и на текущее время **({now.strftime("%H:%M")})** в раздел **{command.args[3].value}**.'
            if date is None:
                msg = 'Неверно задан аргумент: дата. Он задаётся в формате ДД/ММ/ГГ или ДД/ММ/ГГГГ. Вместо ' \
                      'символа "`/`" может быть "`-`" либо "`.`".'
    elif check_pattern(command.args, 'time number text text'):
        now = datetime.datetime.now()
        msg = f'Добавил **{command.args[1].value} {command.args[2].value}** на сегодня ' \
              f'**({now.strftime("%d.%m.%y")})** и на время **{command.args[0].value}** в раздел ' \
              f'**{command.args[3].value}**.'
        time = get_time(command.args[0].value)
        if time is None:
            msg = 'Неверно задан аргумент: время. Он задаётся в формате ЧЧ.ММ. Вместо ' \
                  'символа "`.`" может быть "`:`".'
    elif check_pattern(command.args, 'number text text'):
        now = datetime.datetime.now()
        msg = f'Добавил **{command.args[0].value} {command.args[1].value}** на сегодня ' \
              f'**({now.strftime("%d.%m.%y")})** и на текущее время **({now.strftime("%H:%M")})** в раздел ' \
              f'**{command.args[2].value}**.'
    else:
        msg = 'Неизвестная команда! Отправьте /start, чтобы посмотреть список актуальных команд.'

    if not msg:
        msg = f"Неверный набор аргументов для команды добавления! Отправьте /start, чтобы посмотреть список " \
              f"доступных аргументов."
    await bot.send_message(event.chat_id, msg, parse_mode='md')

def main():
    while True:
        try:
            bot.run_until_disconnected()
            break
        except Exception as e:
            logger.debug("Ошибка подключения: ", str(e))
            continue

if __name__ == "__main__":
    main()