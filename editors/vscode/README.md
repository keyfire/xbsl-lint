# XBSL for VS Code

Syntax highlighting and on-the-fly linting for **1C:Element** sources (`.xbsl`), powered by the
[xbsllint](https://github.com/keyfire/xbsl-lint) linter.

![XBSL: syntax highlighting and an inline lint diagnostic from xbsllint](https://raw.githubusercontent.com/keyfire/xbsl-lint/main/editors/vscode/images/demo.png)

## Features

- **Syntax highlighting** for `.xbsl`: keywords (both Russian and English forms), declarations,
  operators, `@`-decorators, numbers, comments, and strings with `%name` / `${...}` interpolation.
- **Live diagnostics** as you type (debounced) and on save — brackets/blocks balance, unused
  locals, typography, code-style conventions, and everything else the linter reports. Squiggles
  carry the rule id (e.g. `code/brackets`) and severity.
- **Whole-project check** — the command *XBSL: проверить весь проект* runs the linter across the
  workspace, including cross-file rules (`Ид` uniqueness, unknown types) that a single buffer
  cannot see.

`.yaml` element descriptions keep their built-in YAML highlighting.

## Requirements

The extension is a thin client over the `xbsllint` CLI — it does not bundle a checker. You need:

1. **Python 3.10+** and the linter: `pip install xbsllint`.
2. **Element language data** — generated once from your 1C:Element distribution, see
   [step 1 of the linter README](https://github.com/keyfire/xbsl-lint#step-1-generate-the-language-data).
   Without it most rules cannot run; the extension surfaces the linter's error once.

By default the extension calls `xbsllint` from `PATH`. Point it elsewhere with
`xbsl.linter.command` (an executable) or `xbsl.linter.pythonPath` (an interpreter — the linter is
then invoked as `<python> -m xbsllint`).

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
| `xbsl.linter.debounce` | `300` | Delay (ms) before linting while typing. |

## Commands

- **XBSL: проверить весь проект** (`xbsl.lintProject`) — lint the whole workspace.
- **XBSL: перезапустить линтер** (`xbsl.restartLinter`) — clear and re-lint open files.

## How it works

For each buffer the extension runs `xbsllint --stdin --filename <name> --format json` and turns the
resulting `{diagnostics, summary}` payload into VS Code diagnostics — the same JSON contract the
linter's MCP server exposes. Per-file rules run on the live buffer; cross-file rules run via the
project command against files on disk.

## Development

```sh
npm install
npm run compile          # esbuild bundle -> dist/extension.js
npm run check            # tsc type-check
npm run package          # build the .vsix (via @vscode/vsce)
```

Press **F5** in VS Code to launch an Extension Development Host with the extension loaded.

## License

MIT — see the [repository](https://github.com/keyfire/xbsl-lint).
