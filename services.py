import re
import unicodedata


def slugify(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return value or "restaurant"


def parse_special_text(raw_text):
    text = " ".join(raw_text.split())
    price_match = re.search(r"\$\s?\d+(?:\.\d{2})?", text)
    price = price_match.group(0).replace(" ", "") if price_match else ""

    title_text = text
    if price_match:
        title_text = text[: price_match.start()].strip(" .,-")
    title_text = re.sub(r"\b(tonight|today|starts? at .*)\b", "", title_text, flags=re.I)
    title = title_text.strip(" .,-").title() or "Today Special"

    return {
        "title": title,
        "description": text,
        "price": price,
    }
