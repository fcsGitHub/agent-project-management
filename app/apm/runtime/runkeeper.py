"""Run keeper: bridges conversation interrupts to live agent runs.

The conversation domain calls these hooks; the runtime (I5) installs the real
implementations that pause/resume LangGraph executions.
"""
from __future__ import annotations

from typing import Callable

_interrupt_handler: Callable[[str], None] = lambda conversation_id: None
_resume_handler: Callable[[str, str | None], None] = lambda conversation_id, instruction: None


def set_interrupt_handler(fn: Callable[[str], None]) -> None:
    global _interrupt_handler
    _interrupt_handler = fn


def set_resume_handler(fn: Callable[[str, str | None], None]) -> None:
    global _resume_handler
    _resume_handler = fn


def mark_interrupted_for_conversation(conversation_id: str) -> None:
    _interrupt_handler(conversation_id)


def request_resume(conversation_id: str, instruction: str | None) -> None:
    _resume_handler(conversation_id, instruction)
