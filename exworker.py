from openpyxl import Workbook
from openpyxl.styles import Color, Alignment, PatternFill
from io import BytesIO
from database import Record, Currency, Session, engine

class ExcelWorker:
    def __init__(self, records: list[Record]):
        self.wb = Workbook()
        current_ws = self.wb.active
        current_ws.title = 'Записи'
        self.wb.create_sheet('Сводка')
        self.add_records(records)
        self.add_summary(records)

    def get_bytes(self):
        res = BytesIO()
        self.wb.save(res)
        return res

    def add_records(self, records: list[Record]):
        col_size = 15
        ws = self.wb['Записи']
        ws.append(["№ Записи", "Раздел", "Валюта", "Значение", "Дата", "Дата добавления", "Комментарий",
                   "Месяц", "Видимое",])
        ws.column_dimensions["A"].width = col_size
        ws.column_dimensions["B"].width = col_size
        ws.column_dimensions["C"].width = col_size
        ws.column_dimensions["D"].width = col_size
        ws.column_dimensions["E"].width = col_size * 2
        ws.column_dimensions["F"].width = col_size * 2
        ws.column_dimensions["G"].width = col_size * 3
        ws.column_dimensions["H"].hidden = True
        ws.column_dimensions["I"].hidden = True
        # print(len(records)) 34
        data = [[r.id, r.section.names[0], r.currency.names[0], r.amount, r.datetime, r.added_datetime,
                 r.comment, r.datetime.month, f"=SUBTOTAL(9,D{i+2})"] # (i+1)+1, т.к. записи начиная со 2 строки
                for i, r in enumerate(records)]
        for row in data:
            ws.append(row)

        ws.auto_filter.ref = f'A1:G{len(data) + 1}'

    def add_summary(self, records: list[Record]):
        first_width = 15
        last_width = 20
        xl_recs_end = len(records) + 1
        curr_names = list(set(r.currency.names[0] for r in records))

        ws = self.wb['Сводка']
        ws.column_dimensions["A"].width = first_width
        ws.column_dimensions["N"].width = last_width
        ws.append(["Валюта\\Месяц", "янв.", "февр.", "мар.", "апр.", "май", "июн.", "июл.", "авг.", "сент.", "окт.",
                   "нояб.", "дек.", "Итого"])
        first_row = ws[1]
        first_row[0].fill = PatternFill(patternType="solid", fgColor=Color(rgb='ffc000'))
        for cell in first_row[1:13]:
            cell.fill = PatternFill(patternType="solid", fgColor=Color(rgb='70ad47'))
        first_row[-1].fill = PatternFill(patternType="solid", fgColor=Color(rgb='ed7d31'))

        ws.insert_rows(len(curr_names) + 2, len(curr_names))
        for row in ws.iter_rows(min_row=2, max_row=len(curr_names) + 1, max_col=14):
            row[0].value = curr_names[row[0].row - 2]
            row[0].fill = PatternFill(patternType="solid", fgColor=Color(rgb='ffff00'))
            for i, cell in enumerate(row[1:13]):
                cell.value = f'=SUMIFS(Записи!$I$2:$I${xl_recs_end},Записи!$C$2:$C${xl_recs_end},"="&' \
                             f'Сводка!$A{row[0].row},Записи!$H$2:$H${xl_recs_end},{i + 1})'
                cell.fill = PatternFill(patternType="solid", fgColor=Color(rgb='e2efda'))
            row[-1].value = f"=SUM({row[1].coordinate}:{row[-2].coordinate})"
            row[-1].fill = PatternFill(patternType="solid", fgColor=Color(rgb='f8cbad'))

