---
title: "Changelog"
description: "Release history of the xbsl toolkit: the linter, the LSP and MCP servers, the documentation index and the metadata scaffolding."
sidebar:
  label: "Changelog"
  order: 8
---

<!-- Generated from CHANGELOG.md; do not edit by hand.
     Edit CHANGELOG.md and run: npm run sync:docs -->

> This is the changelog of the **xbsl toolkit** – the Python engine behind the linter, the LSP
> and MCP servers, the documentation index and the metadata scaffolding. The VS Code extension
> keeps its own history in
> [editors/vscode/CHANGELOG.md](https://github.com/keyfire/xbsl/blob/main/editors/vscode/CHANGELOG.md).
> Entries use the English spelling of platform metadata names (`Name`, `Code`, `Attributes`); the
> Russian spellings – the ones a Russian-language project is written in – are in the
> [Russian changelog](https://github.com/keyfire/xbsl/blob/main/CHANGELOG.ru.md).

## 0.30.1

- **`yaml/bare-object-value` accepts a localized-string reference.** A `$`-reference to a
  localized string is a valid value where a literal is expected, so the rule no longer flags it as
  a bare word.
- **Completion follows a chain past a property link.** The LSP walks a member chain through a
  property to the type behind it and keeps offering members, with a guard that stops at the edge of
  the stdlib closure instead of looping.
- **Regenerated language data is picked up without a restart.** The freshness stamp drops the
  in-process caches when the data under the data root changes, so a fresh `xbsl language` is seen
  by an already-running server.
- **The CLI command reference is under test.** `help`, `language`, `coverage` and `freshness` are
  covered by the command-reference tests, and the servers gated behind optional extras (MCP, LSP)
  skip cleanly on a minimal install instead of failing to import.

## 0.30.0

- **Faster on large projects.** Caches for the data-binding layer, YAML parsed through libyaml
  (`compose`), and worker pools sized to the workload cut the wall-clock of a full project run.

## 0.29.0

- **The documentation site, and CLI help and reference in both languages.** The site
  ([docs.keyfire.ru/xbsl](https://docs.keyfire.ru/xbsl/)) is built from these sources; the command
  reference and every `--help` string are complete in English and Russian.
- **The schema of a collection item.** The platform metamodel resolves the class of a nested node –
  an enumeration value, an attribute, a dimension, a resource, a structure field, a tabular-section
  attribute – so the linter sees its full schema with defaults and documentation, not only what the
  yaml already sets.

## 0.28.0

- **A type's hover carries its description.** Hovering a type shows the sentence from the platform
  documentation above the page link, not the link alone (LSP).
- **Removing a form handler is one engine operation.** `xbsl/removeHandler` unbinds an event and
  deletes its method – with the annotations and the separating blank line – as a single edit.

## 0.27.0

- **A unified metamodel API.** Property types, enumerations and defaults are read through one
  interface; the linter and scaffolding resolve object schemas through it, including the properties
  an object has but the yaml leaves unset.

## 0.26.1

- **Completion follows the project's development language.** The language of the completion labels
  and inserts is taken from the project's development language rather than assumed.

## 0.26.0

- **Four new linter rules.** `yaml/bare-object-value` – a bare word where a quoted literal or an
  `=` binding is expected. `code/resource-bare-name` and `code/unknown-resource` – a resource
  addressed by a bare file name that must exist in the project or in the platform's standard image
  library. `yaml/no-expression-in-literal` – an expression inside a node the platform accepts only
  as a literal (a font, a colour).
- **Scaffolding accepts the element kind in any platform language.** `Catalog` works the same as
  `Справочник`; kinds resolve through a terms dictionary extracted from your distribution.
- **Language data comes from the compiler, not from constants.** The terms dictionary now covers
  the members of every stdlib type, and the query-language keywords come from the parser's own
  dictionary instead of constants in the code.

## 0.25.0

- **Three engine rules.** `yaml/ref-needs-nullable` – a reference type in a type position without
  `?` (a reference has no default, so applying the build fails). `yaml/unknown-enum-value` – a
  component property value outside the ui-schema enumeration, which also covers the alignment trap
  (the horizontal axis has `End`, the vertical one does not). `yaml/standard-field-length` – a
  `Name` over 400 characters or a `Code` over 50, the limits the platform rejects.
- **`code/undefined-name` reads names in string interpolation.** A substitution inside a string
  literal (`"...?$format=json"`) is checked, so an undefined name is reported before the build
  instead of failing the compilation.
- **A guard keeps the rule metadata honest.** A test compares every counter, table row and
  documentation link against the rule registry, so the published numbers cannot drift from what the
  engine ships.

---

> Releases before 0.25.0 predate this changelog. The VS Code extension's
> [CHANGELOG](https://github.com/keyfire/xbsl/blob/main/editors/vscode/CHANGELOG.md) carries the
> product history back to 0.1.0.
