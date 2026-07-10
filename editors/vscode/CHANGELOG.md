# Changelog

## 0.1.0

- Initial release.
- Syntax highlighting for `.xbsl` (bilingual keywords, decorators, string interpolation, generics).
- On-the-fly diagnostics via `xbsllint --stdin --format json` (on type, debounced, and on save).
- Command *XBSL: проверить весь проект* for a workspace-wide check (including cross-file rules).
- Settings: linter command / Python interpreter, data dir, language, rule select/ignore, run mode,
  debounce.
