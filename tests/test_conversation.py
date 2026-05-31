import unittest

from app.services.conversation import choose_subject, needs_subject_clarification


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


if __name__ == "__main__":
    unittest.main()
