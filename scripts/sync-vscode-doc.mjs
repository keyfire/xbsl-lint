// Keeps the extension page of the documentation site in sync with the marketplace README.
//
// The source of truth is editors/vscode/README.md (+ .ru.md) - the very file published to
// the VS Code Marketplace. Here it becomes docs/vscode.md (+ .ru.md): the leading H1 and the
// hand-written language switcher line are dropped (Blume provides both), and frontmatter
// (title/description/sidebar) is added.
//
// Run: `npm run sync:docs` (also runs automatically before `npm run build` and `npm run dev`,
// and in CI as its own step before `npx blume build`). After editing editors/vscode/README*.md
// regenerate the page with this script and commit it.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

const pages = [
  {
    src: "editors/vscode/README.md",
    dest: "docs/vscode.md",
    title: "XBSL for VS Code",
    description:
      "The VS Code extension for 1C:Element: syntax highlighting, live linting with Quick Fix, the visual form designer, the metadata explorer, and project-wide navigation – all on the xbsl engine.",
    sidebarLabel: "VS Code extension",
    order: 5,
    note: (src) =>
      `<!-- Generated from ${src}; do not edit by hand.\n` +
      `     Edit ${src} and run: npm run sync:docs -->\n`,
  },
  {
    src: "editors/vscode/README.ru.md",
    dest: "docs/vscode.ru.md",
    title: "XBSL для VS Code",
    description:
      "Расширение VS Code для 1С:Элемент: подсветка синтаксиса, линтинг на лету с Quick Fix, визуальный конструктор форм, обозреватель метаданных и навигация по проекту – всё на движке xbsl.",
    sidebarLabel: "Расширение VS Code",
    order: 5,
    note: (src) =>
      `<!-- Сгенерировано из ${src} – не редактируйте вручную.\n` +
      `     Правьте ${src} и выполните: npm run sync:docs -->\n`,
  },
];

// The hand-written switcher line, "**English** · [Русский](...)" or
// "[English](...) · **Русский**" - on the site Blume's own switcher replaces it.
const isSwitcherLine = (line) =>
  /Русский/.test(line) && /(\*\*English\*\*|\[English\]\()/.test(line);

// Relative paths in the README are relative to editors/vscode/. On the site the page lives
// in docs/, so they are rewritten to absolute repository URLs: images to raw (so they render),
// ordinary links to blob (so they open on GitHub). Absolute (http/https), anchors (#...) and
// root-relative (/...) paths are left alone.
const RAW = "https://raw.githubusercontent.com/keyfire/xbsl/main/editors/vscode/";
const BLOB = "https://github.com/keyfire/xbsl/blob/main/editors/vscode/";
const absolutizeLinks = (md) =>
  md
    .replace(/!\[([^\]]*)\]\((?!https?:|\/|#)([^)]+)\)/g, `![$1](${RAW}$2)`)
    .replace(/(?<!!)\[([^\]]*)\]\((?!https?:|\/|#|mailto:)([^)]+)\)/g, `[$1](${BLOB}$2)`);

for (const page of pages) {
  const raw = readFileSync(join(root, page.src), "utf8");
  const lines = raw.split("\n");

  let i = 0;
  if (lines[i]?.startsWith("# ")) i++; // the leading H1 becomes the frontmatter title
  // Drop blank lines and the language-switcher line right under the heading.
  while (i < lines.length && (lines[i].trim() === "" || isSwitcherLine(lines[i]))) i++;
  const body = absolutizeLinks(lines.slice(i).join("\n").replace(/^\n+/, "").trimEnd());

  const frontmatter =
    "---\n" +
    `title: ${JSON.stringify(page.title)}\n` +
    `description: ${JSON.stringify(page.description)}\n` +
    "sidebar:\n" +
    `  label: ${JSON.stringify(page.sidebarLabel)}\n` +
    `  order: ${page.order}\n` +
    "---\n";

  const note = page.note(page.src);

  writeFileSync(join(root, page.dest), `${frontmatter}\n${note}\n${body}\n`, "utf8");
  console.log(`synced ${page.src} -> ${page.dest}`);
}
