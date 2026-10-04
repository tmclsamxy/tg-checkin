"""Integration tests for the captcha hook inside the executor.

Telegram is replaced by tiny fakes so the button-picking glue (index lookup,
click payload, multi-round cursor) is covered without a network connection.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.telegram.executor import _solve_captchas  # noqa: E402

PROMPT = "🤖 人机验证：请计算 11 + 15 = ？\n请选择正确答案继续操作："
PROMPT_2 = "请计算 16 + 2 = ？\n请选择正确答案继续操作："


class FakeButton:
    def __init__(self, text: str, data: bytes | None = None) -> None:
        self.text = text
        self.data = data


class FakeRow:
    def __init__(self, buttons) -> None:
        self.buttons = list(buttons)


class FakeMarkup:
    def __init__(self, buttons) -> None:
        self.rows = [FakeRow(buttons)]


class FakeMessage:
    def __init__(self, message_id: int, text: str, buttons=(), follow_up=None) -> None:
        self.id = message_id
        self.message = text
        self.reply_markup = FakeMarkup(buttons) if buttons else None
        self.clicked: dict | None = None
        #: invoked right after a successful click, mimicking the bot replying
        self._follow_up = follow_up

    async def click(self, **kwargs) -> None:
        self.clicked = kwargs
        if self._follow_up is not None:
            self._follow_up()


class FakeClient:
    def __init__(self, messages) -> None:
        self.messages = list(messages)

    def iter_messages(self, entity, min_id: int = 0, limit: int | None = None):
        async def generate():
            for message in sorted(self.messages, key=lambda item: -item.id):
                if message.id > min_id:
                    yield message

        return generate()


def _cfg(**overrides):
    base = {"captcha_enabled": True, "captcha_max_rounds": 2, "captcha_wait_seconds": 1}
    base.update(overrides)
    return SimpleNamespace(**base)


def _solve(client, baseline=100, **cfg):
    return asyncio.run(_solve_captchas(client, "entity", baseline, _cfg(**cfg)))


def _numeric_buttons(*values: str):
    return [FakeButton(value, f"cb:{value}".encode()) for value in values]


def test_clicks_the_matching_button():
    message = FakeMessage(101, PROMPT, _numeric_buttons("26", "27", "28", "25"))
    solved = _solve(FakeClient([message]))

    assert [item.label for item in solved] == ["26"]
    assert message.clicked == {"data": b"cb:26"}


def test_text_only_buttons_are_clicked_by_text():
    buttons = [FakeButton("26"), FakeButton("27")]
    message = FakeMessage(101, PROMPT, buttons)
    solved = _solve(FakeClient([message]))

    assert [item.label for item in solved] == ["26"]
    assert message.clicked == {"text": "26"}


def test_solves_multiple_rounds():
    """The bot answers the first challenge with a second one."""
    client = FakeClient([])
    second = FakeMessage(102, PROMPT_2, _numeric_buttons("18", "20", "13", "22"))
    first = FakeMessage(101, PROMPT, _numeric_buttons("26", "27", "28", "25"), follow_up=lambda: client.messages.append(second))
    client.messages.append(first)

    solved = _solve(client)

    assert [item.label for item in solved] == ["26", "18"]
    assert first.clicked == {"data": b"cb:26"}
    assert second.clicked == {"data": b"cb:18"}


def test_stops_after_max_rounds():
    client = FakeClient([])
    second = FakeMessage(102, PROMPT_2, _numeric_buttons("18", "20", "13", "22"))
    first = FakeMessage(101, PROMPT, _numeric_buttons("26", "27", "28", "25"), follow_up=lambda: client.messages.append(second))
    client.messages.append(first)

    solved = _solve(client, captcha_max_rounds=1)

    assert [item.label for item in solved] == ["26"]
    assert second.clicked is None


def test_picks_the_newest_matching_prompt():
    older = FakeMessage(101, PROMPT, _numeric_buttons("26", "27", "28", "25"))
    newer = FakeMessage(103, PROMPT_2, _numeric_buttons("18", "20", "13", "22"))
    solved = _solve(FakeClient([older, newer]))

    assert [item.label for item in solved] == ["18"]
    assert older.clicked is None


def test_ignores_messages_before_the_baseline():
    message = FakeMessage(50, PROMPT, _numeric_buttons("26", "27", "28", "25"))
    assert _solve(FakeClient([message]), baseline=100) == []
    assert message.clicked is None


def test_ignores_unsolvable_and_buttonless_messages():
    menu = FakeMessage(101, "请选择要办理的业务", _numeric_buttons("26", "27"))
    plain = FakeMessage(102, "今日签到成功，已连续 3 天")
    assert _solve(FakeClient([menu, plain])) == []
    assert menu.clicked is None


def test_disabled_by_max_rounds_zero():
    message = FakeMessage(101, PROMPT, _numeric_buttons("26", "27"))
    assert _solve(FakeClient([message]), captcha_max_rounds=0) == []
    assert message.clicked is None
