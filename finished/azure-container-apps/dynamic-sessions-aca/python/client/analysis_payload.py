import csv
import json
from pathlib import Path

data_path = Path("/mnt/data/operational-data.csv")
output_path = Path("/mnt/data/trend.svg")

with data_path.open(newline="", encoding="utf-8") as source:
    rows = list(csv.DictReader(source))

values = [int(row["requests"]) for row in rows]
summary = {
    "months": len(rows),
    "total_requests": sum(values),
    "average_requests": sum(values) / len(values),
    "peak_month": rows[values.index(max(values))]["month"],
    "peak_requests": max(values),
}

bars = []
for index, row in enumerate(rows):
    height = int(row["requests"])
    x = 30 + index * 80
    y = 430 - height
    bars.append(
        f'<rect x="{x}" y="{y}" width="50" height="{height}" '
        f'fill="#0078d4"><title>{row["month"]}: '
        f'{row["requests"]}</title></rect>'
    )

svg = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="360" height="460">'
    '<rect width="100%" height="100%" fill="white"/>'
    '<text x="20" y="20">Monthly document requests</text>'
    + "".join(bars)
    + "</svg>"
)
output_path.write_text(svg, encoding="utf-8")

print(json.dumps(summary))
