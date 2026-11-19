"""Gera data/holidays.csv: feriados nacionais de Portugal + municipais dos distritos das lojas.

Corre-se à mão. O gerador e o forecast leem só o CSV.
"""
import csv
from datetime import date
from pathlib import Path

import holidays

OUT = Path(__file__).resolve().parents[3] / "data" / "holidays.csv"
YEARS = range(2025, 2028)          # inclui 2027 para o forecast

# Feriado municipal da sede de cada distrito (mês, dia, nome)
MUNICIPAL = {
    "Porto": (6, 24, "São João"),
    "Braga": (6, 24, "São João"),
    "Aveiro": (5, 12, "Santa Joana"),
    "Coimbra": (7, 4, "Rainha Santa Isabel"),
    "Lisboa": (6, 13, "Santo António"),
    "Faro": (9, 7, "Dia da Cidade"),
}


def main():
    rows = []
    for day, name in sorted(holidays.Portugal(years=YEARS, language="pt_PT").items()):
        rows.append([day.isoformat(), "", "nacional", name])
    for district, (month, d, name) in MUNICIPAL.items():
        for year in YEARS:
            rows.append([date(year, month, d).isoformat(), district, "municipal", name])

    rows.sort()
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["day", "district", "type", "name"])   # district vazio = todo o país
        w.writerows(rows)
    print(f"{len(rows)} feriados em {OUT}")


if __name__ == "__main__":
    main()
