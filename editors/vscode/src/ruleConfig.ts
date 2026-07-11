// Пер-правило переопределения из настройки xbsl.rules: ключ – идентификатор правила
// ("whitespace/trailing") или целая группа ("style"), значение – off | error | warning |
// info | hint. "off" скрывает находки и исключает правило из прогона, уровень заменяет
// собственную важность правила. Точное имя сильнее группы. Плюс действие "Настроить
// правило ..." на каждой находке – управление не отходя от строки.

import * as vscode from "vscode";

export type RuleLevel = "off" | "error" | "warning" | "info" | "hint";
const LEVELS: readonly RuleLevel[] = ["error", "warning", "info", "hint", "off"];

function isLevel(v: unknown): v is RuleLevel {
  return typeof v === "string" && (LEVELS as readonly string[]).includes(v);
}

function rulesMap(resource?: vscode.Uri): Record<string, unknown> {
  return vscode.workspace.getConfiguration("xbsl", resource ?? null).get<Record<string, unknown>>("rules") ?? {};
}

// Переопределение для правила: точный ключ, затем группа (часть до "/").
export function ruleOverride(rule: string, resource?: vscode.Uri): RuleLevel | undefined {
  const map = rulesMap(resource);
  const exact = map[rule];
  if (isLevel(exact)) {
    return exact;
  }
  const slash = rule.indexOf("/");
  if (slash > 0) {
    const group = map[rule.slice(0, slash)];
    if (isLevel(group)) {
      return group;
    }
  }
  return undefined;
}

export function severityFor(level: Exclude<RuleLevel, "off">): vscode.DiagnosticSeverity {
  switch (level) {
    case "error":
      return vscode.DiagnosticSeverity.Error;
    case "warning":
      return vscode.DiagnosticSeverity.Warning;
    case "info":
      return vscode.DiagnosticSeverity.Information;
    default:
      return vscode.DiagnosticSeverity.Hint;
  }
}

// Правила со значением off дополняют список ignore линтера – выключенное не запускается.
export function mergeOffRules(ignore: string | undefined, resource?: vscode.Uri): string | undefined {
  const off = Object.entries(rulesMap(resource))
    .filter(([, v]) => v === "off")
    .map(([k]) => k);
  if (off.length === 0) {
    return ignore;
  }
  const base = (ignore ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  return [...new Set([...base, ...off])].join(",");
}

function ruleOf(diag: vscode.Diagnostic): string | undefined {
  if (typeof diag.code === "string") {
    return diag.code;
  }
  if (diag.code && typeof diag.code === "object" && "value" in diag.code) {
    return String(diag.code.value);
  }
  return undefined;
}

// Применяет переопределение к готовой диагностике (LSP-мидлвара): null = скрыть.
export function applyOverride(diag: vscode.Diagnostic, resource?: vscode.Uri): vscode.Diagnostic | null {
  const rule = ruleOf(diag);
  if (!rule) {
    return diag;
  }
  const over = ruleOverride(rule, resource);
  if (!over) {
    return diag;
  }
  if (over === "off") {
    return null;
  }
  diag.severity = severityFor(over);
  return diag;
}

const CONFIGURE_COMMAND = "xbsl.configureRule";

// Пункт "Настроить правило ..." на каждой находке xbsllint (поверх quick-fix-правок).
class ConfigureRuleProvider implements vscode.CodeActionProvider {
  provideCodeActions(
    document: vscode.TextDocument,
    _range: vscode.Range | vscode.Selection,
    context: vscode.CodeActionContext
  ): vscode.CodeAction[] {
    const actions: vscode.CodeAction[] = [];
    const seen = new Set<string>();
    for (const d of context.diagnostics) {
      if (d.source !== "xbsllint") {
        continue;
      }
      const rule = ruleOf(d);
      if (!rule || seen.has(rule)) {
        continue;
      }
      seen.add(rule);
      const action = new vscode.CodeAction(vscode.l10n.t('Configure rule "{0}"...', rule), vscode.CodeActionKind.QuickFix);
      action.diagnostics = [d];
      action.command = {
        command: CONFIGURE_COMMAND,
        title: action.title,
        arguments: [rule, document.uri],
      };
      actions.push(action);
    }
    return actions;
  }
}

async function configureRule(rule: string, resource?: vscode.Uri): Promise<void> {
  const current = ruleOverride(rule, resource);
  type Item = vscode.QuickPickItem & { value: RuleLevel | "default" | "settings" };
  const items: Item[] = [
    {
      label: "$(circle-slash) " + vscode.l10n.t("Disable the rule"),
      description: vscode.l10n.t("hide the findings and skip the rule"),
      value: "off",
    },
    ...(["error", "warning", "info", "hint"] as const).map((level) => ({
      label: "$(" + (level === "error" ? "error" : level === "warning" ? "warning" : "info") + ") " + level,
      description: current === level ? vscode.l10n.t("current override") : undefined,
      value: level as RuleLevel,
    })),
  ];
  if (current) {
    items.push({
      label: "$(discard) " + vscode.l10n.t("Reset the override"),
      description: vscode.l10n.t("back to the rule's own level"),
      value: "default",
    });
  }
  items.push({ label: "$(gear) " + vscode.l10n.t("Open the XBSL rules settings"), value: "settings" });

  const picked = await vscode.window.showQuickPick(items, {
    title: vscode.l10n.t('Rule "{0}"', rule),
    placeHolder: vscode.l10n.t("Choose the level or an action"),
  });
  if (!picked) {
    return;
  }
  if (picked.value === "settings") {
    await vscode.commands.executeCommand("workbench.action.openSettings", "xbsl.rules");
    return;
  }
  const cfg = vscode.workspace.getConfiguration("xbsl", resource ?? null);
  const map = { ...(cfg.get<Record<string, unknown>>("rules") ?? {}) };
  if (picked.value === "default") {
    delete map[rule];
  } else {
    map[rule] = picked.value;
  }
  const target = vscode.workspace.workspaceFolders?.length
    ? vscode.ConfigurationTarget.Workspace
    : vscode.ConfigurationTarget.Global;
  await cfg.update("rules", Object.keys(map).length > 0 ? map : undefined, target);
  void vscode.window.setStatusBarMessage(
    picked.value === "default"
      ? vscode.l10n.t('XBSL: the override of "{0}" is removed', rule)
      : vscode.l10n.t('XBSL: rule "{0}" is set to {1}', rule, picked.value),
    4000
  );
  // Перепроверка тем же привычным механизмом: в CLI-режиме это resetAndRelint,
  // в LSP-режиме – перезапуск сервера (подхватит и off-правила в --ignore).
  void vscode.commands.executeCommand("xbsl.restartLinter");
}

export function registerRuleConfig(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.commands.registerCommand(CONFIGURE_COMMAND, configureRule),
    vscode.languages.registerCodeActionsProvider(
      [{ language: "xbsl" }, { language: "yaml" }],
      new ConfigureRuleProvider(),
      { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix] }
    )
  );
}
