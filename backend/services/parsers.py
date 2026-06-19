import re


def parse_raw_file(text: str) -> list[tuple[float, float]]:
    data = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";", "*", "!", "%")):
            continue
        if any(
            keyword in line.lower()
            for keyword in [
                "theta",
                "angle",
                "field",
                "moment",
                "temp",
                "intensity",
                "header",
                "scan",
            ]
        ):
            continue
        values = re.split(r"[\s+,;]+", line)
        values = [v.strip() for v in values if v.strip()]
        if len(values) >= 2:
            try:
                data.append((float(values[0]), float(values[1])))
            except ValueError:
                continue
    return data
