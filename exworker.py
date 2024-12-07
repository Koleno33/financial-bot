from openpyxl import Workbook
from openpyxl.styles import Color, Alignment, PatternFill, Border, Side
from openpyxl.worksheet.formula import ArrayFormula
from openpyxl.worksheet.datavalidation import DataValidation
from io import BytesIO
from database import Record, Currency, Session, engine
from datetime import datetime

class ExcelWorker:
    def __init__(self, records: list[Record], years: list[str], section_currencies: dict[str: list]):
        self.wb = Workbook()
        current_ws = self.wb.active
        current_ws.title = 'Записи'
        self.wb.create_sheet('Промежуточный')
        self.wb.create_sheet('Сводка')
        self.add_records(records)
        self.add_summary(len(records), years, section_currencies)
        self.add_inter(len(records))

    def get_bytes(self):
        res = BytesIO()
        self.wb.save(res)
        return res

    def add_records(self, records: list[Record]):
        col_size = 15
        ws = self.wb['Записи']
        ws.append(["№ Записи", "Раздел", "Валюта", "Значение", "Дата", "Дата добавления", "Комментарий",
                   "Месяц", "Видимое"])
        ws.column_dimensions["A"].width = col_size
        ws.column_dimensions["B"].width = col_size
        ws.column_dimensions["C"].width = col_size
        ws.column_dimensions["D"].width = col_size
        ws.column_dimensions["E"].width = col_size * 2
        ws.column_dimensions["F"].width = col_size * 2
        ws.column_dimensions["G"].width = col_size * 3
        ws.column_dimensions["H"].hidden = True
        ws.column_dimensions["I"].hidden = True

        data = [[r.id, r.section.names[0], r.currency.names[0], r.amount, r.datetime, r.added_datetime,
                 r.comment, r.datetime.month, f"=SUBTOTAL(9,D{i+2})"] # (i+1)+1, т.к. записи начиная со 2 строки
                for i, r in enumerate(records)]
        for row in data:
            ws.append(row)

        ws.auto_filter.ref = f'A1:G{len(data) + 1}'

    def add_inter(self, records_length: int):
        ws = self.wb['Промежуточный']
        ws.sheet_state = "hidden"
        formula = f"""=_xlfn.FILTER(
          Записи!$A$2:$G${records_length + 1},
          (Записи!$E$2:$E${records_length + 1}>=DATE(Сводка!$B$1,$I$2,1))*
          (Записи!$E$2:$E${records_length + 1}<=DATE(Сводка!$B$1,$I$2 + 1,1)),
          \"\"
        )"""
        #formula = f"""=_xlfn.FILTER(
        #  Записи!$A$2:$G${records_length + 1},
        #  (Записи!$E$2:$E${records_length + 1}>=DATE(Сводка!$B$1,$I$2,1))*
        #  (Записи!$E$2:$E${records_length + 1}<=DATE(Сводка!$B$1,$I$2 + 1,1))*
        #  (NOT(ISERROR(Записи!$E$2:$E${records_length + 1}))),
        #  \"\"
        #)"""
        ws["A1"] = ArrayFormula(f"A1:G{records_length}", formula)
        ws["I1"] = ArrayFormula(f"I1:I1", f"=IFERROR(A1=A{records_length},FALSE)")
        ws["I2"] = ArrayFormula(f"I2:I2", f"=MONTH(DATEVALUE(\"01.\"&Сводка!B2&\".2024\"))")

    def add_summary(self, records_length: int, years: list[int], section_currencies):
        ws = self.wb['Сводка']
        months = "январь,февраль,март,апрель,май,июнь,июль,август,сентябрь,октябрь,ноябрь,декабрь"

        border = Border(
            left=Side(border_style="thin", color='FF000000'),
            right=Side(border_style="thin", color='FF000000'),
            top=Side(border_style="thin", color='FF000000'),
            bottom=Side(border_style="thin", color='FF000000'),
            diagonal=Side(border_style=None, color='FF000000'),
            diagonal_direction=0,
            outline=Side(border_style=None, color='FF000000'),
            vertical=Side(border_style=None, color='FF000000'),
            horizontal=Side(border_style=None, color='FF000000')
        )

        ws["A1"] = "Год"
        ws["A2"] = "Месяц"
        ws.column_dimensions["F"].hidden = True
        ws.column_dimensions["K"].hidden = True
        ws.column_dimensions["L"].hidden = True
        ws.column_dimensions["M"].hidden = True
        ws.column_dimensions["N"].hidden = True
        dv1 = DataValidation(type="list", formula1=f"\"{','.join(years)}\"", allow_blank=False)
        ws.add_data_validation(dv1)
        ws["B1"] = 2024
        dv1.add(ws["B1"])

        dv2 = DataValidation(type="list", formula1=f"\"{months}\"", allow_blank=False)
        ws.add_data_validation(dv2)
        ws["B2"] = months.split(',')[datetime.now().month - 1]
        dv2.add(ws["B2"])
        ws["B2"].alignment = Alignment(horizontal="right")

        ws.append([])
        ws.append(["Сеть", "Дата", "Время", "Валюта", "Сумма", "Видимое", "", "Сеть", "Валюта", "Итого"])
        ws.append(["=IF(NOT(ISBLANK(Промежуточный!A1)),Промежуточный!B1,\"\")",
                   "=IF(NOT(ISBLANK(Промежуточный!E1)),TEXT(Промежуточный!E1,\"ДД.ММ.ГГ\"),\"\")",
                   "=IF(NOT(ISBLANK(Промежуточный!E1)),TEXT(Промежуточный!E1,\"ЧЧ:ММ\"),\"\")",
                   "=IF(NOT(ISBLANK(Промежуточный!C1)),Промежуточный!C1,\"\")",
                   "=IF(NOT(ISBLANK(Промежуточный!D1)),Промежуточный!D1,\"\")",
                   "=IF(NOT(ISBLANK(Промежуточный!A1)),Промежуточный!B1,\"\")"
                   ])
        ws.insert_rows(6, records_length)
        for row in ws.iter_rows(min_row=6, max_row=records_length, max_col=6):
            find_number = int(row[0].row) - 4
            prev_number = int(row[0].row) - 1
            row[0].value = ArrayFormula(f"A{row[0].row}:A{row[0].row}",
                                        f"=IF(NOT(Промежуточный!I1),IFERROR(IF(Промежуточный!B{find_number}<>\"\",IF(NOT(IFERROR(MATCH("
                                        f"Промежуточный!B{find_number},$A$5:$A{prev_number},0),0)),"
                                        f"Промежуточный!B{find_number},\"\"),\"\"),\"\"),\"\")")
            #row[1].value = f"=IF(NOT(Промежуточный!I1),IFERROR(IF(Промежуточный!E{find_number}<>\"\",IF(OR(NOT(IFERROR(MATCH(" \
            #               f"TEXT(Промежуточный!E{find_number},\"ДД.ММ.ГГ\"),$B$5:$B{prev_number},0),0))" \
            #               f",A{row[0].row}<>\"\")," \
            #               f"TEXT(Промежуточный!E{find_number},\"ДД.ММ.ГГ\"),\"\"),\"\"),\"\"),\"\")"
            row[1].value = f"=IF(NOT(Промежуточный!I1),IFERROR(IF(Промежуточный!E{find_number}<>\"\"," \
                           f"IF(OR(TEXT(Промежуточный!E{find_number - 1},\"ДД.ММ.ГГ\")<>TEXT(" \
                           f"Промежуточный!E{find_number},\"ДД.ММ.ГГ\"),A{row[0].row}<>\"\"),TEXT(" \
                           f"Промежуточный!E{find_number},\"ДД.ММ.ГГ\"),\"\"),\"\"),\"\"),\"\")"
            row[2].value = f"=IF(NOT(Промежуточный!I1),IFERROR(IF(Промежуточный!E{find_number}<>\"\"," \
                           f"TEXT(Промежуточный!E{find_number},\"ЧЧ:ММ\"),\"\"),\"\"),\"\")"
            row[3].value = f"=IF(NOT(Промежуточный!I1),IFERROR(IF(Промежуточный!C{find_number}<>\"\"," \
                           f"TEXT(Промежуточный!C{find_number},\"ЧЧ:ММ\"),\"\"),\"\"),\"\")"
            row[4].value = f"=IF(NOT(Промежуточный!I1),IFERROR(IF(Промежуточный!D{find_number}<>\"\"," \
                           f"Промежуточный!D{find_number},\"\"),\"\"),\"\")"
            row[5].value = f"=IF(NOT(Промежуточный!I1),IFERROR(IF(Промежуточный!B{find_number}<>\"\"," \
                           f"Промежуточный!B{find_number},\"\"),\"\"),\"\")"
            for cell in row[:6]:
                cell.border = border

        max_currencies = sum([len(section_currencies[s]) for s in section_currencies]) + 4
        #if len(section_currencies) > 1:
        #    max_currencies += len(section_currencies) - 1 # пустые строки между валютами

        ws['K5'] = ArrayFormula(f"K5:L{max_currencies}",
                                f"=IFERROR(M5:N{max_currencies},\"\")")
        ws['M5'] = ArrayFormula(f"M5:N{max_currencies}",
                                f"=_xlfn.UNIQUE(Промежуточный!B1:C{records_length})")
        for row in ws.iter_rows(min_row=5, max_row=max_currencies, min_col=8, max_col=12):
            max_ind = records_length + 4
            row[0].value = f"=IF(K{row[0].row - 1}=K{row[0].row},\"\",K{row[0].row})"
            row[1].value = f"=IF(AND(L{row[1].row - 1}=L{row[1].row},H{row[1].row}=\"\"),\"\",L{row[1].row})"
            sumifs = f"SUMIFS($E${row[2].row}:$E${max_ind},$D${row[2].row}:$D${max_ind},$L{row[2].row},$F${row[2].row}:$F${max_ind},$K{row[2].row})"
            row[2].value = f"=IF({sumifs},{sumifs},\"\")"
            for cell in row[:3]:
                cell.border = border

        first_row = ws[1]
        for cell in first_row[:2]:
            cell.fill = PatternFill(patternType="solid", fgColor=Color(rgb='fff2cc'))
            cell.border = border

        second_row = ws[2]
        for cell in second_row[:2]:
            cell.fill = PatternFill(patternType="solid", fgColor=Color(rgb='fce4d6'))
            cell.border = border

        third_row = ws[4]
        for cell in third_row[:6]:
            cell.fill = PatternFill(patternType="solid", fgColor=Color(rgb='a9d08e'))
            cell.border = border
        for cell in third_row[7:12]:
            cell.fill = PatternFill(patternType="solid", fgColor=Color(rgb='8ea9db'))
            cell.border = border

        fifth_row = ws[5]
        for cell in fifth_row[:5]:
            cell.border = border
        #first_width = 15
        #last_width = 20
        #xl_recs_end = len(records) + 1
        #curr_names = list(set(r.currency.names[0] for r in records))
#
        #ws = self.wb['Сводка']
        #ws.column_dimensions["A"].width = first_width
        #ws.column_dimensions["N"].width = last_width
        #ws.append(["Валюта\\Месяц", "янв.", "февр.", "мар.", "апр.", "май", "июн.", "июл.", "авг.", "сент.", "окт.",
        #           "нояб.", "дек.", "Итого"])
        #first_row = ws[1]
        #first_row[0].fill = PatternFill(patternType="solid", fgColor=Color(rgb='ffc000'))
        #for cell in first_row[1:13]:
        #    cell.fill = PatternFill(patternType="solid", fgColor=Color(rgb='70ad47'))
        #first_row[-1].fill = PatternFill(patternType="solid", fgColor=Color(rgb='ed7d31'))
#
        #ws.insert_rows(len(curr_names) + 2, len(curr_names))
        #for row in ws.iter_rows(min_row=2, max_row=len(curr_names) + 1, max_col=14):
        #    row[0].value = curr_names[row[0].row - 2]
        #    row[0].fill = PatternFill(patternType="solid", fgColor=Color(rgb='ffff00'))
        #    for i, cell in enumerate(row[1:13]):
        #        cell.value = f'=SUMIFS(Записи!$I$2:$I${xl_recs_end},Записи!$C$2:$C${xl_recs_end},"="&' \
        #                     f'Сводка!$A{row[0].row},Записи!$H$2:$H${xl_recs_end},{i + 1})'
        #        cell.fill = PatternFill(patternType="solid", fgColor=Color(rgb='e2efda'))
        #    row[-1].value = f"=SUM({row[1].coordinate}:{row[-2].coordinate})"
        #    row[-1].fill = PatternFill(patternType="solid", fgColor=Color(rgb='f8cbad'))

