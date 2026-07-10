"""Тир C: структурный баланс кода по токенам (без полного AST).

Модель выверена на реальном корпусе (openers == ';' во всех модулях):
- открыватель блока – ключевое слово в НИЖНЕМ регистре из набора OPENERS; заглавные формы
  (Метод, Исключение, Выбор) – это PascalCase-идентификаторы, а не ключевые слова;
- `иначе если` на одной строке – else-if (продолжение того же if, не новый блок);
  вложенный `если` в ветке `иначе` (на другой строке) – новый блок;
- `;` закрывает текущий блок; скобки () [] {} балансируются отдельным стеком.
"""

from __future__ import annotations

from collections.abc import Iterable

from xbsllint.diagnostics import Diagnostic, Severity
from xbsllint.engine import SourceFile, rule
from xbsllint.lexer import tokens

_OPENERS = {
    "METHOD", "STRUCTURE", "ENUMERATION", "EXCEPTION", "CONSTRUCTOR",
    "IF", "FOR", "WHILE", "TRY", "CASE",
}
_BLOCK_WORD = {
    "METHOD": "метод", "STRUCTURE": "структура", "ENUMERATION": "перечисление",
    "EXCEPTION": "исключение", "CONSTRUCTOR": "конструктор", "IF": "если",
    "FOR": "для", "WHILE": "пока", "TRY": "попытка", "CASE": "выбор",
}
_PAIRS = {")": "(", "]": "[", "}": "{"}
_OPEN_CH = "([{"
_CLOSE_CH = ")]}"


def _compute(source: SourceFile) -> list[Diagnostic]:
    if "struct_diags" in source.cache:
        return source.cache["struct_diags"]

    diags: list[Diagnostic] = []
    blocks: list[tuple[str, int, int]] = []  # (canonical, line, col)
    brackets: list[tuple[str, int, int]] = []  # (char, line, col)
    prev_sig: tuple[str, str, int] | None = None  # (kind, canon|value, line)

    for t in tokens(source):
        if t.kind == "COMMENT":
            continue
        if t.kind == "EOF":
            break

        if t.kind == "KEYWORD" and t.canonical in _OPENERS and t.value[:1].islower():
            is_else_if = (
                t.canonical == "IF"
                and prev_sig is not None
                and prev_sig[0] == "KEYWORD"
                and prev_sig[1] == "ELSE"
                and prev_sig[2] == t.line
            )
            if not is_else_if:
                blocks.append((t.canonical, t.line, t.col))
        elif t.kind == "OP":
            v = t.value
            if v == ";":
                if blocks:
                    blocks.pop()
                else:
                    diags.append(Diagnostic(
                        source.rel, t.line, t.col, "code/blocks", Severity.ERROR,
                        "Лишний ';' – нет открытого блока для закрытия.",
                    ))
            elif v in _OPEN_CH:
                brackets.append((v, t.line, t.col))
            elif v in _CLOSE_CH:
                if brackets and brackets[-1][0] == _PAIRS[v]:
                    brackets.pop()
                elif brackets:
                    exp = {"(": ")", "[": "]", "{": "}"}[brackets[-1][0]]
                    diags.append(Diagnostic(
                        source.rel, t.line, t.col, "code/brackets", Severity.ERROR,
                        f"Непарная скобка: ожидалась '{exp}', встречена '{v}'.",
                    ))
                    brackets.pop()
                else:
                    diags.append(Diagnostic(
                        source.rel, t.line, t.col, "code/brackets", Severity.ERROR,
                        f"Непарная закрывающая скобка '{v}'.",
                    ))

        prev_sig = (t.kind, t.canonical if t.kind == "KEYWORD" else t.value, t.line)

    for ch, line, col in brackets:
        diags.append(Diagnostic(
            source.rel, line, col, "code/brackets", Severity.ERROR,
            f"Не закрыта скобка '{ch}'.",
        ))
    for canon, line, col in blocks:
        diags.append(Diagnostic(
            source.rel, line, col, "code/blocks", Severity.ERROR,
            f"Не закрыт блок '{_BLOCK_WORD.get(canon, canon)}' – ожидается ';'.",
        ))

    source.cache["struct_diags"] = diags
    return diags


@rule("code/brackets", "Дисбаланс скобок () [] {}", "C", severity=Severity.ERROR)
def brackets_balance(source: SourceFile) -> Iterable[Diagnostic]:
    if source.kind != "xbsl":
        return []
    return [d for d in _compute(source) if d.rule_id == "code/brackets"]


@rule("code/blocks", "Дисбаланс блоков и ';'", "C", severity=Severity.ERROR)
def blocks_balance(source: SourceFile) -> Iterable[Diagnostic]:
    if source.kind != "xbsl":
        return []
    return [d for d in _compute(source) if d.rule_id == "code/blocks"]


def _new_frame(line: int | None) -> dict:
    # and_or – позиция последнего 'и'/'или' на этом уровне глубины (до '?'),
    # pending – позиция '?', встреченного после and_or (ждём ':' для подтверждения тернарного)
    return {"and_or": None, "pending": None, "line": line}


@rule(
    "code/ternary-and-or",
    "Составное условие тернарного оператора без скобок",
    "C",
    severity=Severity.ERROR,
)
def ternary_compound_condition(source: SourceFile) -> Iterable[Diagnostic]:
    """Тернарный '?:' связывает сильнее 'и'/'или': 'А и Б ? X : Y' == 'А и (Б ? X : Y)'.

    Компилятор Элемента падает с "Incompatible types of logical operator operands" /
    "Булево cannot be assigned to ...". Ловим по токенам: на одном уровне скобочной
    глубины встречаются 'и'/'или', затем '?', затем ':' – условие не взято в скобки.
    Правильно: '((А и Б) ? X : Y)' – там 'и' лежит глубже и последовательность не совпадает.
    """
    if source.kind != "xbsl":
        return []
    diags: list[Diagnostic] = []
    frames: list[dict] = [_new_frame(None)]

    for t in tokens(source):
        if t.kind == "COMMENT":
            continue
        if t.kind == "EOF":
            break
        top = frames[-1]
        # Вне скобок выражение живёт в одной строке – новая строка сбрасывает состояние.
        if len(frames) == 1 and top["line"] != t.line:
            frames[0] = top = _new_frame(t.line)

        if t.kind == "KEYWORD" and t.canonical in ("AND", "OR"):
            if top["pending"] is None:
                top["and_or"] = (t.line, t.col, t.value)
        elif t.kind == "OP":
            v = t.value
            if v in _OPEN_CH:
                frames.append(_new_frame(t.line))
            elif v in _CLOSE_CH:
                if len(frames) > 1:
                    frames.pop()
            elif v == "?":
                if top["and_or"] is not None and top["pending"] is None:
                    top["pending"] = (t.line, t.col)
            elif v == ":":
                if top["pending"] is not None:
                    line, col = top["pending"]
                    _, _, word = top["and_or"]
                    diags.append(Diagnostic(
                        source.rel, line, col, "code/ternary-and-or", Severity.ERROR,
                        f"Условие тернарного оператора с '{word}' без скобок: "
                        f"'А {word} Б ? X : Y' парсится как 'А {word} (Б ? X : Y)'. "
                        f"Взять условие в скобки: '((А {word} Б) ? X : Y)'.",
                    ))
                frames[-1] = _new_frame(top["line"])
            elif v in (",", ";", "="):
                frames[-1] = _new_frame(top["line"])

    return diags
