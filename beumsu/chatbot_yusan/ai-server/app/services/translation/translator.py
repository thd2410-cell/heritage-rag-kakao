class Translator:
    def translate_evidence_answer(self, text: str, language: str) -> str:
        if language == "en":
            replacements = {
                "경복궁은": "Gyeongbokgung Palace is",
                "조선 왕조의 법궁으로": "the main royal palace of the Joseon dynasty and",
                "조선 시대 궁궐 문화와 왕실 의례를 이해하는 핵심 유산이다": "an important heritage site for understanding Joseon palace culture and royal rituals.",
                "근정전은": "Geunjeongjeon Hall is",
                "경복궁의 중심 건물로": "the central building of Gyeongbokgung Palace and",
                "국가 의례와 공식 행사가 이루어진 정전이다": "the main hall where state rites and official ceremonies were held.",
            }
            for ko, en in replacements.items():
                text = text.replace(ko, en)
        return text
