import telethon
import datetime
from asyncio import TimeoutError
from sqlalchemy import select, func, Date, DateTime, extract
from database import Session, engine, User, Section, SectionName, Record, CurrencyName, Currency
from config import read_config, config
from log import logger
from command import Command, Arg, reserved, get_date, get_time, get_month, get_year, months
from exworker import ExcelWorker

answering_state = False

bot = telethon.TelegramClient("bot", config["api_id"], config["api_hash"]).start(bot_token=config["bot_token"])

def check_pattern(args: list[Arg] | Arg, pattern: str):
    split_patt = pattern.split()
    if type(args) is Arg:
        args = [args]
    if len(args) != len(split_patt):
        if split_patt[-1] != 'comment':
            return False
        elif len(args) < len(split_patt) - 1:
            return False
    for i in range(len(args)):
        if split_patt[i] == 'comment':
            return True
        if split_patt[i] != args[i].type and not (split_patt[i] == 'number' and args[i].type == 'time') and not (
            split_patt[i] == 'month' and args[i].type in ('number', 'text')):
            return False
    return True

def record_stringify(record: Record):
    if record.comment:
        comment = f';\n**Комментарий:** {record.comment}'
    else:
        comment = '.'
    return f"**Дата:** {record.datetime.strftime('%d.%m.%y')};\n" \
           f"**Время:** {record.datetime.strftime('%H:%M')};\n" \
           f"**Сумма:** {record.amount};\n" \
           f"**Валюта:** {', '.join(record.currency.names)};\n" \
           f"**Раздел:** {', '.join(record.section.names)}" \
           f"{comment}"

async def check_user(chat_id: int):
    with Session(engine) as session:
        check_user = session.scalar(select(User).where(User.id == chat_id))
        if not check_user:
            new_user = User(id=chat_id, date=datetime.datetime.now())
            session.add(new_user)
            session.commit()

@bot.on(telethon.events.NewMessage(pattern='/start'))
async def handle_start_command(event):
    await check_user(event.chat_id)
    await bot.send_message(event.chat_id, "Привет! Управление ботом происходит через следующие предложения, которые"
                                          " могут быть написаны как с заглавными, так и со строчными буквами:\n\n"
                                          "`(<дата>) (<время>) <сумма> <валюта> <раздел> (<комментарий>)` - добавить запись (по умолчанию текущие дата и время)\n"
                                          "`Доход (<раздел>)` - узнать сведения о доходах за этот месяц\n"
                                          "`Доход <дата> (<раздел>)` - узнать сведения о доходах за конкретный день\n"
                                          "`Доход <месяц> (<раздел>)` - узнать доход за конкретный месяц\n"
                                          "`Доход <месяц> <год> (<раздел>)` - узнать доход за конкретный месяц конкретного года\n"
                                          "`Удали` - удалить последнюю запись\n"
                                          "`Удали <дата> (<время>) <сумма> <валюта> <раздел>` - удалить конкретную запись\n"
                                          "`Удали <дата> (<раздел>)` - удалить записи за день\n"
                                          "`Удали <дата> <дата> (<раздел>)` - удалить записи за диапазон дней (вторая дата - исключительно)\n"
                                          "`Записи <дата>` - просмотр всех записей за конкретную дату\n"
                                          "`Записи <дата> <дата>` - просмотр всех записей за диапазон дней (вторая дата - исключительно)\n"
                                          "`Разделы` - показать текущие разделы\n"
                                          "`Раздел <название раздела> <синоним>` - создание синонимов для разделов\n"
                                          "`Валюты` - показать текущие валюты\n"
                                          "`Валюта <название валюты> <синоним>` - создание синонимов для валют\n"
                                          "`Отчет` - отослать отчет по доходам в виде Excel-документа\n"
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
    command = Command(event.raw_text)
    msg = ''
    unknown = False

    if command.instruction is not None:
        if not command.args:
            current_month = datetime.datetime.now().month
            month_name = list(months.keys())[list(months.values()).index(current_month)]
            with Session(engine) as session:
                records = session.query(func.sum(Record.amount), Record.currency_id).join(
                    Section).group_by(Record.currency_id).order_by(Record.datetime).where(
                    Section.user_id == event.chat_id, extract('month', Record.datetime) == current_month).all()
                if records:
                    msg = f"Доходы со всех разделов за {month_name}\n\n"
                    for i, r in enumerate(records):
                        cnames = session.query(CurrencyName.name).join(Currency).order_by(
                            CurrencyName.added_datetime).where(CurrencyName.currency_id == r[1]).all()
                        names = [name[0] for name in cnames]
                        msg += f"**Валюта**: {', '.join(names)}\n"
                        msg += f"**Сумма**: {r[0]}\n\n"
                else:
                    msg = f"Нет доходов."
        elif check_pattern(command.args, 'text') and not command.args[0].value in months.keys():
            current_month = datetime.datetime.now().month
            month_name = list(months.keys())[list(months.values()).index(current_month)]
            with Session(engine) as session:
                records = session.query(func.sum(Record.amount), Record.currency_id).join(
                    Section).group_by(Record.currency_id).order_by(Record.datetime).where(
                    Section.user_id == event.chat_id, extract('month', Record.datetime) == current_month,
                    Section.names.like(command.args[0].value)).all()
                if records:
                    msg = f"Доходы в разделе **{command.args[0].original_value}** за {month_name}\n\n"
                    for i, r in enumerate(records):
                        cnames = session.query(CurrencyName.name).order_by(CurrencyName.added_datetime).where(
                            CurrencyName.currency_id == r[1]).all()
                        names = [name[0] for name in cnames]
                        msg += f"**Валюта**: {', '.join(names)}\n"
                        msg += f"**Сумма**: {r[0]}\n\n"
                else:
                    msg = f"Нет доходов."
        elif check_pattern(command.args, 'month'):
            month = get_month(command.args[0].value)
            if month is not None:
                month_name = list(months.keys())[list(months.values()).index(month)]
                with Session(engine) as session:
                    records = session.query(func.sum(Record.amount), Record.currency_id).join(
                        Section).group_by(Record.currency_id).order_by(Record.datetime).where(
                        Section.user_id == event.chat_id, extract('month', Record.datetime) == month).all()
                    if records:
                        msg = f"Доходы со всех разделов за {month_name}\n\n"
                        for i, r in enumerate(records):
                            cnames = session.query(CurrencyName.name).order_by(CurrencyName.added_datetime).where(
                                CurrencyName.currency_id == r[1]).all()
                            names = [name[0] for name in cnames]
                            msg += f"**Валюта**: {', '.join(names)}\n"
                            msg += f"**Сумма**: {r[0]}\n\n"
                    else:
                        msg = f"Нет доходов."
            else:
                msg = 'Неверно задан аргумент: месяц. Он задаётся либо названием месяца, либо его порядковым ' \
                      'номером в году.'
        elif check_pattern(command.args, 'date'):
            date = get_date(command.args[0].value)
            if date is not None:
                with Session(engine) as session:
                    records = session.query(func.sum(Record.amount), Record.currency_id).join(
                        Section).group_by(Record.currency_id).order_by(Record.datetime).where(
                        Section.user_id == event.chat_id,
                        extract('year', Record.datetime) == date.year,
                        extract('month', Record.datetime) == date.month,
                        extract('day', Record.datetime) == date.day).all()
                    if records:
                        msg = f"Доходы со всех разделов за {command.args[0].original_value}\n\n"
                        for i, r in enumerate(records):
                            cnames = session.query(CurrencyName.name).order_by(CurrencyName.added_datetime).where(
                                CurrencyName.currency_id == r[1]).all()
                            names = [name[0] for name in cnames]
                            msg += f"**Валюта**: {', '.join(names)}\n"
                            msg += f"**Сумма**: {r[0]}\n\n"
                    else:
                        msg = f"Нет доходов."
            else:
                msg = 'Неверно задан аргумент: дата. Он задаётся в формате ДД/ММ/ГГ или ДД/ММ/ГГГГ. Вместо ' \
                      'символа "`/`" может быть "`-`" либо "`.`".'
        elif check_pattern(command.args, 'month text'):
            month = get_month(command.args[0].value)
            if month is not None:
                month_name = list(months.keys())[list(months.values()).index(month)]
                with Session(engine) as session:
                    records = session.query(func.sum(Record.amount), Record.currency_id).join(
                        Section).group_by(Record.currency_id).order_by(Record.datetime).where(
                        Section.user_id == event.chat_id, extract('month', Record.datetime) == month,
                        Section.names.like(command.args[1].value)).all()
                    if records:
                        msg = f"Доходы в разделе {command.args[1].original_value} за {month_name}\n\n"
                        for i, r in enumerate(records):
                            cnames = session.query(CurrencyName.name).order_by(CurrencyName.added_datetime).where(
                                CurrencyName.currency_id == r[1]).all()
                            names = [name[0] for name in cnames]
                            msg += f"**Валюта**: {', '.join(names)}\n"
                            msg += f"**Сумма**: {r[0]}\n\n"
                    else:
                        msg = f"Нет доходов."
            else:
                msg = 'Неверно задан аргумент: месяц. Он задаётся либо названием месяца, либо его порядковым ' \
                      'номером в году.'
        elif check_pattern(command.args, 'date text'):
            date = get_date(command.args[0].value)
            if date is not None:
                with Session(engine) as session:
                    records = session.query(func.sum(Record.amount), Record.currency_id).join(
                        Section).group_by(Record.currency_id).order_by(Record.datetime).where(
                        Section.user_id == event.chat_id,
                        extract('year', Record.datetime) == date.year,
                        extract('month', Record.datetime) == date.month,
                        extract('day', Record.datetime) == date.day,
                        Section.names.like(command.args[1].value)).all()
                    if records:
                        msg = f"Доходы в разделе {command.args[1].original_value} за " \
                              f"{command.args[0].original_value}\n\n"
                        for i, r in enumerate(records):
                            cnames = session.query(CurrencyName.name).order_by(CurrencyName.added_datetime).where(
                                CurrencyName.currency_id == r[1]).all()
                            names = [name[0] for name in cnames]
                            msg += f"**Валюта**: {', '.join(names)}\n"
                            msg += f"**Сумма**: {r[0]}\n\n"
                    else:
                        msg = f"Нет доходов."
            else:
                msg = 'Неверно задан аргумент: дата. Он задаётся в формате ДД/ММ/ГГ или ДД/ММ/ГГГГ. Вместо ' \
                      'символа "`/`" может быть "`-`" либо "`.`".'
        elif check_pattern(command.args, 'month number'):
            month = get_month(command.args[0].value)
            year = get_year(command.args[1].value)
            if month is not None:
                if year is not None:
                    month_name = list(months.keys())[list(months.values()).index(month)]
                    with Session(engine) as session:
                        records = session.query(func.sum(Record.amount), Record.currency_id).join(
                            Section).group_by(Record.currency_id).order_by(Record.datetime).where(
                            Section.user_id == event.chat_id, extract('month', Record.datetime) == month,
                            extract('year', Record.datetime) == year).all()
                        if records:
                            msg = f"Доходы со всех разделов за {month_name} {year} года\n\n"
                            for i, r in enumerate(records):
                                cnames = session.query(CurrencyName.name).order_by(CurrencyName.added_datetime).where(
                                    CurrencyName.currency_id == r[1]).all()
                                names = [name[0] for name in cnames]
                                msg += f"**Валюта**: {', '.join(names)}\n"
                                msg += f"**Сумма**: {r[0]}\n\n"
                        else:
                            msg = f"Нет доходов."
                else:
                    msg = 'Неверно задан аргумент: год. Он задаётся либо полным числом (например, **2024**) ' \
                          'либо неполным числом (например, **24**).'
            else:
                msg = 'Неверно задан аргумент: месяц. Он задаётся либо названием месяца, либо его порядковым ' \
                      'номером в году.'
        elif check_pattern(command.args, 'month number text'):
            month = get_month(command.args[0].value)
            year = get_year(command.args[1].value)
            if month is not None:
                if year is not None:
                    month_name = list(months.keys())[list(months.values()).index(month)]
                    with Session(engine) as session:
                        records = session.query(func.sum(Record.amount), Record.currency_id).join(
                            Section).group_by(Record.currency_id).order_by(Record.datetime).where(
                            Section.user_id == event.chat_id, extract('month', Record.datetime) == month,
                            extract('year', Record.datetime) == year,
                            Section.names.like(command.args[2].value)).all()
                        if records:
                            msg = f"Доходы в разделе {command.args[2].original_value} за {month_name} {year} года\n\n"
                            for i, r in enumerate(records):
                                cnames = session.query(CurrencyName.name).order_by(CurrencyName.added_datetime).where(
                                    CurrencyName.currency_id == r[1]).all()
                                names = [name[0] for name in cnames]
                                msg += f"**Валюта**: {', '.join(names)}\n"
                                msg += f"**Сумма**: {r[0]}\n\n"
                        else:
                            msg = f"Нет доходов."
                else:
                    msg = 'Неверно задан аргумент: год. Он задаётся либо полным числом (например, **2024**) ' \
                          'либо неполным числом (например, **24**).'
            else:
                msg = 'Неверно задан аргумент: месяц. Он задаётся либо названием месяца, либо его порядковым ' \
                      'номером в году.'
        else:
            unknown = True
    else:
        unknown = True

    if unknown:
        msg = f"Неверный набор аргументов для команды `доход`! Отправьте /start, чтобы посмотреть список " \
              f"доступных аргументов."

    await bot.send_message(event.chat_id, msg, parse_mode='md')

@bot.on(telethon.events.NewMessage(pattern='(?i)удали+'))
async def handle_delete_command(event):
    command = Command(event.raw_text)
    msg = ''

    if not command.args:
        with Session(engine) as session:
            last_record = session.query(Record).join(Section).order_by(Record.added_datetime.desc()).where(
                Section.user_id == event.chat_id).first()
            if last_record is not None:
                msg = f"Последняя добавленная запись была успешно удалена: \n\n{record_stringify(last_record)}"
                session.delete(last_record)
                session.commit()
            else:
                msg = f"Не было найдено ни одной записи."
    elif check_pattern(command.args, 'date number text text'):
        with Session(engine) as session:
            date = get_date(command.args[0].value)
            if date is not None:
                found_record = session.query(Record).join(Currency).join(Section).\
                    where(extract('year', Record.datetime) == date.year,
                        extract('month', Record.datetime) == date.month,
                        extract('day', Record.datetime) == date.day,
                        Record.amount == float(command.args[1].value),
                        Currency.names.like(command.args[2].value),
                        Section.names.like(command.args[3].value),
                        Section.user_id == event.chat_id)\
                    .first()
                if found_record is not None:
                    msg = f"Была удалена следующая запись: \n\n{record_stringify(found_record)}"
                    session.delete(found_record)
                    session.commit()
                else:
                    msg = f"Не было найдено ни одной записи с такими параметрами."
            elif date is None:
                msg = 'Неверно задан аргумент: дата. Он задаётся в формате ДД/ММ/ГГ или ДД/ММ/ГГГГ. Вместо ' \
                      'символа "`/`" может быть "`-`" либо "`.`".'
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
                        Currency.names.like(command.args[3].value),
                        Section.names.like(command.args[4].value),
                        Section.user_id == event.chat_id)\
                    .first()
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
                to_delete = session.query(Record.id).join(Section).filter(Section.names.like(
                    command.args[2].value), Record.datetime.between(date1, date2), Section.user_id == event.chat_id)
                found_cnt = session.query(Record).filter(Record.id.in_(to_delete)).delete()

                if found_cnt:
                    session.commit()
                    msg = f"Успешно удалено {found_cnt} записей с {command.args[0].value} по " \
                          f"{command.args[1].value} в разделе {command.args[2].original_value}."
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
                to_delete = session.query(Record.id).join(Section).filter(Section.user_id == event.chat_id,
                                                                       Record.datetime.between(date1, date2))
                found_cnt = session.query(Record).filter(Record.id.in_(to_delete)).delete()

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
                      Section.names.like(command.args[1].value),
                      Section.user_id == event.chat_id)
                found_cnt = session.query(Record).filter(Record.id.in_(to_delete)).delete()

                if found_cnt:
                    session.commit()
                    msg = f"Успешно удалено {found_cnt} записей из раздела {command.args[1].original_value} " \
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
                to_delete = session.query(Record.id).join(Section).filter(extract('year', Record.datetime) == date.year,
                      extract('month', Record.datetime) == date.month,
                      extract('day', Record.datetime) == date.day,
                      Section.user_id == event.chat_id)
                found_cnt = session.query(Record).filter(Record.id.in_(to_delete)).delete()

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

@bot.on(telethon.events.NewMessage(pattern='(?i)раздел+(?!ы)'))
async def handle_section_command(event):
    command = Command(event.raw_text)
    msg = ''

    if len(command.args) == 2 and command.args[1].original_value in list(months.keys()) + reserved:
        msg = 'Нельзя использовать ключевое слово в качестве названия для раздела.'
        await bot.send_message(event.chat_id, msg, parse_mode='md')
        return

    if check_pattern(command.args, 'text text'):
        global answering_state
        section_name = command.args[0].value
        new_name = command.args[1].value
        with Session(engine) as session:
            checked_section = session.query(Section).filter(Section.user_id == event.chat_id,
                                            Section.names.like(section_name)).first()
            checked_synonym = session.query(Section).filter(Section.user_id == event.chat_id,
                                            Section.names.like(new_name)).first()
            if checked_section is not None:
                if checked_synonym is not None:
                    if len(checked_synonym.sn) > 1:
                        sn = session.query(SectionName).join(Section).filter(SectionName.name == new_name,
                                                                             Section.user_id == event.chat_id).first()
                        sn.section_id = checked_section.id
                        new_synonyms = list(set(checked_synonym.names) - set([new_name]))
                        msg = f"Слово **{command.args[1].original_value}** теперь является синонимом для раздела " \
                              f"**{command.args[0].original_value}**. " \
                              f"У раздела **{new_synonyms[0]}** остались следующие синонимы:\n" \
                              f"{', '.join(new_synonyms)}"
                    else:
                        try:
                            async with bot.conversation(event.chat_id) as conv:
                                answering_state = True
                                await conv.send_message(f'У раздела **{command.args[1].original_value}** есть только ' \
                                                        f'одно название. Присвоение этого названия разделу ' \
                                                        f'**{command.args[0].original_value}** повлечет перенесение ' \
                                                        f'всех записей из раздела **{command.args[1].original_value}**'\
                                                        f' в раздел **{command.args[0].original_value}**. '
                                                        f'Хотите продолжить? (Да/Нет)', parse_mode='md')
                                text = await conv.get_response()
                                text = text.raw_text
                                if text is not None and text.lower() in ('да', 'д'):
                                    for sn in checked_synonym.sn: # len(sn) == 1
                                        sn.section_id = checked_section.id
                                    for record in checked_synonym.records:
                                        record.section_id = checked_section.id
                                    msg = f"Раздел **{command.args[1].original_value}** успешно добавлен в список " \
                                          f"синонимов раздела " \
                                          f"**{command.args[0].original_value}**, а записи в этих разделах объединены."
                                else:
                                    msg = "Раздел не был переименован."
                                answering_state = False
                        except TimeoutError:
                            msg = "Время ожидания ответа истекло."
                else:
                    new_sectionname_o = SectionName(section_id=checked_section.id, name=new_name,
                                                    added_datetime=datetime.datetime.now())
                    session.add(new_sectionname_o)
                    msg = f"Новый синоним **{command.args[1].original_value}** для раздела " \
                          f"**{command.args[0].original_value}** успешно добавлен."
            else:
                msg = f"Не найдено раздела с названием **{command.args[0].original_value}**."
            session.commit()
    else:
        msg = f"Неверный набор аргументов для команды добавления названия раздела! Отправьте /start, чтобы " \
              f"посмотреть список доступных аргументов."

    await bot.send_message(event.chat_id, msg, parse_mode='md')

@bot.on(telethon.events.NewMessage(pattern='(?i)разделы+'))
async def handle_sections_command(event):
    command = Command(event.raw_text)
    msg = ''
    if command.instruction is not None and not command.args:
        with Session(engine) as session:
            sections = session.query(Section).where(Section.user_id == event.chat_id).all()
            if sections:
                msg = f"Список разделов:\n\n"
                for i, s in enumerate(sections):
                    snames = session.query(SectionName.name).join(Section).order_by(SectionName.added_datetime).where(
                        SectionName.section_id == s.id, Section.user_id == event.chat_id).all()
                    if not len(snames):
                        continue
                    names = [name[0] for name in snames]
                    msg += f"{i + 1}. **{names[0]}** " \
                           f"{'(' + ', '.join([name for name in names[1:]]) + ')' if names[1:] else ''}\n"
            else:
                msg = f"Не найдено ни одного раздела."
    else:
        msg = f"Неверный набор аргументов для команды просмотра разделов! Отправьте /start, чтобы " \
              f"посмотреть список доступных аргументов."

    await bot.send_message(event.chat_id, msg, parse_mode='md')

@bot.on(telethon.events.NewMessage(pattern='(?i)валюта+'))
async def handle_currency_command(event):
    command = Command(event.raw_text)
    msg = ''

    if len(command.args) == 2 and command.args[1].original_value in list(months.keys()) + reserved:
        msg = 'Нельзя использовать ключевое слово в качестве названия для валюты.'
        await bot.send_message(event.chat_id, msg, parse_mode='md')
        return

    if check_pattern(command.args, 'text text'):
        global answering_state
        currency_name = command.args[0].value
        new_name = command.args[1].value
        with Session(engine) as session:
            checked_currency = session.query(Currency).filter(Currency.user_id == event.chat_id,
                                                              Currency.names.like(currency_name)).first()
            checked_synonym = session.query(Currency).filter(Currency.user_id == event.chat_id,
                                            Currency.names.like(new_name)).first()
            if checked_currency is not None:
                if checked_synonym is not None:
                    if len(checked_synonym.cn) > 1:
                        cn = session.query(CurrencyName).join(Currency).filter(CurrencyName.name == new_name,
                                                                            Currency.user_id == event.chat_id).first()
                        cn.currency_id = checked_currency.id
                        new_synonyms = list(set(checked_synonym.names) - set([new_name]))
                        msg = f"Слово **{command.args[1].original_value}** теперь является синонимом для валюты " \
                              f"**{command.args[0].original_value}**. " \
                              f"У валюты **{new_synonyms[0]}** остались следующие синонимы:\n" \
                              f"{', '.join(new_synonyms)}"
                    else:
                        try:
                            async with bot.conversation(event.chat_id) as conv:
                                answering_state = True
                                await conv.send_message(f'У валюты **{command.args[1].original_value}** есть только ' \
                                                        f'одно название. Присвоение этого названия валюте ' \
                                                        f'**{command.args[0].original_value}** повлечет перенесение ' \
                                                        f'всех записей с валютой **{command.args[1].original_value}** '\
                                                        f'к валюте **{command.args[0].original_value}**. '\
                                                        f'Хотите продолжить? (Да/Нет)', parse_mode='md')
                                text = await conv.get_response()
                                text = text.raw_text
                                if text is not None and text.lower() in ('да', 'д'):
                                    for cn in checked_synonym.cn:
                                        cn.currency_id = checked_currency.id
                                    for record in checked_synonym.records:
                                        record.currency_id = checked_currency.id
                                    msg = f"Валюта **{command.args[1].original_value}** успешно добавлена в список " \
                                          f"синонимов валюты **{command.args[0].original_value}**, а записи с этими " \
                                          f"валютами объединены."
                                else:
                                    msg = "Валюта не была переименована."
                                answering_state = False
                        except TimeoutError:
                            msg = "Время ожидания ответа истекло."
                else:
                    new_currencyname_o = CurrencyName(currency_id=checked_currency.id, name=new_name,
                                                      added_datetime=datetime.datetime.now())
                    session.add(new_currencyname_o)
                    msg = f"Новый синоним **{command.args[1].original_value}** для валюты " \
                          f"**{command.args[0].original_value}** успешно добавлен."
            else:
                msg = f"Не найдено валюты с названием **{currency_name}**."
            session.commit()
    else:
        msg = f"Неверный набор аргументов для команды добавления названия валюты! Отправьте /start, чтобы " \
              f"посмотреть список доступных аргументов."

    await bot.send_message(event.chat_id, msg, parse_mode='md')

@bot.on(telethon.events.NewMessage(pattern='(?i)валюты'))
async def handle_currencies_command(event):
    command = Command(event.raw_text)
    msg = ''
    if command.instruction is not None and not command.args:
        with Session(engine) as session:
            currencies = session.query(Currency).where(Currency.user_id == event.chat_id).all()
            if currencies:
                msg = f"Список валют:\n\n"
                for i, c in enumerate(currencies):
                    snames = session.query(CurrencyName.name).join(Currency).order_by(CurrencyName.added_datetime).where(
                        CurrencyName.currency_id == c.id, Currency.user_id == event.chat_id).all()
                    if not len(snames):
                        continue
                    names = [name[0] for name in snames]
                    msg += f"{i + 1}. **{names[0]}** " \
                           f"{'(' + ', '.join([name for name in names[1:]]) + ')' if names[1:] else ''}\n"
            else:
                msg = f"Не найдено ни одной валюты."
    else:
        msg = f"Неверный набор аргументов для команды просмотра валют! Отправьте /start, чтобы " \
              f"посмотреть список доступных аргументов."

    await bot.send_message(event.chat_id, msg, parse_mode='md')

@bot.on(telethon.events.NewMessage(pattern='(?i)отч[её]т'))
async def handle_report_command(event):
    async def get_section_currencies(records: list[Record]):
        result_dict = {}

        for record in records:
            first_section_name = record.section.names[0] if record.section else None

            if first_section_name:
                if first_section_name not in result_dict:
                    result_dict[first_section_name] = []

                if record.currency.cn[0] not in result_dict[first_section_name]:
                    result_dict[first_section_name].append(record.currency.cn[0])

        for section in result_dict:
            result_dict[section].sort(key=lambda cur: cur.added_datetime)
            result_dict[section] = [cur.name for cur in result_dict[section]]

        return result_dict


    command = Command(event.raw_text)

    if command.instruction is not None and not command.args:
        with Session(engine) as session:
            records = session.query(Record).join(Section).join(SectionName).join(Currency).join(
                CurrencyName).where(Section.user_id == event.chat_id).order_by(
                SectionName.added_datetime, Record.datetime, CurrencyName.added_datetime).all()
            years = sorted(list(set([str(r.datetime.year) for r in records])))
            section_currencies = await get_section_currencies(records)
            if not records:
                await bot.send_message(event.chat_id, "Отчет не может быть сформирован: не найдено ни одной записи.")
                return
            try:
                ew = ExcelWorker(records, years, section_currencies)
                file = ew.get_bytes()
                file.name = f"Отчет-{datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S-%f')}.xlsx"
                file.seek(0)
                await bot.send_message(event.chat_id, 'Отчет успешно сформирован.', parse_mode='md', file=file)
            except Exception as e:
                raise(e)
                await bot.send_message(event.chat_id, "При формировании отчета возникла ошибка.")
    else:
        msg = f"Команда `Отчет` должна вызываться без аргументов."
        await bot.send_message(event.chat_id, msg)


@bot.on(telethon.events.NewMessage(pattern='(?i)записи+'))
async def handle_records_command(event):
    command = Command(event.raw_text)
    msg = ''

    if check_pattern(command.args, 'date'):
        date = get_date(command.args[0].value)
        if date is not None:
            with Session(engine) as session:
                records = session.query(Record).order_by(Record.datetime).join(
                    Section).where(
                    Section.user_id == event.chat_id,
                    extract('year', Record.datetime) == date.year,
                    extract('month', Record.datetime) == date.month,
                    extract('day', Record.datetime) == date.day).all()
                if records:
                    msg = f"Все записи за {command.args[0].original_value}\n\n"
                    for r in records:
                        add_to_msg = record_stringify(r) + '\n\n'
                        if len(msg + add_to_msg) > 4096:
                            await bot.send_message(event.chat_id, msg)
                            msg = add_to_msg
                            continue
                        msg += add_to_msg
                else:
                    msg = f"Нет записей за указанную дату."
        else:
            msg = 'Неверно задан аргумент: дата. Он задаётся в формате ДД/ММ/ГГ или ДД/ММ/ГГГГ. Вместо ' \
                  'символа "`/`" может быть "`-`" либо "`.`".'
    elif check_pattern(command.args, 'date date'):
        date1 = get_date(command.args[0].value)
        date2 = get_date(command.args[1].value)
        if date1 is not None and date2 is not None:
            with Session(engine) as session:
                records = session.query(Record).order_by(Record.datetime).join(
                    Section).where(
                    Section.user_id == event.chat_id,
                    Record.datetime.between(date1, date2)).all()
                if records:
                    msg = f"Все записи за {command.args[0].original_value} - {command.args[1].original_value}\n\n"
                    for r in records:
                        add_to_msg = record_stringify(r) + '\n\n'
                        if len(msg + add_to_msg) > 4096:
                            await bot.send_message(event.chat_id, msg)
                            msg = add_to_msg
                            continue
                        msg += add_to_msg
                else:
                    msg = f"Нет записей за указанный диапазон дней."
        else:
            msg = 'Неверно задан аргумент: дата. Он задаётся в формате ДД/ММ/ГГ или ДД/ММ/ГГГГ. Вместо ' \
                  'символа "`/`" может быть "`-`" либо "`.`".'
    else:
        msg = f"Неверный набор аргументов для команды просмотра записей! Отправьте /start, чтобы " \
              f"посмотреть список доступных аргументов."

    await bot.send_message(event.chat_id, msg, parse_mode='md')

async def filter_another_commands(event):
    await check_user(event.chat_id)
    if answering_state:
        return False
    for word in reserved:
        if event.raw_text.lower().startswith(word):
            return False
    return True

@bot.on(telethon.events.NewMessage(func=filter_another_commands))
async def handle_another_command(event):
    command = Command(event.raw_text)
    msg = ''
    unknown = False
    date, time, amount, currency, section, comment = None, None, None, None, None, None

    if check_pattern(command.args, 'date time number text text comment'):
        date = get_date(command.args[0].value)
        comment = ' '.join([arg.original_value for arg in command.args[5:]])
        msg = f'Добавил **{command.args[2].value} {command.args[3].original_value}** на дату ' \
              f'**{command.args[0].value}** ' \
              f'и время **{command.args[1].value}** в раздел **{command.args[4].original_value}**.'
        if comment:
            msg += f" Комментарий: {comment}"
        if date is None:
            msg = 'Неверно задан аргумент: дата. Он задаётся в формате ДД/ММ/ГГ или ДД/ММ/ГГГГ. Вместо ' \
                  'символа "`/`" может быть "`-`" либо "`.`".'
        time = get_time(command.args[1].value)
        if time is None:
            if msg: msg += '\n'
            msg += 'Неверно задан аргумент: время. Он задаётся в формате ЧЧ.ММ. Вместо ' \
                  'символа "`.`" может быть "`:`".'
        try:
            amount = float(command.args[2].value.replace(',', '.'))
        except Exception as e:
            logger.debug(e)
        currency = command.args[3].value
        section = command.args[4].value
    elif check_pattern(command.args, 'number text text comment'):
        now = datetime.datetime.now()
        comment = ' '.join([arg.original_value for arg in command.args[3:]])
        msg = f'Добавил **{command.args[0].value} {command.args[1].original_value}** на сегодня ' \
              f'**({now.strftime("%d.%m.%y")})** и на текущее время **({now.strftime("%H:%M")})** в раздел ' \
              f'**{command.args[2].original_value}**.'
        if comment:
            msg += f" Комментарий: {comment}"
        date = datetime.datetime.now().date()
        time = datetime.datetime.now().time()
        try:
            amount = float(command.args[0].value.replace(',', '.'))
        except Exception as e:
            logger.debug(e)
        currency = command.args[1].value
        section = command.args[2].value
    elif check_pattern(command.args, 'date number text text comment'):
        date = get_date(command.args[0].value)
        now = datetime.datetime.now()
        comment = ' '.join([arg.original_value for arg in command.args[4:]])
        msg = f'Добавил **{command.args[1].value} {command.args[2].original_value}** на дату ' \
              f'**{command.args[0].value}** ' \
              f'и на текущее время **({now.strftime("%H:%M")})** в раздел **{command.args[3].original_value}**.'
        if comment:
            msg += f" Комментарий: {comment}"
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
    elif check_pattern(command.args, 'time number text text comment'):
        now = datetime.datetime.now()
        comment = ' '.join([arg.original_value for arg in command.args[4:]])
        msg = f'Добавил **{command.args[1].value} {command.args[2].original_value}** на сегодня ' \
              f'**({now.strftime("%d.%m.%y")})** и на время **{command.args[0].value}** в раздел ' \
              f'**{command.args[3].original_value}**.'
        if comment:
            msg += f" Комментарий: {comment}"
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
        unknown = True

    forbidden_names = False
    if any(name in list(months.keys()) + reserved for name in (currency, section)):
        forbidden_names = True
        msg = 'Нельзя использовать ключевое слово в качестве названия для валюты или раздела.'

    if unknown:
        msg = 'Неизвестная команда! Отправьте /start, чтобы посмотреть список актуальных команд.'
    elif None in (date, time, amount, currency, section):
        if None in (amount, currency, section):
            msg = f"Неверный набор аргументов для команды добавления! Отправьте /start, чтобы посмотреть список " \
                  f"доступных аргументов."
    elif not forbidden_names:
        with Session(engine) as session:
            res_datetime = datetime.datetime.combine(date, time)
            checked_section = session.query(Section).filter(Section.user_id == event.chat_id,
                                                            Section.names.like(section)).first()
            checked_currency = session.query(Currency).filter(Currency.user_id == event.chat_id,
                                                              Currency.names.like(currency)).first()
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
                               currency_id=checked_currency.id, added_datetime=datetime.datetime.now(),
                               comment=comment))
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

