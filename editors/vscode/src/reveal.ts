// Reveal a document position so a NARROW editor scrolls horizontally to the line's content -
// past the indentation - instead of leaving deeply-indented text off-screen (docs/DESIGNER.md).
// VS Code has no "set horizontal scroll offset" API, but revealRange scrolls horizontally to a
// range; revealing from the first non-whitespace character brings the content into view.

import * as vscode from "vscode";

export function revealContent(editor: vscode.TextEditor, position: vscode.Position): void {
  const line = editor.document.lineAt(position.line);
  const from = new vscode.Position(position.line, line.firstNonWhitespaceCharacterIndex);
  editor.revealRange(
    new vscode.Range(from, line.range.end),
    vscode.TextEditorRevealType.InCenterIfOutsideViewport
  );
}
