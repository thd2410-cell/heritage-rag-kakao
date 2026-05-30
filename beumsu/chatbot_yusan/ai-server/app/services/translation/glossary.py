import re
import unicodedata


GLOSSARY = {
    "경복궁": {"ko": "경복궁", "en": "Gyeongbokgung Palace", "zh": "景福宫", "ja": "景福宮"},
    "근정전": {"ko": "근정전", "en": "Geunjeongjeon Hall", "zh": "勤政殿", "ja": "勤政殿"},
    "단청": {"ko": "단청", "en": "dancheong", "zh": "丹青", "ja": "丹靑"},
}


def normalize_key(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().strip()
    text = re.sub(r"[\s\-_.,!?()'\"·]+", "", text)
    return text
