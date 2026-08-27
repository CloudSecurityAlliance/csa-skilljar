from .access import register_access_tools
from .courses import register_course_tools
from .feedback import register_feedback_tools
from .lessons import register_lesson_tools
from .questions import register_question_tools
from .quizzes import register_quiz_tools

__all__ = ["register_access_tools", "register_course_tools", "register_feedback_tools",
           "register_lesson_tools", "register_question_tools", "register_quiz_tools"]
