"""Human-verification (captcha) prompt solver.

Bots that guard daily check-ins often answer a command with an inline keyboard
like::

    人机验证：请计算 11 + 15 = ？
    请选择正确答案继续操作：
    [26] [27] [28] [25]

This module holds the pure, side-effect-free half of the solution: given the
question text and the button labels, decide which button to press. It never
talks to Telegram, which keeps it trivially unit-testable and safe to import
from anywhere.

Three strategies are attempted, in order:

1. ``arithmetic`` — extract an expression such as ``11 + 15`` and match the
   option whose value equals the result. Self-validating: it only fires when an
   explicit expression *and* a numerically matching button both exist.
2. ``largest`` / ``smallest`` — "please pick the biggest number" style prompts.
3. ``literal`` — the question quotes one of the options (e.g. 请点击「确认」).

Strategies 2 and 3 only run when the text carries a verification keyword, so a
normal bot menu can never be clicked by accident.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = ["CaptchaSolution", "looks_like_captcha", "solve_question"]


# --------------------------------------------------------------------------- #
# normalisation helpers
# --------------------------------------------------------------------------- #
# Full-width ASCII (！…～) maps onto its half-width counterpart; the extra
# entries cover the symbols Telegram bots actually put in arithmetic prompts.
_TRANSLATE = {code: code - 0xFEE0 for code in range(0xFF01, 0xFF5F)}
_TRANSLATE.update(
    {
        ord("\u3000"): ord(" "),  # ideographic space
        ord("\u200b"): None,  # zero-width space
        ord("\u200e"): None,  # LRM
        ord("\u200f"): None,  # RLM
        ord("\u00d7"): ord("*"),  # ×
        ord("\u2715"): ord("*"),  # ✕
        ord("\u2716"): ord("*"),  # ✖
        ord("\u2219"): ord("*"),  # ∙
        ord("\u00f7"): ord("/"),  # ÷
        ord("\u2212"): ord("-"),  # −
        ord("\u2013"): ord("-"),  # –
        ord("\u2014"): ord("-"),  # —
        ord("\u2018"): ord("'"),
        ord("\u2019"): ord("'"),
        ord("\u201c"): ord('"'),
        ord("\u201d"): ord('"'),
    }
)

_CN_OPERATORS = {
    "加上": "+",
    "加": "+",
    "减去": "-",
    "减掉": "-",
    "减": "-",
    "乘以": "*",
    "乘上": "*",
    "乘": "*",
    "除以": "/",
    "除": "/",
}

_NUMBER_TOKEN = r"[0-9零一二三四五六七八九十百千万两]{1,8}"
_OPERATOR_TOKEN = "(?:" + "|".join(re.escape(word) for word in _CN_OPERATORS) + r"|[-+*/])"
_TERM_TOKEN = rf"\(*\s*{_NUMBER_TOKEN}\s*\)*"
_EXPRESSION_RE = re.compile(rf"{_TERM_TOKEN}(?:\s*{_OPERATOR_TOKEN}\s*{_TERM_TOKEN})+")
_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?|[零一二三四五六七八九十百千万两]+|[-+*/()]")

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}

#: Words that mark a message as a verification challenge.
_CAPTCHA_KEYWORDS = (
    "验证",
    "人机",
    "防机器人",
    "请计算",
    "请回答",
    "请选择正确",
    "正确答案",
    "计算结果",
    "captcha",
    "verify",
    "human",
    "robot",
)

#: Characters that may surround a number in a button label without changing its
#: meaning ("26", "26 分", "26。").
_OPTION_NOISE = set(" \t.。、,，!！?？:：;；'\"分个次秒%％/／")


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    return str(text).translate(_TRANSLATE).strip()


def _chinese_to_int(text: str) -> int | None:
    """Convert a Chinese numeral (≤ 9999) to an int, or return ``None``."""
    if not text:
        return None
    total = section = number = 0
    for char in text:
        if char in _CN_DIGITS:
            number = _CN_DIGITS[char]
        elif char in _CN_UNITS:
            unit = _CN_UNITS[char]
            if number == 0:
                number = 1  # 十五 -> 15
            section += number * unit
            number = 0
        elif char == "万":
            section = (section + number) * 10000
            total += section
            section = number = 0
        else:
            return None
    return total + section + number


def _format_number(value: float) -> str:
    """Render a computed result without a trailing ``.0``."""
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.4f}".rstrip("0").rstrip(".") or "0"


def _tokenize(expression: str) -> list[tuple[str, float | str]] | None:
    tokens: list[tuple[str, float | str]] = []
    for piece in _TOKEN_RE.findall(expression):
        if piece[0].isdigit():
            tokens.append(("num", float(piece)))
        elif piece in "+-*/()":
            tokens.append(("op", piece))
        else:
            value = _chinese_to_int(piece)
            if value is None:
                return None
            tokens.append(("num", float(value)))
    return tokens or None


def _evaluate(tokens: list[tuple[str, float | str]]) -> float | None:
    """Evaluate a token stream with a tiny recursive-descent parser.

    Deliberately avoids :func:`eval` — the input comes from a remote bot.
    """
    index = 0

    def parse_factor() -> float | None:
        nonlocal index
        if index >= len(tokens):
            return None
        kind, value = tokens[index]
        if kind == "op" and value in "+-":
            index += 1
            inner = parse_factor()
            if inner is None:
                return None
            return -inner if value == "-" else inner
        if kind == "num":
            index += 1
            return float(value)
        if kind == "op" and value == "(":
            index += 1
            inner = parse_expression()
            if inner is None or index >= len(tokens) or tokens[index] != ("op", ")"):
                return None
            index += 1
            return inner
        return None

    def parse_term() -> float | None:
        nonlocal index
        left = parse_factor()
        if left is None:
            return None
        while index < len(tokens):
            kind, value = tokens[index]
            if kind != "op" or value not in "*/":
                break
            index += 1
            right = parse_factor()
            if right is None:
                return None
            if value == "*":
                left *= right
            else:
                if abs(right) < 1e-12:
                    return None
                left /= right
        return left

    def parse_expression() -> float | None:
        nonlocal index
        left = parse_term()
        if left is None:
            return None
        while index < len(tokens):
            kind, value = tokens[index]
            if kind != "op" or value not in "+-":
                break
            index += 1
            right = parse_term()
            if right is None:
                return None
            left = left + right if value == "+" else left - right
        return left

    result = parse_expression()
    if result is None or index != len(tokens):
        return None
    return result


def _extract_expression(question: str) -> tuple[str, float] | None:
    """Return ``(raw_expression, value)`` for the longest expression found."""
    matches = [match.group(0) for match in _EXPRESSION_RE.finditer(question)]
    if not matches:
        return None
    for raw in sorted(matches, key=len, reverse=True):
        expanded = raw
        for word, symbol in _CN_OPERATORS.items():
            expanded = expanded.replace(word, symbol)
        tokens = _tokenize(expanded)
        if tokens is None:
            continue
        value = _evaluate(tokens)
        if value is None:
            continue
        return raw.strip(), value
    return None


def _option_value(label: str) -> float | None:
    """Read a button label as a number, or ``None`` if it is not one."""
    normalized = _normalize(label)
    if not normalized:
        return None

    if re.fullmatch(r"[零一二三四五六七八九十百千万两]+", normalized):
        value = _chinese_to_int(normalized)
        return float(value) if value is not None else None

    match = re.search(r"-?\d+(?:\.\d+)?", normalized)
    if match is None:
        return None
    remainder = normalized.replace(match.group(0), "", 1)
    if remainder and not set(remainder) <= _OPTION_NOISE:
        return None
    return float(match.group(0))


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CaptchaSolution:
    """The button that should be pressed, plus why."""

    index: int
    label: str
    answer: str
    strategy: str
    question: str

    @property
    def summary(self) -> str:
        if self.strategy == "arithmetic":
            return f"{self.question} = {self.answer}"
        return f"{self.question} → {self.label}"


def looks_like_captcha(text: str | None) -> bool:
    """Heuristic keyword gate for prompts that are not self-validating."""
    normalized = _normalize(text).lower()
    return any(keyword in normalized for keyword in _CAPTCHA_KEYWORDS)


def solve_question(question: str | None, labels: Sequence[str]) -> CaptchaSolution | None:
    """Pick the button that answers a verification prompt.

    Returns ``None`` when the prompt cannot be answered with confidence, in
    which case the caller must leave the message alone.
    """
    if not question or not labels:
        return None

    normalized_question = _normalize(question)
    if not normalized_question:
        return None

    options = [(index, label, _option_value(label)) for index, label in enumerate(labels)]
    numeric = [(index, label, value) for index, label, value in options if value is not None]

    # 1) arithmetic — self-validating, so it runs even without keywords
    expression = _extract_expression(normalized_question)
    if expression is not None:
        raw, value = expression
        for index, label, number in numeric:
            if abs(number - value) < 1e-6:
                return CaptchaSolution(index, label, _format_number(value), "arithmetic", raw)

    if not looks_like_captcha(normalized_question):
        return None

    # 2) largest / smallest of the offered numbers
    if numeric:
        if re.search(r"最大|最多|最高|最长|最贵|largest|greatest|\bmax\b", normalized_question, re.I):
            index, label, value = max(numeric, key=lambda item: item[2])
            return CaptchaSolution(index, label, _format_number(value), "largest", normalized_question)
        if re.search(r"最小|最少|最低|最短|最便宜|smallest|least|\bmin\b", normalized_question, re.I):
            index, label, value = min(numeric, key=lambda item: item[2])
            return CaptchaSolution(index, label, _format_number(value), "smallest", normalized_question)

    # 3) the question quotes one of the options verbatim
    quoted = [
        (index, label)
        for index, label in enumerate(labels)
        if len(_normalize(label)) >= 2 and _normalize(label) in normalized_question
    ]
    if quoted:
        index, label = max(quoted, key=lambda item: len(_normalize(item[1])))
        return CaptchaSolution(index, label, _normalize(label), "literal", normalized_question)

    return None
