# xbsl linter rules

**English** · [Русский](https://github.com/keyfire/xbsl/blob/main/docs/RULES.ru.md)

The full list of linter checks. This file is extended as rules are added; the live list at
runtime is `xbsl list-rules` (or the MCP `list_rules`). Currently there are 80 rules.

## Boundary: the linter complements the compiler, it does not replace it

The linter works over text and the project model, without type inference. It catches what the
Element compiler does not check or reports unclearly (conventions, typography, structure,
references to non-existent types and objects), but NOT what needs type inference: a redundant
cast, an unclosed resource, a return-type mismatch. Code correctness is verified by the
server-side compilation on deploy; the linter runs before it and removes common mistakes early.

## How to read the table

- **Rule** – the `group/name` identifier. The group (the part before `/`) lets you enable and
  disable rules in bulk.
- **Severity** – `error` (a build/CI should fail), `warning` (a convention is broken),
  `info` (a hint, usually off).
- **Default** – whether the rule is in the default set (`on`) or is enabled explicitly (`off`).
- **Scope** – `file` (the rule sees one file) or `project` (needs the whole-project index:
  duplicate Ids, unknown types, cross-module calls).
- **Docs** – a link to the platform documentation section behind the rule. In VS Code the code
  of such a rule in the Problems panel opens that section right in the editor.

## Tiers

Rules are split into tiers A-D by what they rely on. A tier is also a quick filter for
`--select`/`--ignore` (alongside the group and the identifier): `--select A,B` runs only
structure and text, `--ignore D` drops the semantics over stdlib.

### Tier A - structure and YAML

The file exists, parses, the object has a unique UUID, the name matches the file.

| Rule | Severity | Default | Scope | What it checks | Docs |
|---|---|---|---|---|---|
| `yaml/valid` | error | on | file | YAML does not parse | – |
| `yaml/id-uuid` | error | on | file | Ид is not a UUID | – |
| `yaml/id-required` | warning | on | file | The object has no Ид | – |
| `yaml/name-matches-file` | warning | on | file | Имя does not match the file name | – |
| `yaml/id-unique` | error | on | project | Duplicate Ид in the project | – |
| `project/identifier` | warning | on | file | Project name or vendor is not an identifier | [docs](https://1cmycloud.com/docs/help/topics/project-properties-standard/) |
| `project/presentation` | warning | on | file | Project presentation is empty | [docs](https://1cmycloud.com/docs/help/topics/project-properties-standard/) |
| `project/version` | warning | on | file | Project version is not A.B.C | [docs](https://1cmycloud.com/docs/help/topics/project-properties-standard/) |
| `structure/xbsl-pair` | warning | on | file | Module .xbsl without a paired .yaml | – |

### Tier B - text and conventions

Encoding, newlines, whitespace, typography (dashes, quotes, ellipsis), line length.

| Rule | Severity | Default | Scope | What it checks | Docs |
|---|---|---|---|---|---|
| `typography/em-dash` | info | off | file | Em dash in a comment | – |
| `typography/ellipsis` | warning | on | file | Ellipsis character in a comment | – |
| `typography/curly-quotes` | warning | on | file | Curly quotes | – |
| `typography/guillemets-comment` | info | off | file | Guillemets in a comment | – |
| `whitespace/trailing` | warning | on | file | Trailing whitespace | – |
| `whitespace/mixed-newline` | warning | on | file | Mixed newlines | – |
| `encoding/utf8` | error | on | file | File is not UTF-8 | – |
| `style/tab-indent` | warning | on | file | Tab in the indentation | [docs](https://1cmycloud.com/docs/help/topics/general-design/) |
| `style/line-length` | info | off | file | Line longer than 120 characters | [docs](https://1cmycloud.com/docs/help/topics/general-design/) |

### Tier C - code structure, basic syntax and code-writing conventions

Block and bracket balance, loop and method headers, local variables and the `style/` group -
conventions from the documentation section "Code-writing recommendations". Some `style/` rules
are off by default (accumulated debt, `info`): enable them with `--select style` to measure.

| Rule | Severity | Default | Scope | What it checks | Docs |
|---|---|---|---|---|---|
| `code/parse-error` | error | on | file | Syntax error (a full parse against the platform grammar) | [docs](https://1cmycloud.com/docs/help/topics/general-design/) |
| `code/brackets` | error | on | file | Unbalanced brackets () [] {} | – |
| `code/blocks` | error | on | file | Unbalanced blocks and ';' | [docs](https://1cmycloud.com/docs/help/topics/general-design/) |
| `code/ternary-and-or` | error | on | file | Compound ternary condition without parentheses | [docs](https://1cmycloud.com/docs/help/topics/question-mark-operation/) |
| `code/param-type-required` | error | on | file | Parameter without a type and without a default value | [docs](https://1cmycloud.com/docs/help/topics/methods-in-built-in-script-language/) |
| `code/loop-header` | error | on | file | Malformed 'для' loop header | [docs](https://1cmycloud.com/docs/help/topics/for-in-loop/) |
| `code/unused-local` | warning | on | file | Unused local variable | – |
| `code/unused-loop-var` | warning | on | file | Unused loop variable | – |
| `code/ref-field-needs-req` | error | on | file | Structure reference field without 'обз' | [docs](https://1cmycloud.com/docs/help/topics/structure/) |
| `style/boolean-compare` | info | off | file | Comparing a boolean value with Истина/Ложь | [docs](https://1cmycloud.com/docs/help/topics/check-logical-values/) |
| `style/undefined-is` | warning | on | file | Checking Неопределено with the 'это' operator | [docs](https://1cmycloud.com/docs/help/topics/check-if-undefined/) |
| `style/negated-is` | warning | on | file | Negating the 'это' operator on the outside | [docs](https://1cmycloud.com/docs/help/topics/is-operator/) |
| `style/semicolon-line` | warning | on | file | ';' not on its own line | [docs](https://1cmycloud.com/docs/help/topics/general-design/) |
| `style/wrap-operator` | warning | on | file | Operator at the end of a wrapped line | [docs](https://1cmycloud.com/docs/help/topics/split-expressions/) |
| `style/wrap-comma` | warning | on | file | Comma at the start of a wrapped line | [docs](https://1cmycloud.com/docs/help/topics/split-expressions/) |
| `style/camel-case` | info | off | file | Name is not in UpperCamelCase | [docs](https://1cmycloud.com/docs/help/topics/naming-convention/) |
| `style/const-case` | warning | on | file | Constant is not in ALL_CAPS | [docs](https://1cmycloud.com/docs/help/topics/naming-convention/) |
| `style/exception-prefix` | warning | on | file | Exception name without the "Исключение" prefix | [docs](https://1cmycloud.com/docs/help/topics/naming-convention/) |
| `style/abbreviation-case` | info | off | file | All-caps abbreviation in a name | [docs](https://1cmycloud.com/docs/help/topics/naming-convention/) |
| `style/enum-name-vid` | warning | on | file | Enumeration name starts with "Тип" | [docs](https://1cmycloud.com/docs/help/topics/naming-convention/) |
| `style/collection-literal` | info | off | file | Manual collection fill instead of a literal | [docs](https://1cmycloud.com/docs/help/topics/collection-literals-usage/) |
| `style/redundant-tostring` | info | off | file | '.ВСтроку()' in a concatenation | [docs](https://1cmycloud.com/docs/help/topics/string-concatenation/) |
| `style/interpolation` | info | off | file | Concatenation instead of interpolation | [docs](https://1cmycloud.com/docs/help/topics/string-concatenation/) |
| `style/type-colon-space` | warning | on | file | Spaces around the type colon | [docs](https://1cmycloud.com/docs/help/topics/type-description-and-initialization/) |
| `style/union-spaces` | warning | on | file | Spaces around '\|' in a union type | [docs](https://1cmycloud.com/docs/help/topics/type-description-and-initialization/) |
| `style/nullable-shorthand` | warning | on | file | Неопределено in a type without the '?' shorthand | [docs](https://1cmycloud.com/docs/help/topics/type-description-and-initialization/) |
| `style/redundant-type` | warning | on | file | Redundant type annotation on initialization | [docs](https://1cmycloud.com/docs/help/topics/type-description-and-initialization/) |
| `style/optional-params-last` | warning | on | file | Optional parameter before a required one | [docs](https://1cmycloud.com/docs/help/topics/method-declarations/) |

### Tier D - semantics over stdlib, forms and the metamodel

Needs the project index and platform data: unknown types and objects, enumeration values,
the execution model (client/server), form handlers, properties and queries.

| Rule | Severity | Default | Scope | What it checks | Docs |
|---|---|---|---|---|---|
| `yaml/choice-needs-static-list` | warning | on | file | ВыборЗначения without a static СписокВыбора | [docs](https://1cmycloud.com/docs/help/stdlib/element/xbsl/Std/Interface/CommonComponents/ValueChoice_ru/) |
| `code/unknown-type` | warning | on | project | Unknown type | – |
| `code/undefined-name` | warning | off | project | Undefined name in an expression (typos like `Адресар` for `Адреса`); on by default once the stdlib catalog is completed | – |
| `code/unknown-object-type` | warning | on | project | Unknown project-object type | – |
| `yaml/unknown-type` | warning | on | project | Unknown type in yaml | – |
| `yaml/dynlist-missing-field` | warning | on | project | Missing dynamic-list field | [docs](https://1cmycloud.com/docs/help/topics/dynamic-list/) |
| `code/unknown-enum-value` | warning | on | project | Unknown enumeration value | [docs](https://1cmycloud.com/docs/help/topics/enumeration-properties/) |
| `yaml/enum-needs-nullable` | warning | on | project | Enumeration without nullable | [docs](https://1cmycloud.com/docs/help/topics/enumeration-properties/) |
| `form/unknown-handler` | warning | on | project | Form handler not found in the module | [docs](https://1cmycloud.com/docs/help/topics/form-component/) |
| `code/server-call-from-handler` | warning | on | project | Server method is unavailable to a client handler | [docs](https://1cmycloud.com/docs/help/topics/module-execution/) |
| `code/client-annotation-in-server-module` | warning | on | project | Client annotation in a server common module | [docs](https://1cmycloud.com/docs/help/topics/module-execution/) |
| `code/client-module-in-http-service` | warning | on | project | Client common module in an HTTP service | [docs](https://1cmycloud.com/docs/help/topics/module-execution/) |
| `code/local-method-cross-component` | warning | on | project | Cross-component call of a local method | [docs](https://1cmycloud.com/docs/help/topics/modular-development/) |
| `naming/yo` | warning | on | file | Letter "ё" in a name | [docs](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/underscore` | warning | on | file | Underscore in a name | [docs](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/abbreviation` | warning | on | file | All-caps abbreviation in a name | [docs](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/latin-term` | warning | on | file | English term spelled in Cyrillic | [docs](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/enum-vid` | warning | on | file | Enumeration name with the word "Тип" | [docs](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/kind-in-name` | warning | on | file | Element kind inside its name | [docs](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/filler-word` | warning | on | file | Filler word in a name | [docs](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/module-suffix` | warning | on | file | Environment suffix in a common module name | [docs](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/number` | warning | on | file | Wrong number for the element kind | [docs](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/boolean-name` | warning | on | file | Boolean attribute name | [docs](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/presentation` | warning | on | file | Element presentation | [docs](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `naming/prefix-by-kind` | warning | on | file | Kind-specific name without its prefix | [docs](https://1cmycloud.com/docs/help/topics/project-element-names-standard/) |
| `code/unknown-ns-object` | warning | on | project | Unknown object in a kind namespace | – |
| `query/unknown-table` | warning | on | project | Unknown table in a query | [docs](https://1cmycloud.com/docs/help/topics/select-from/) |
| `query/in-subquery-composite` | warning | on | project | 'IN' with a subquery over a composite type | [docs](https://1cmycloud.com/docs/help/topics/in-expression/) |
| `yaml/unknown-property` | warning | on | file | Unknown object property | – |
| `code/reserved-name` | warning | on | file | Reserved name | – |
| `yaml/builtin-property-name` | warning | on | file | Built-in property name clash | – |
| `yaml/size-needs-no-stretch` | info | off | file | A size without disabling the stretch | [docs](https://1cmycloud.com/docs/help/topics/arrange-components-on-screen/) |
| `code/unused-method` | warning | off | project | Method is never referenced | – |
| `yaml/missing-import` | warning | on | project | Missing subsystem import in yaml | [docs](https://1cmycloud.com/docs/help/topics/modular-development/) |

## Enabling and disabling

`--select` and `--ignore` accept a rule identifier, a group (the part before `/`, e.g. `style`)
or a tier letter `A`/`B`/`C`/`D`. A plugin may override a rule's severity (the `xbsl.severity`
entry-points group); `XBSL_NO_PLUGINS=1` disables plugins and restores the built-in values from
this table.
