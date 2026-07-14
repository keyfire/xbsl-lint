// Статус-бар (справа внизу): версия расширения и линтера xbsllint + режим дополнения (обычный CLI /
// LSP). Нужно, чтобы при разработке сразу видеть, какая сборка активна, и не путать старую с новой.
// Версию линтера получаем вызовом "<линтер> --version"; при неудаче показываем "?".

import * as vscode from "vscode";
import { spawn } from "child_process";
import * as fs from "fs";
import * as path from "path";
import { LinterConfig } from "./report";

const SHOW_INFO = "xbsl.showVersionInfo";

// Время сборки активного расширения = mtime установленного dist/extension.js. Все дев-сборки имеют одну
// версию (0.12.0), поэтому именно метка времени отличает свежую сборку от прежней.
function buildStamp(context: vscode.ExtensionContext): string {
  try {
    const t = fs.statSync(path.join(context.extensionPath, "dist", "extension.js")).mtime;
    const p = (n: number): string => String(n).padStart(2, "0");
    return `${p(t.getHours())}:${p(t.getMinutes())} ${p(t.getDate())}.${p(t.getMonth() + 1)}`;
  } catch {
    return "?";
  }
}

function linterVersion(cfg: LinterConfig): Promise<string | undefined> {
  return new Promise((resolve) => {
    const args = [...(cfg.usePython ? ["-m", "xbsllint"] : []), "--version"];
    let child;
    try {
      child = spawn(cfg.command, args);
    } catch {
      resolve(undefined);
      return;
    }
    let out = "";
    const grab = (d: Buffer): void => {
      out += d.toString("utf8");
    };
    child.stdout.on("data", grab);
    child.stderr.on("data", grab); // некоторые инструменты печатают версию в stderr
    child.on("error", () => resolve(undefined));
    child.on("close", () => {
      const m = /(\d+\.\d+(?:\.\d+)?[A-Za-z0-9.+-]*)/.exec(out);
      resolve(m ? m[1] : undefined);
    });
    child.stdin?.end();
  });
}

export function registerStatusBar(
  context: vscode.ExtensionContext,
  getLinter: (resource?: vscode.Uri) => LinterConfig
): { setLspMode: (on: boolean) => void } {
  const extVersion = String(context.extension.packageJSON.version ?? "?");
  const build = buildStamp(context);
  const item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  item.command = SHOW_INFO;
  let linter = "…";
  // Режим показываем ФАКТИЧЕСКИЙ, а не по настройке: сервер мог не подняться (нет extra [lsp]),
  // и тогда дополнение идёт по-старому, через CLI-индекс. Ставит его extension после запуска.
  let lspOn = false;

  const line = (): string =>
    vscode.l10n.t(
      "Extension XBSL {0} (build {3}) · linter xbsllint {1} · completion: {2}",
      extVersion,
      linter,
      lspOn ? vscode.l10n.t("LSP") : vscode.l10n.t("CLI index"),
      build
    );

  const render = (): void => {
    item.text = `$(versions) XBSL ${extVersion} @${build} · lint ${linter}`;
    item.tooltip = line();
    item.show();
  };

  const refresh = async (): Promise<void> => {
    render();
    linter = (await linterVersion(getLinter())) ?? "?";
    render();
  };

  context.subscriptions.push(
    item,
    vscode.commands.registerCommand(SHOW_INFO, () => void vscode.window.showInformationMessage(line())),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("xbsl.linter") || e.affectsConfiguration("xbsl.lsp")) {
        void refresh();
      }
    })
  );
  void refresh();
  return {
    setLspMode: (on: boolean): void => {
      lspOn = on;
      render();
    },
  };
}
