import unittest

from app.services.answer_builder import wants_easy_explanation, wants_importance, wants_more_detail, wants_travel_visit
from app.services.conversation import choose_subject, is_contextual_question, needs_subject_clarification


class ConversationTests(unittest.TestCase):
    def test_current_topic_is_kept_without_new_subject(self):
        subject, mode = choose_subject("건축적으로 설명해줘", ["서울 숭례문", "흥인지문"])
        self.assertEqual(subject, "서울 숭례문")
        self.assertEqual(mode, "current_topic")

    def test_previous_topic_can_be_recalled(self):
        subject, mode = choose_subject("아까 그거 화재 얘기 다시 해줘", ["흥인지문", "서울 숭례문"])
        self.assertEqual(subject, "서울 숭례문")
        self.assertEqual(mode, "previous_topic")

    def test_root_topic_can_be_recalled(self):
        subject, mode = choose_subject("처음 말한 거 위치 알려줘", ["흥인지문", "경복궁", "서울 숭례문"])
        self.assertEqual(subject, "서울 숭례문")
        self.assertEqual(mode, "root_topic")

    def test_contextual_question_without_subject_needs_clarification(self):
        self.assertTrue(needs_subject_clarification("근처에 뭐 있어?"))

    def test_compact_detail_followups_are_contextual(self):
        examples = [
            "더자세하게 알려줘",
            "상세히 알려줘",
            "좀 더 풀어서 설명해줘",
            "길게 설명해줘",
            "구체적인 예시도 알려줘",
            "왜 중요한데?",
            "의미가 뭐야?",
        ]
        for example in examples:
            with self.subTest(example=example):
                self.assertTrue(is_contextual_question(example))

    def test_detail_answer_variants_trigger_deep_answer(self):
        examples = [
            "더자세하게 알려줘",
            "상세히 알려줘",
            "좀 더 풀어서 설명해줘",
            "길게 설명해줘",
            "구체적인 예시도 알려줘",
        ]
        for example in examples:
            with self.subTest(example=example):
                self.assertTrue(wants_more_detail(example))

    def test_importance_variants_trigger_importance_answer(self):
        for example in ["왜 중요한데?", "의미가 뭐야?", "뭐가 특별해?"]:
            with self.subTest(example=example):
                self.assertTrue(wants_importance(example))

    def test_easy_variants_trigger_easy_answer(self):
        for example in ["쉽게 다시 설명해줘", "초등학생도 이해하게 설명해줘", "쉬운 말로 풀어서 말해줘"]:
            with self.subTest(example=example):
                self.assertTrue(wants_easy_explanation(example))

    def test_travel_variants_trigger_travel_answer(self):
        for example in ["근처에 뭐 있어?", "위치 알려줘", "답사 코스 알려줘"]:
            with self.subTest(example=example):
                self.assertTrue(wants_travel_visit(example))


if __name__ == "__main__":
    unittest.main()
