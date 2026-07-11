// Экспериментальный LSP-режим (xbsl.lsp.enabled): вместо вызовов CLI на каждое событие
// расширение поднимает долгоживущий сервер xbsllint-lsp (extra [lsp] пакета xbsllint) и
// отдаёт ему диагностику, навигацию, автодополнение, hover и quick-fix. Данные Элемента и
// индекс проекта живут в памяти сервера - отклик на набор текста не платит за старт
// интерпретатора.

import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;

interface SpawnPlan {
  command: string;
  args: string[];
}

// Чем запускать сервер: явная команда из настройки, иначе интерпретатор из
// xbsl.linter.pythonPath (модулем), иначе xbsllint-lsp из PATH.
function spawnPlan(cfg: vscode.WorkspaceConfiguration): SpawnPlan {
  const explicit = (cfg.get<string>("lsp.command") || "").trim();
  if (explicit) {
    return { command: explicit, args: [] };
  }
  const python = (cfg.get<string>("linter.pythonPath") || "").trim();
  if (python) {
    return { command: python, args: ["-m", "xbsllint.lsp"] };
  }
  return { command: "xbsllint-lsp", args: [] };
}

export async function activateLsp(
  context: vscode.ExtensionContext,
  output: vscode.OutputChannel
): Promise<boolean> {
  const cfg = vscode.workspace.getConfiguration("xbsl");
  const folder = vscode.workspace.workspaceFolders?.[0];
  const plan = spawnPlan(cfg);
  const args = [...plan.args];
  const projectRoot = (cfg.get<string>("projectRoot") || "").trim();
  if (projectRoot) {
    args.push("--project-root", projectRoot);
  }
  for (const [flag, key] of [
    ["--select", "linter.select"],
    ["--ignore", "linter.ignore"],
    ["--data-dir", "linter.dataDir"],
    ["--lang", "linter.lang"],
  ] as const) {
    const value = (cfg.get<string>(key) || "").trim();
    if (value) {
      args.push(flag, value);
    }
  }

  const serverOptions: ServerOptions = {
    command: plan.command,
    args,
    options: { cwd: folder?.uri.fsPath },
  };
  // yaml ограничиваем корнем исходников, чтобы не линтить посторонние yaml репозитория.
  const yamlPattern = projectRoot ? `**/${projectRoot}/**/*.yaml` : "**/*.yaml";
  const clientOptions: LanguageClientOptions = {
    documentSelector: [{ language: "xbsl" }, { language: "yaml", pattern: yamlPattern }],
    outputChannel: output,
    diagnosticCollectionName: "xbsl-lsp",
  };

  client = new LanguageClient("xbslLsp", "XBSL LSP", serverOptions, clientOptions);
  try {
    await client.start();
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    output.appendLine(vscode.l10n.t('XBSL LSP: the server failed to start ({0}): {1}', plan.command, msg));
    void vscode.window.showErrorMessage(
      vscode.l10n.t(
        'XBSL: failed to start xbsllint-lsp. Install the linter with the [lsp] extra (pip install "xbsllint[lsp]") or set the command in the xbsl.lsp.command setting. The extension keeps working in the regular mode (CLI).'
      )
    );
    client = undefined;
    return false;
  }
  output.appendLine(vscode.l10n.t('XBSL LSP: server started ({0} {1}).', plan.command, args.join(" ")));

  context.subscriptions.push(
    { dispose: () => void client?.stop() },
    // Команды сохраняют привычные идентификаторы и в LSP-режиме.
    vscode.commands.registerCommand("xbsl.restartLinter", async () => {
      await client?.restart();
      void vscode.window.setStatusBarMessage(vscode.l10n.t("XBSL LSP: server restarted"), 3000);
    }),
    vscode.commands.registerCommand("xbsl.lintProject", () => {
      void vscode.window.showInformationMessage(
        vscode.l10n.t(
          'XBSL LSP: project-wide diagnostics run on the server on every save; force them with the "XBSL: restart the linter" command.'
        )
      );
    })
  );
  return true;
}
