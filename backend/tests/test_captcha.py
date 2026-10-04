"""Unit tests for the human-verification (captcha) solver.

The prompts below are copied verbatim from real check-in bots, including the
three screenshots in the issue report.
"""

from __future__ import annotations

from app.telegram.captcha import looks_like_captcha, solve_question  # noqa: E402

ARITHMETIC_PROMPT = "🤖 人机验证：请计算 11 + 15 = ？\n请选择正确答案继续操作："


def _label(question, labels):
    solution = solve_question(question, labels)
    return solution.label if solution else None


# --------------------------------------------------------------------------- #
# arithmetic — the case in the screenshots
# --------------------------------------------------------------------------- #
def test_screenshot_prompts():
    assert _label(ARITHMETIC_PROMPT, ["26", "27", "28", "25"]) == "26"
    assert _label("请计算 6 + 3 = ？\n请选择正确答案继续操作：", ["10", "4", "14", "9"]) == "9"
    assert _label("请计算 16 + 2 = ？\n请选择正确答案继续操作：", ["18", "20", "13", "22"]) == "18"


def test_solution_carries_context():
    solution = solve_question(ARITHMETIC_PROMPT, ["26", "27", "28", "25"])
    assert solution is not None
    assert solution.strategy == "arithmetic"
    assert solution.index == 0
    assert solution.answer == "26"
    assert solution.summary == "11 + 15 = 26"


def test_operator_variants():
    assert _label("请计算 3 × 7 = ?", ["21", "24", "10", "18"]) == "21"
    assert _label("请计算 100 ÷ 4 = ?", ["24", "25", "26", "20"]) == "25"
    assert _label("请计算 12 - 5 = ?", ["6", "7", "8", "9"]) == "7"
    assert _label("请计算 11 加 15 = ?", ["26", "27", "28", "25"]) == "26"
    assert _label("请计算 9 乘 3 = ?", ["27", "18", "12", "6"]) == "27"
    assert _label("请计算 20 除以 5 = ?", ["4", "5", "6", "8"]) == "4"


def test_chinese_numerals():
    assert _label("请计算 六 + 三 = ？", ["8", "9", "10", "11"]) == "9"
    assert _label("请计算 二十六 - 6 = ？", ["18", "20", "22", "24"]) == "20"


def test_fullwidth_characters():
    assert _label("请计算　１１ ＋ １５ ＝ ？", ["26", "27", "28", "25"]) == "26"


def test_multi_operator_expression():
    assert _label("请计算 2 + 3 × 4 = ?", ["14", "20", "24", "9"]) == "14"
    assert _label("请计算 (2 + 3) × 4 = ?", ["20", "14", "24", "9"]) == "20"


def test_decimal_result():
    assert _label("请计算 10 / 4 = ?", ["2.5", "2", "3", "4"]) == "2.5"


def test_option_labels_with_suffixes():
    assert _label(ARITHMETIC_PROMPT, ["26 分", "27 分", "28 分", "25 分"]) == "26 分"


def test_chinese_numeral_options():
    assert _label("请计算 11 + 15 = ?", ["二十五", "二十六", "二十七", "二十八"]) == "二十六"


# --------------------------------------------------------------------------- #
# negatives — must never click something it is not sure about
# --------------------------------------------------------------------------- #
def test_no_expression_returns_none():
    assert solve_question("请选择正确答案继续操作：", ["26", "27", "28", "25"]) is None
    assert solve_question("欢迎使用签到机器人", ["签到", "查询", "帮助"]) is None


def test_answer_absent_from_options_returns_none():
    assert solve_question(ARITHMETIC_PROMPT, ["30", "31", "32", "33"]) is None


def test_plain_menu_is_not_clicked():
    """A normal bot menu containing a number must not be auto-clicked."""
    assert solve_question("请选择要办理的业务", ["1. 签到", "2. 查询"]) is None
    assert solve_question("今日已签到 3 天，请选择操作", ["继续", "退出"]) is None


def test_division_by_zero_returns_none():
    assert solve_question("请计算 5 / 0 = ?", ["0", "5", "1", "∞"]) is None


def test_empty_inputs():
    assert solve_question("", ["1"]) is None
    assert solve_question(None, ["1"]) is None
    assert solve_question("请计算 1 + 1 = ?", []) is None


def test_expression_is_not_evaluated_as_code():
    """The parser must never run arbitrary code from a remote bot."""
    payload = "请计算 1 + 1 = ?  (__import__('os').system('echo pwned'))"
    solution = solve_question(payload, ["2", "3"])
    assert solution is not None
    assert solution.answer == "2"
    assert solution.label == "2"


# --------------------------------------------------------------------------- #
# other verification flavours
# --------------------------------------------------------------------------- #
def test_largest_smallest_prompts():
    assert _label("人机验证：请选择最大的数字", ["7", "19", "4", "12"]) == "19"
    assert _label("防机器人验证：请选择最小的数字", ["7", "19", "4", "12"]) == "4"


def test_literal_prompt():
    question = "人机验证：请点击「确认」继续"
    assert _label(question, ["确认", "取消"]) == "确认"


def test_keyword_gate():
    assert looks_like_captcha(ARITHMETIC_PROMPT) is True
    assert looks_like_captcha("Please verify you are human") is True
    assert looks_like_captcha("今日签到成功") is False
