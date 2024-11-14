import telethon
import datetime
from sqlalchemy import select, func, Date, DateTime, extract
from database import Session, engine, User, Section, SectionName, Record, CurrencyName, Currency
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
        if pattern[i] != args[i].type and not (pattern[i] == 'number' and args[i].type == 'time'):
            return False
    return True

def record_stringify(record: Record):
    return f"**Дата:** {record.datetime.strftime('%d.%m.%y')};\n" \
           f"**Время:** {record.datetime.strftime('%H:%M')};\n" \
           f"**Сумма:** {record.amount};\n" \
           f"**Валюта:** {', '.join(record.currency.names)};\n" \
           f"**Раздел:** {', '.join(record.section.names)}."

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
    command = Command(event.raw_text)
    msg = ''

    if not command.args:
        with Session(engine) as session:
            last_record = session.query(Record, func.max(Record.added_datetime)).one_or_none()
            if last_record:
                msg = f"Последняя добавленная запись была успешно удалена: \n\n{record_stringify(last_record[0])}"
                session.delete(last_record[0])
                session.commit()
            else:
                msg = f"Не было найдено ни одной записи."
    elif check_pattern(command.args, 'date time number text text'):
        with Session(engine) as session:
            date = get_date(command.args[0].value)
            time = get_time(command.args[1].value)
            if date is not None and time is not None:
                datetime_o = datetime.datetime.combine(date, time)
                found_record = session.query(Record).join(Currency).join(Section).\
                    where(extract('year', Record.datetime) == datetime_o.year,
                        extract('month', Record.datetime) == datetime_o.month,
                        extract('day', Record.datetime) == datetime_o.day,
                        extract('hour', Record.datetime) == datetime_o.hour,
                        extract('minute', Record.datetime) == datetime_o.minute,
                        Record.amount == float(command.args[2].value),
                        Currency.names.contains(command.args[3].value),
                        Section.names.contains(command.args[4].value))\
                    .one_or_none()
                if found_record is not None:
                    msg = f"Была удалена следующая запись: \n\n{record_stringify(found_record)}"
                    session.delete(found_record)
                    session.commit()
                else:
                    msg = f"Не было найдено ни одной записи с такими параметрами."
            elif date is None:
                msg = 'Неверно задан аргумент: дата. Он задаётся в формате ДД/ММ/ГГ или ДД/ММ/ГГГГ. Вместо ' \
                      'символа "`/`" может быть "`-`" либо "`.`".'
            elif time is None:
                msg += 'Неверно задан аргумент: время. Он задаётся в формате ЧЧ.ММ. Вместо ' \
                       'символа "`.`" может быть "`:`".'
    elif check_pattern(command.args, 'date date text'):
        date1 = get_date(command.args[0].value)
        date2 = get_date(command.args[1].value)
        if date1 is not None and date2 is not None:
            date1 = datetime.datetime.combine(date1, datetime.datetime.min.time())
            date2 = datetime.datetime.combine(date2, datetime.datetime.min.time())
            with Session(engine) as session:
                to_delete = session.query(Record.id).join(Section).filter(Section.names.contains(
                    command.args[2].value), Record.datetime.between(date1, date2))
                found_cnt = session.query(Record).filter(Record.id.in_(to_delete.subquery())).delete()
                if found_cnt:
                    session.commit()
                    msg = f"Успешно удалено {found_cnt} записей с {command.args[0].value} по " \
                          f"{command.args[1].value} в разделе {command.args[2].value}."
                else:
                    msg = f"Не было найдено ни одной записи в указанном диапазоне дат и разделе."
        else:
            msg = 'Неверно задан аргумент: дата. Он задаётся в формате ДД/ММ/ГГ или ДД/ММ/ГГГГ. Вместо ' \
                  'символа "`/`" может быть "`-`" либо "`.`".'
    elif check_pattern(command.args, 'date date'):
        date1 = get_date(command.args[0].value)
        date2 = get_date(command.args[1].value)
        if date1 is not None and date2 is not None:
            date1 = datetime.datetime.combine(date1, datetime.datetime.min.time())
            date2 = datetime.datetime.combine(date2, datetime.datetime.min.time())
            with Session(engine) as session:
                found_cnt = session.query(Record).filter(Record.datetime.between(date1, date2)).delete()
                if found_cnt:
                    session.commit()
                    msg = f"Успешно удалено {found_cnt} записей с {command.args[0].value} по " \
                          f"{command.args[1].value}."
                else:
                    msg = f"Не было найдено ни одной записи в указанном диапазоне дат."
        else:
            msg = 'Неверно задан аргумент: дата. Он задаётся в формате ДД/ММ/ГГ или ДД/ММ/ГГГГ. Вместо ' \
                  'символа "`/`" может быть "`-`" либо "`.`".'
    elif check_pattern(command.args, 'date text'):
        date = get_date(command.args[0].value)
        if date is not None:
            with Session(engine) as session:
                to_delete = session.query(Record.id).join(Section).filter(extract('year', Record.datetime) == date.year,
                      extract('month', Record.datetime) == date.month,
                      extract('day', Record.datetime) == date.day,
                      Section.names.contains(command.args[1].value))
                found_cnt = session.query(Record).filter(Record.id.in_(to_delete.subquery())).delete()
                if found_cnt:
                    session.commit()
                    msg = f"Успешно удалено {found_cnt} записей из раздела {command.args[1].value} " \
                          f"за {command.args[0].value}."
                else:
                    msg = f"Не было найдено ни одной записи за указанную дату в указанном разделе."
        else:
            msg = 'Неверно задан аргумент: дата. Он задаётся в формате ДД/ММ/ГГ или ДД/ММ/ГГГГ. Вместо ' \
                  'символа "`/`" может быть "`-`" либо "`.`".'
    elif check_pattern(command.args, 'date'):
        date = get_date(command.args[0].value)
        if date is not None:
            with Session(engine) as session:
                found_cnt = session.query(Record).filter(extract('year', Record.datetime) == date.year,
                      extract('month', Record.datetime) == date.month,
                      extract('day', Record.datetime) == date.day).delete()
                if found_cnt:
                    session.commit()
                    msg = f"Успешно удалено {found_cnt} записей за {command.args[0].value}."
                else:
                    msg = f"Не было найдено ни одной записи за указанную дату."
        else:
            msg = 'Неверно задан аргумент: дата. Он задаётся в формате ДД/ММ/ГГ или ДД/ММ/ГГГГ. Вместо ' \
                  'символа "`/`" может быть "`-`" либо "`.`".'
    else:
        msg = f"Неверный набор аргументов для команды удаления! Отправьте /start, чтобы посмотреть список " \
              f"доступных аргументов."

    await bot.send_message(event.chat_id, msg, parse_mode='md')

@bot.on(telethon.events.NewMessage(pattern='(?i)раздел +'))
async def handle_section_command(event):
    command = Command(event.raw_text)
    msg = ''
    if check_pattern(command.args, 'text text'):
        section_name = command.args[0].value
        new_name = command.args[1].value
        with Session(engine) as session:
            checked_section = session.query(Section).filter(Section.user_id == event.chat_id,
                                            Section.names.contains(section_name)).one_or_none()

            if checked_section is not None:
                    new_sectionname_o = SectionName(section_id=checked_section.id, name=new_name, 
                                                    added_datetime=datetime.datetime.now())
                    session.add(new_sectionname_o)
                    session.commit()
                    msg = f"Успешно добавлен новый синоним {new_name} для раздела {section_name}."
            else:
                msg = f"Не найдено раздела с названием {section_name}."
    else:
        msg = f"Неверный набор аргументов для команды добавления названия раздела! Отправьте /start, чтобы посмотреть список доступных аргументов."
    await bot.send_message(event.chat_id, msg)

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
    date, time, amount, currency, section = None, None, None, None, None

    if check_pattern(command.args, 'date time number text text'):
        date = get_date(command.args[0].value)
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
        try:
            amount = float(command.args[2].value.replace(',', '.'))
        except Exception as e:
            logger.debug(e)
        currency = command.args[3].value
        section = command.args[4].value
    elif check_pattern(command.args, 'number text text'):
        now = datetime.datetime.now()
        msg = f'Добавил **{command.args[0].value} {command.args[1].value}** на сегодня ' \
              f'**({now.strftime("%d.%m.%y")})** и на текущее время **({now.strftime("%H:%M")})** в раздел ' \
              f'**{command.args[2].value}**.'
        date = datetime.datetime.now().date()
        time = datetime.datetime.now().time()
        try:
            amount = float(command.args[0].value.replace(',', '.'))
        except Exception as e:
            logger.debug(e)
        currency = command.args[1].value
        section = command.args[2].value
    elif check_pattern(command.args, 'date number text text'):
        date = get_date(command.args[0].value)
        now = datetime.datetime.now()
        msg = f'Добавил **{command.args[1].value} {command.args[2].value}** на дату **{command.args[0].value}** ' \
              f'и на текущее время **({now.strftime("%H:%M")})** в раздел **{command.args[3].value}**.'
        if date is None:
            msg = 'Неверно задан аргумент: дата. Он задаётся в формате ДД/ММ/ГГ или ДД/ММ/ГГГГ. Вместо ' \
                  'символа "`/`" может быть "`-`" либо "`.`".'
        time = datetime.datetime.now().time()
        try:
            amount = float(command.args[1].value.replace(',', '.'))
        except Exception as e:
            logger.debug(e)
        currency = command.args[2].value
        section = command.args[3].value
    elif check_pattern(command.args, 'time number text text'):
        now = datetime.datetime.now()
        msg = f'Добавил **{command.args[1].value} {command.args[2].value}** на сегодня ' \
              f'**({now.strftime("%d.%m.%y")})** и на время **{command.args[0].value}** в раздел ' \
              f'**{command.args[3].value}**.'
        time = get_time(command.args[0].value)
        if time is None:
            msg = 'Неверно задан аргумент: время. Он задаётся в формате ЧЧ.ММ. Вместо ' \
                  'символа "`.`" может быть "`:`".'
        date = datetime.datetime.now().date()
        try:
            amount = float(command.args[1].value.replace(',', '.'))
        except Exception as e:
            logger.debug(e)
        currency = command.args[2].value
        section = command.args[3].value
    else:
        msg = 'Неизвестная команда! Отправьте /start, чтобы посмотреть список актуальных команд.'

    forbidden_names = False
    if any(name in reserved for name in (currency, section)):
        forbidden_names = True
        msg = 'Нельзя использовать ключевое слово в качестве названия для валюты или раздела.'

    if None in (date, time, amount, currency, section):
        if None in (amount, currency, section):
            msg = f"Неверный набор аргументов для команды добавления! Отправьте /start, чтобы посмотреть список " \
                  f"доступных аргументов."
    elif not forbidden_names:
        with Session(engine) as session:
            res_datetime = datetime.datetime.combine(date, time)
            checked_section = session.query(Section).filter(Section.user_id == event.chat_id,
                                                            Section.names.contains(section)).one_or_none()
            checked_currency = session.query(Currency).filter(Currency.user_id == event.chat_id,
                                                              Currency.names.contains(currency)).one_or_none()
            if checked_section is None:
                checked_section = Section(user_id=event.chat_id)
                session.add(checked_section)
                session.flush()
                new_section_name = SectionName(section_id=checked_section.id, name=section,
                                               added_datetime=datetime.datetime.now())
                session.add(new_section_name)
            if checked_currency is None:
                checked_currency = Currency(user_id=event.chat_id)
                session.add(checked_currency)
                session.flush()
                new_currency_name = CurrencyName(currency_id=checked_currency.id, name=currency,
                                                 added_datetime=datetime.datetime.now())
                session.add(new_currency_name)
            session.add(Record(section_id=checked_section.id, datetime=res_datetime, amount=amount,
                               currency_id=checked_currency.id, added_datetime=datetime.datetime.now()))
            session.commit()

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
