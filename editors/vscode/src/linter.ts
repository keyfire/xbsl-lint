import * as vscode from "vscode";
import { spawn } from "child_process";
import {
  buildArgs,
  buildPathArgs,
  computeRange,
  LinterConfig,
  parseReport,
  RawDiag,
  RawReport,
  severityCode,
} from "./report";

export interface RunResult {
  report?: RawReport;
  // A human-readable problem (spawn failure, non-JSON output, data error) — shown to the user once.
  error?: string;
}

const DECODER_LIMIT = 8 * 1024 * 1024; // guard against a runaway process

function runProcess(
  command: string,
  args: string[],
  cwd: string | undefined,
  stdin: string | undefined
): Promise<RunResult> {
  return new Promise((resolve) => {
    let child;
    try {
      child = spawn(command, args, { cwd });
    } catch (e) {
      resolve({ error: describeSpawnError(command, e) });
      return;
    }
    let out = "";
    let err = "";
    let tooBig = false;
    child.on("error", (e) => resolve({ error: describeSpawnError(command, e) }));
    child.stdout.on("data", (d: Buffer) => {
      if (out.length < DECODER_LIMIT) {
        out += d.toString("utf8");
      } else {
        tooBig = true;
      }
    });
    child.stderr.on("data", (d: Buffer) => {
      err += d.toString("utf8");
    });
    child.on("close", (code) => {
      if (tooBig) {
        resolve({ error: "linter produced too much output" });
        return;
      }
      // Exit code 1 just means "errors among the diagnostics" — still valid JSON on stdout.
      // A real failure (missing data, crash) leaves stdout empty / non-JSON; surface stderr.
      try {
        resolve({ report: parseReport(out) });
      } catch {
        const detail = (err || out || `exit code ${code}`).trim();
        resolve({ error: detail });
      }
    });
    if (child.stdin) {
      child.stdin.on("error", () => {
        /* ignore EPIPE if the child exits early */
      });
      child.stdin.end(stdin !== undefined ? Buffer.from(stdin, "utf8") : undefined);
    }
  });
}

function describeSpawnError(command: string, e: unknown): string {
  const err = e as NodeJS.ErrnoException;
  if (err && err.code === "ENOENT") {
    return `не найден исполняемый файл линтера "${command}". Установите xbsllint (pip install xbsllint) или задайте xbsl.linter.command / xbsl.linter.pythonPath.`;
  }
  return `не удалось запустить линтер "${command}": ${err && err.message ? err.message : String(e)}`;
}

// Check one buffer via `xbsllint --stdin` (per-file rules only).
export function lintBuffer(
  text: string,
  filename: string,
  cwd: string | undefined,
  cfg: LinterConfig
): Promise<RunResult> {
  return runProcess(cfg.command, buildArgs(filename, cfg), cwd, text);
}

// Check a whole path on disk via `xbsllint <path>` (includes cross-file rules).
export function lintPath(target: string, cwd: string | undefined, cfg: LinterConfig): Promise<RunResult> {
  return runProcess(cfg.command, buildPathArgs(target, cfg), cwd, undefined);
}

// Builds a diagnostic; lineText (when known) lets us widen the anchor to the word under it.
export function makeDiagnostic(d: RawDiag, lineText: string | undefined): vscode.Diagnostic {
  const span = computeRange(lineText, d.line, d.col);
  const range = new vscode.Range(span.sl, span.sc, span.el, span.ec);
  const diag = new vscode.Diagnostic(range, d.message, severityCode(d.severity));
  diag.source = "xbsllint";
  diag.code = d.rule;
  return diag;
}

export function toDiagnostic(d: RawDiag, doc: vscode.TextDocument): vscode.Diagnostic {
  const li = Math.min(Math.max(0, d.line - 1), Math.max(0, doc.lineCount - 1));
  const lineText = doc.lineCount > 0 ? doc.lineAt(li).text : undefined;
  return makeDiagnostic(d, lineText);
}
