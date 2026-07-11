# Changelog

## Unreleased

- Go to definition and completion powered by the project index (`xbsllint index`, with the
  `--index` spelling probed as a fallback): objects, tabular sections, local types, enum values,
  methods, form components, yaml `Обработчик:` / `Тип:`. Silent when the installed linter has no
  index command.
- New setting `xbsl.navigation.enabled` (default `true`).
- Activation on workspaces containing `.xbsl` (so navigation also works in `.yaml` descriptions).

## 0.1.0

- Initial release.
- Syntax highlighting for `.xbsl` (bilingual keywords, decorators, string interpolation, generics).
- On-the-fly diagnostics via `xbsllint --stdin --format json` (on type, debounced, and on save).
- Command *XBSL: проверить весь проект* for a workspace-wide check (including cross-file rules).
- Settings: linter command / Python interpreter, data dir, language, rule select/ignore, run mode,
  debounce.
