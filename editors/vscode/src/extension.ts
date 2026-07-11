import * as vscode from "vscode";
import * as path from "path";
import { LinterConfig } from "./report";
import { lintBuffer, lintPath, makeDiagnostic, toDiagnostic } from "./linter";
import { registerNavigation } from "./navigation";

let collection: vscode.DiagnosticCollection;
let output: vscode.OutputChannel;
const debounceTimers = new Map<string, NodeJS.Timeout>();
let warnedOnce = false;

interface Settings {
  linter: LinterConfig;
  run: "onType" | "onSave" | "off";
  debounce: number;
}

function readSettings(resource?: vscode.Uri): Settings {
  const c = vscode.workspace.getConfiguration("xbsl", resource ?? null);
  const python = (c.get<string>("linter.pythonPath") || "").trim();
  const command = (c.get<string>("linter.command") || "xbsllint").trim();
  const lang = (c.get<string>("linter.lang") || "").trim();
  return {
    linter: {
      command: python || command,
      usePython: python.length > 0,
      dataDir: (c.get<string>("linter.dataDir") || "").trim() || undefined,
      lang: lang || undefined,
      select: (c.get<string>("linter.select") || "").trim() || undefined,
      ignore: (c.get<string>("linter.ignore") || "").trim() || undefined,
    },
    run: c.get<"onType" | "onSave" | "off">("linter.run") || "onType",
    debounce: c.get<number>("linter.debounce") ?? 300,
  };
}

function cwdFor(uri: vscode.Uri): string | undefined {
  const folder = vscode.workspace.getWorkspaceFolder(uri);
  if (folder) {
    return folder.uri.fsPath;
  }
  return uri.scheme === "file" ? path.dirname(uri.fsPath) : undefined;
}

async function lintDocument(doc: vscode.TextDocument): Promise<void> {
  if (doc.languageId !== "xbsl") {
    return;
  }
  const settings = readSettings(doc.uri);
  const filename = doc.uri.scheme === "file" ? path.basename(doc.uri.fsPath) : "buffer.xbsl";
  const version = doc.version;
  const result = await lintBuffer(doc.getText(), filename, cwdFor(doc.uri), settings.linter);
  if (result.error) {
    reportProblem(result.error);
    return;
  }
  // Drop a stale result: the buffer changed while the linter was running.
  if (doc.version !== version) {
    return;
  }
  const diags = (result.report?.diagnostics ?? []).map((d) => toDiagnostic(d, doc));
  collection.set(doc.uri, diags);
}

function reportProblem(message: string): void {
  output.appendLine(message);
  if (!warnedOnce) {
    warnedOnce = true;
    void vscode.window.showErrorMessage(`XBSL: ${message}`, "Показать журнал").then((pick) => {
      if (pick) {
        output.show(true);
      }
    });
  }
}

function scheduleLint(doc: vscode.TextDocument, delay: number): void {
  const key = doc.uri.toString();
  const prev = debounceTimers.get(key);
  if (prev) {
    clearTimeout(prev);
  }
  debounceTimers.set(
    key,
    setTimeout(() => {
      debounceTimers.delete(key);
      void lintDocument(doc);
    }, delay)
  );
}

async function lintProject(): Promise<void> {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    void vscode.window.showInformationMessage("XBSL: нет открытой папки для проверки.");
    return;
  }
  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Window, title: "XBSL: проверка проекта..." },
    async () => {
      collection.clear();
      for (const folder of folders) {
        const settings = readSettings(folder.uri);
        const result = await lintPath(folder.uri.fsPath, folder.uri.fsPath, settings.linter);
        if (result.error) {
          reportProblem(result.error);
          continue;
        }
        const byFile = new Map<string, vscode.Diagnostic[]>();
        for (const d of result.report?.diagnostics ?? []) {
          const fsPath = path.isAbsolute(d.path) ? d.path : path.resolve(folder.uri.fsPath, d.path);
          const list = byFile.get(fsPath) ?? [];
          list.push(makeDiagnostic(d, undefined));
          byFile.set(fsPath, list);
        }
        for (const [fsPath, diags] of byFile) {
          collection.set(vscode.Uri.file(fsPath), diags);
        }
      }
    }
  );
}

function lintOpenDocuments(): void {
  for (const doc of vscode.workspace.textDocuments) {
    if (doc.languageId === "xbsl") {
      void lintDocument(doc);
    }
  }
}

export function activate(context: vscode.ExtensionContext): void {
  collection = vscode.languages.createDiagnosticCollection("xbsl");
  output = vscode.window.createOutputChannel("XBSL");
  context.subscriptions.push(collection, output);

  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((doc) => {
      if (doc.languageId === "xbsl" && readSettings(doc.uri).run !== "off") {
        void lintDocument(doc);
      }
    }),
    vscode.workspace.onDidChangeTextDocument((e) => {
      const doc = e.document;
      if (doc.languageId !== "xbsl") {
        return;
      }
      const settings = readSettings(doc.uri);
      if (settings.run === "onType") {
        scheduleLint(doc, settings.debounce);
      }
    }),
    vscode.workspace.onDidSaveTextDocument((doc) => {
      if (doc.languageId === "xbsl" && readSettings(doc.uri).run !== "off") {
        void lintDocument(doc);
      }
    }),
    vscode.workspace.onDidCloseTextDocument((doc) => {
      const key = doc.uri.toString();
      const t = debounceTimers.get(key);
      if (t) {
        clearTimeout(t);
        debounceTimers.delete(key);
      }
      collection.delete(doc.uri);
    }),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("xbsl")) {
        warnedOnce = false;
        lintOpenDocuments();
      }
    }),
    vscode.commands.registerCommand("xbsl.lintProject", () => lintProject()),
    vscode.commands.registerCommand("xbsl.restartLinter", () => {
      warnedOnce = false;
      collection.clear();
      lintOpenDocuments();
    })
  );

  registerNavigation(context, output, (resource) => readSettings(resource).linter);

  lintOpenDocuments();
}

export function deactivate(): void {
  for (const t of debounceTimers.values()) {
    clearTimeout(t);
  }
  debounceTimers.clear();
  collection?.dispose();
  output?.dispose();
}
