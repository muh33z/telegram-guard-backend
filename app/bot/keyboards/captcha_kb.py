import random
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def build_captcha_keyboard(user_id: int, correct_answer: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    wrong_answers = set()
    while len(wrong_answers) < 3:
        offset = random.choice([-3, -2, -1, 1, 2, 3])
        val = max(1, correct_answer + offset)
        if val != correct_answer:
            wrong_answers.add(val)

    all_options = list(wrong_answers) + [correct_answer]
    random.shuffle(all_options)

    for option in all_options:
        is_correct = "1" if option == correct_answer else "0"
        builder.button(
            text=str(option),
            callback_data=f"captcha:{user_id}:{is_correct}"
        )

    builder.adjust(2, 2)
    return builder.as_markup()