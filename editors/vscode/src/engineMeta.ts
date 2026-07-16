// Скаффолдинг метаданных: тонкий клиент движка xbsl. Единственный источник шаблонов и
// правок – модуль xbsl.scaffold движка; расширение только собирает параметры в UI и
// применяет присланные изменения через WorkspaceEdit (сохраняются undo и грязные буферы).
//
// Два транспорта с одинаковым результатом (полные новые тексты файлов):
//   - LSP-режим: кастомный запрос xbsl/meta* (сервер читает открытые буферы);
//   - CLI-режим: `xbsl <подкоманда> ... --dry-run` (движок читает диск, поэтому перед
//     правкой существующего файла грязный буфер предлагается сохранить).

import { spawn } from "child_process";
import * as vscode from "vscode";
import { lspActive, lspRequest } from "./lspClient";
import { pipInstallCommand, runInstallTask } from "./installer";

export interface ScaffoldFile {
  path: string;
  created: boolean;
  content: string;
  cursor?: { line: number; character: number } | null;
}

export interface ScaffoldResult {
  files?: ScaffoldFile[];
  notes?: string[];
  error?: string;
}

interface CliPlan {
  command: string;
  args: string[];
}

function cliPlan(subcommand: string, args: string[]): CliPlan {
  const cfg = vscode.workspace.getConfiguration("xbsl");
  const python = (cfg.get<string>("linter.pythonPath") || "").trim();
  if (python) {
    return { command: python, args: ["-m", "xbsl", subcommand, ...args, "--dry-run"] };
  }
  const command = (cfg.get<string>("linter.command") || "xbsl").trim();
  return { command, args: [subcommand, ...args, "--dry-run"] };
}

function runCli(plan: CliPlan, cwd: string | undefined): Promise<ScaffoldResult | undefined> {
  return new Promise((resolve) => {
    let child;
    try {
      child = spawn(plan.command, plan.args, { cwd });
    } catch {
      resolve(undefined);
      return;
    }
    let out = "";
    child.stdout.on("data", (d: Buffer) => (out += d.toString("utf8")));
    child.stderr.on("data", () => undefined);
    child.on("error", () => resolve(undefined));
    child.on("close", () => {
      try {
        resolve(JSON.parse(out) as ScaffoldResult);
      } catch {
        resolve(undefined); // не-JSON: старый движок без подкоманд либо крах запуска
      }
    });
    child.stdin?.end();
  });
}

// Сообщение о недоступности скаффолдинга: старый движок или движок не установлен.
function reportUnavailable(): void {
  const install = vscode.l10n.t("Install/upgrade the engine");
  void vscode.window
    .showErrorMessage(
      vscode.l10n.t("XBSL: metadata commands need the xbsl engine 0.16+ (pip install --upgrade xbsl)."),
      install
    )
    .then((pick) => {
      if (pick === install) {
        runInstallTask("xbsl", pipInstallCommand("xbsl"), "workbench.action.reloadWindow");
      }
    });
}

// Вызов операции скаффолдинга: LSP при активном сервере, иначе CLI. undefined – движок
// недоступен (сообщение уже показано); {error} – отказ операции (показан вызывающим).
export async function callMeta(
  lspMethod: string,
  lspParams: Record<string, unknown>,
  cliSubcommand: string,
  cliArgs: string[],
  cwd?: string
): Promise<ScaffoldResult | undefined> {
  if (lspActive()) {
    const viaLsp = await lspRequest<ScaffoldResult>(lspMethod, lspParams);
    if (viaLsp) {
      return viaLsp;
    }
    // Сервер поднят, но метода нет – значит движок старее расширения.
  }
  const viaCli = await runCli(cliPlan(cliSubcommand, cliArgs), cwd);
  if (viaCli) {
    return viaCli;
  }
  reportUnavailable();
  return undefined;
}

// В CLI-режиме движок читает файлы с диска: несохранённый буфер правимого файла обязан
// быть сохранён до вызова, иначе применение полного нового текста затёрло бы правки.
export async function ensureSavedForCli(paths: string[]): Promise<boolean> {
  if (lspActive()) {
    return true; // LSP-сервер видит буферы, сохранение не требуется
  }
  const dirty = vscode.workspace.textDocuments.filter(
    (doc) => doc.isDirty && paths.some((p) => doc.uri.fsPath === p)
  );
  if (!dirty.length) {
    return true;
  }
  const save = vscode.l10n.t("Save and continue");
  const pick = await vscode.window.showWarningMessage(
    vscode.l10n.t("XBSL: the file has unsaved changes; save it before the metadata edit."),
    { modal: true },
    save
  );
  if (pick !== save) {
    return false;
  }
  for (const doc of dirty) {
    await doc.save();
  }
  return true;
}

// Применение результата: новые файлы создаются, правимые заменяются целиком одним
// WorkspaceEdit (обратимо через undo). Возвращает список затронутых путей.
export async function applyScaffold(result: ScaffoldResult): Promise<string[]> {
  if (result.error) {
    void vscode.window.showWarningMessage(vscode.l10n.t("XBSL: {0}", result.error));
    return [];
  }
  const files = result.files ?? [];
  const we = new vscode.WorkspaceEdit();
  for (const file of files) {
    const uri = vscode.Uri.file(file.path);
    if (file.created) {
      we.createFile(uri, { contents: Buffer.from(file.content, "utf8"), ignoreIfExists: false });
    } else {
      const doc = await vscode.workspace.openTextDocument(uri);
      const full = new vscode.Range(doc.positionAt(0), doc.positionAt(doc.getText().length));
      we.replace(uri, full, file.content);
    }
  }
  await vscode.workspace.applyEdit(we);
  // Правки существующих файлов сохраняются (создание файлов WorkspaceEdit уже пишет на диск).
  for (const file of files.filter((f) => !f.created)) {
    const doc = vscode.workspace.textDocuments.find((d) => d.uri.fsPath === file.path);
    if (doc?.isDirty) {
      await doc.save();
    }
  }
  for (const note of result.notes ?? []) {
    void vscode.window.showInformationMessage(vscode.l10n.t("XBSL: {0}", note));
  }
  return files.map((f) => f.path);
}
