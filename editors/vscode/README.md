# XBSL for VS Code

**English** · [Русский](https://github.com/keyfire/xbsl-lint/blob/main/editors/vscode/README.ru.md)

Syntax highlighting and on-the-fly linting for **1C:Element** sources (`.xbsl`), powered by the
[xbsllint](https://github.com/keyfire/xbsl-lint) linter.

![XBSL: syntax highlighting and an inline lint diagnostic from xbsllint](https://raw.githubusercontent.com/keyfire/xbsl-lint/main/editors/vscode/images/demo.png)

## Features

- **Syntax highlighting** for `.xbsl`: keywords (both Russian and English forms), declarations,
  operators, `@`-decorators, numbers, comments, and strings with `%name` / `${...}` interpolation.
- **Live diagnostics** as you type (debounced) and on save – brackets/blocks balance, unused
  locals, typography, code-style conventions, and everything else the linter reports. Squiggles
  carry the rule id (e.g. `code/brackets`) and severity.
- **Workspace diagnostics** – saving any `.xbsl`/`.yaml` file runs the linter over the whole
  workspace folder in the background, so project-scope rules (`code/unknown-type`,
  `yaml/unknown-type`, `Ид` uniqueness) show up right in the editor, across all files.
  Controlled by `xbsl.workspaceLint` (on by default).
- **Whole-project check** – the command *XBSL: проверить весь проект* runs the same
  workspace-wide check on demand.
- **Go to definition and completion across the project** – powered by a project index built by
  the linter (`xbsllint --index`). See [Navigation and completion](#navigation-and-completion).
- **Quick Fix for mechanical findings** – a lightbulb on a fixable diagnostic (trailing
  whitespace, typography characters) applies the exact edit the linter reports; a *fix all*
  source action (`source.fixAll.xbsl`) fixes the whole file and can run on save via
  `editor.codeActionsOnSave`. Needs `xbsllint` ≥ 0.7.1. See [Quick Fix](#quick-fix).

`.yaml` element descriptions keep their built-in YAML highlighting.

## Requirements

The extension is a thin client over the `xbsllint` CLI – it does not bundle a checker. You need:

1. **Python 3.10+** and the linter: `pip install xbsllint`.
2. **Element language data** – generated once from your 1C:Element distribution, see
   [step 1 of the linter README](https://github.com/keyfire/xbsl-lint#step-1-generate-the-language-data).
   Without it most rules cannot run; the extension surfaces the linter's error once.

By default the extension calls `xbsllint` from `PATH`. Point it elsewhere with
`xbsl.linter.command` (an executable) or `xbsl.linter.pythonPath` (an interpreter – the linter is
then invoked as `<python> -m xbsllint`).

## Navigation and completion

The extension asks the linter for a project index once on activation and rebuilds it (debounced,
one process at a time) whenever a `.xbsl`/`.yaml` file is saved. The index command is probed as
`xbsllint index <root>` first, then `xbsllint --index <root>` as a fallback. If the installed
linter does not support the index yet, navigation silently stays off – details go to the *XBSL*
output channel, no popups.

**Go to definition** (F12 / Ctrl+Click), in `.xbsl` and `.yaml`:

- a project object name (bare, or the root of a dotted chain) → its `.yaml`;
- `Объект.ЛокальныйТип` → the type declaration; `Объект.ТабличнаяЧасть` → the section in the
  object's yaml; `Перечисление.Значение` → the value line;
- `Модуль.Метод` (including manager modules named after the object), and a bare method name
  inside its own module → the method;
- `Компоненты.Имя` → the component node in the current form's yaml; `Компоненты.Имя.Метод` → the
  method of that module;
- in yaml, the value of `Обработчик: Имя` → the handler in the paired `.xbsl`.

**Completion** (triggered by `.` and `:`):

- after `Объект.` – the type family (`Ссылка`, `Объект`, ...), tabular sections, local types and
  manager-module methods; for an enum – its values;
- after `Компоненты.` – components of the current form; after `Компоненты.X.` – methods of
  module `X`;
- in yaml after `Тип:` – project object names (the object kind is shown as the detail).

Known limits – by design, the index knows declarations, not types: no completion after variables
or arbitrary expressions, no type inference for dotted chains deeper than one level, no rename.
When the context is ambiguous the providers return nothing rather than guessing.

## Quick Fix

Findings the linter can repair mechanically carry a fix; the extension turns it into a Quick Fix:

- A **lightbulb on the diagnostic** (`Ctrl+.`) – *Исправить: `<rule>`* – applies the exact edit:
  trailing whitespace removed, em dash → en dash, `…` → `...`, curly quotes → straight.
- A **fix-all source action** – *Исправить все (xbsllint)* – repairs every fixable finding in the
  file in one edit. Run it on save by adding to your settings:

  ```json
  "editor.codeActionsOnSave": { "source.fixAll.xbsl": "explicit" }
  ```

Fixes need a linter that emits them in its JSON (`xbsllint` ≥ 0.7.1). Only unambiguous edits are
offered, and only against the exact text they were computed on – a version-stamped snapshot guards
against applying an offset to text that changed since the last lint. Whole-file fixes (mixed
newlines) are left to `xbsllint --fix` on the command line.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `xbsl.linter.run` | `onType` | When to lint: `onType` (debounced) / `onSave` / `off`. |
| `xbsl.linter.command` | `xbsllint` | Linter executable (PATH or absolute path). |
| `xbsl.linter.pythonPath` | – | Python interpreter; when set, runs `<python> -m xbsllint`. |
| `xbsl.linter.dataDir` | – | Element data root (folder with `index.json`); empty = auto-resolved. |
| `xbsl.linter.lang` | auto | Diagnostic language: ` ` (auto) / `ru` / `en`. |
| `xbsl.linter.select` | – | Only these rules (ids, groups, or tier letters `A`–`D`). |
| `xbsl.linter.ignore` | – | Exclude these rules. |
| `xbsl.rules` | `{}` | Per-rule levels and disabling: `{"style": "off", "code/brackets": "error"}`. See [Rules](#rules-levels-and-disabling). |
| `xbsl.linter.debounce` | `300` | Delay (ms) before linting while typing. |
| `xbsl.projectRoot` | – | Sources root for project-wide runs and the navigation index, relative to the workspace folder (or absolute). Empty – the whole folder. Set it when the repository holds examples or copies next to the project: otherwise project-scope rules (`Ид` uniqueness etc.) cross-fire between directories. |
| `xbsl.workspaceLint` | `true` | Full workspace run on every save of a `.xbsl`/`.yaml` file. |
| `xbsl.workspaceLintTimeout` | `60000` | Kill a workspace run after this many ms (`0` – no limit). |
| `xbsl.navigation.enabled` | `true` | Index-based go-to-definition and completion. |

## Rules: levels and disabling

Every finding carries a **"Configure rule..."** action in its lightbulb (`Ctrl+.`): disable
the rule or override its level (error / warning / info / hint) without leaving the line;
the check reruns right away. The choices land in the `xbsl.rules` setting – a map from a
rule id (`whitespace/trailing`) or a whole group (`style`) to a level or `off`; an exact id
beats its group, `off` also excludes the rule from the run. Works in both the CLI and the
LSP mode.

## LSP mode (experimental)

With `"xbsl.lsp.enabled": true` the extension runs everything through a long-living
`xbsllint-lsp` server instead of spawning the CLI per event: the Element language data and
the project index stay resident, so as-you-type diagnostics respond in milliseconds, and
**hover** appears (a card for a project object, method or form component). Definition,
completion, project-wide diagnostics on save and quick fixes work as before, just faster.
Requires the linter installed with the `[lsp]` extra (`pip install "xbsllint[lsp]"`); the
server is found as `xbsllint-lsp` on `PATH`, via `xbsl.linter.pythonPath` (run as a
module), or by the explicit `xbsl.lsp.command`. If the server fails to start, the
extension falls back to the regular CLI mode by itself. Toggling the setting needs a
window reload.

## Code palette

The command **XBSL: палитра кода** (`xbsl.choosePalette`) recolors XBSL syntax with one of
the popular palettes: the 1C:Element web IDE style (red keywords, blue strings), One Dark,
Monokai, Dracula, GitHub Dark – or resets back to the active editor theme. The choice is
applied via `editor.tokenColorCustomizations` rules addressing only `*.xbsl` scopes, so the
global theme and other languages stay untouched; the extension manages only its own rules
(prefixed `xbsl-palette`) and preserves any customizations of yours.

## Commands

- **XBSL: проверить весь проект** (`xbsl.lintProject`) – lint the whole workspace.
- **XBSL: перезапустить линтер** (`xbsl.restartLinter`) – clear and re-lint open files.
- **XBSL: палитра кода** (`xbsl.choosePalette`) – pick a syntax palette for XBSL (see above).

## How it works

Two producers feed one diagnostic collection, and the split is by buffer state:

- **While you type** (dirty buffer) the extension runs
  `xbsllint --stdin --filename <name> --format json` on the live text – per-file rules only,
  fast, debounced. Its result replaces the diagnostics of *that buffer only*.
- **When you save** any `.xbsl`/`.yaml` file, the extension runs
  `xbsllint <workspace folder> --format json` in the background (debounced, at most one run
  at a time; a save during a run cancels the now-stale run and starts over). The result covers
  per-file *and* project-scope rules, so it replaces the diagnostics of *every* file in the
  folder – except buffers that are dirty again by then: those stay with their live `--stdin`
  diagnostics until the next save.

This way there are no duplicates and no rule is lost: a clean file always shows the full
workspace-run picture, a file being edited shows the instant per-file picture, and each save
reconciles the two. Both runs speak the same `{diagnostics, summary}` JSON contract that the
linter's MCP server exposes.

A workspace run that fails or exceeds `xbsl.workspaceLintTimeout` is reported to the *XBSL*
output channel only – no popups on every save.

## Development

```sh
npm install
npm run compile          # esbuild bundle -> dist/extension.js
npm run check            # tsc type-check
npm test                 # unit tests for the navigation core (plain Node, no runner)
npm run package          # build the .vsix (via @vscode/vsce)
```

Press **F5** in VS Code to launch an Extension Development Host with the extension loaded.

## License

MIT – see the [repository](https://github.com/keyfire/xbsl-lint).
