import re


class LanguageDetector:
    def detect(self, text: str, requested: str = "auto") -> str:
        if requested != "auto":
            return requested
        if re.search(r"[\uac00-\ud7a3]", text):
            return "ko"
        if re.search(r"[\u3040-\u30ff]", text):
            return "ja"
        if re.search(r"[\u4e00-\u9fff]", text):
            return "zh"
        if re.search(r"[A-Za-z]", text):
            return "en"
        return "unknown"
