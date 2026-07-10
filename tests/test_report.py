"""Форма машиночитаемого отчёта (report.report) – без зависимости от данных Элемента."""

import json

from xbsllint import report
from xbsllint.diagnostics import Diagnostic, Severity


def _d(line, col, rule, sev):
    return Diagnostic(path="X.xbsl", line=line, col=col, rule_id=rule, severity=sev, message="m")


def test_report_shape_counts_and_order():
    diags = [
        _d(3, 1, "code/brackets", Severity.ERROR),
        _d(1, 5, "typography/curly-quotes", Severity.WARNING),
        _d(1, 2, "whitespace/trailing", Severity.WARNING),
    ]
    payload = report.report(diags, 1)

    assert set(payload) == {"diagnostics", "summary"}
    assert payload["summary"] == {"files": 1, "diagnostics": 3, "errors": 1, "warnings": 2}

    # Отсортировано по (path, line, col, rule)
    positions = [(d["line"], d["col"]) for d in payload["diagnostics"]]
    assert positions == sorted(positions)

    # Поля одного замечания
    first = payload["diagnostics"][0]
    assert set(first) == {"path", "line", "col", "rule", "severity", "message"}
    assert first["severity"] in {"error", "warning", "info"}

    # Сериализуется в JSON без потерь
    assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload


def test_report_empty():
    payload = report.report([], 0)
    assert payload == {
        "diagnostics": [],
        "summary": {"files": 0, "diagnostics": 0, "errors": 0, "warnings": 0},
    }
