// Вид "Документация" на панели действий 1С:Элемент: дерево "Содержание" справки Элемента
// (разделы -> типы -> члены) плюс команды поиска, открытия страницы и показа документации по
// символу под курсором. Данные приходят от LSP-сервера линтера (docsClient), страницы
// показывает docsPanel. Дерево строится из плоского списка узлов (id, parent) один раз и
// перечитывается по кнопке обновления.

import * as vscode from "vscode";
import { DocNode, docsSearch, docsTree } from "./docsClient";
import { openForSymbol, openPage } from "./docsPanel";

const KIND_ICON: Record<string, string> = {
  type: "symbol-class",
  method: "symbol-method",
  annotation: "symbol-property",
  member: "symbol-field",
};

class DocsTreeProvider implements vscode.TreeDataProvider<string> {
  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.changed.event;
  private nodes = new Map<string, DocNode>();
  private children = new Map<string, string[]>();
  private loaded = false;

  refresh(): void {
    this.loaded = false;
    this.changed.fire();
  }

  private async ensure(): Promise<void> {
    if (this.loaded) {
      return;
    }
    this.nodes.clear();
    this.children.clear();
    for (const n of await docsTree()) {
      this.nodes.set(n.id, n);
      const bucket = this.children.get(n.parent);
      if (bucket) {
        bucket.push(n.id);
      } else {
        this.children.set(n.parent, [n.id]);
      }
    }
    this.loaded = true;
  }

  async getChildren(element?: string): Promise<string[]> {
    await this.ensure();
    return this.children.get(element ?? "") ?? [];
  }

  getTreeItem(id: string): vscode.TreeItem {
    const node = this.nodes.get(id);
    const hasChildren = (this.children.get(id) ?? []).length > 0;
    const item = new vscode.TreeItem(
      node?.title ?? id,
      hasChildren ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None
    );
    item.iconPath = new vscode.ThemeIcon(KIND_ICON[node?.kind ?? "member"] ?? "symbol-field");
    item.command = { command: "xbsl.docs.open", title: "", arguments: [id] };
    return item;
  }
}

// Поиск по документации: строка запроса -> ранжированные попадания -> выбор -> открытие страницы.
async function searchDocs(context: vscode.ExtensionContext): Promise<void> {
  const query = await vscode.window.showInputBox({
    prompt: vscode.l10n.t("Search the Element documentation"),
    placeHolder: vscode.l10n.t("method, property, type ..."),
  });
  if (!query) {
    return;
  }
  const hits = await docsSearch(query, 30);
  if (hits.length === 0) {
    void vscode.window.showInformationMessage(vscode.l10n.t('XBSL: nothing found for "{0}".', query));
    return;
  }
  const pick = await vscode.window.showQuickPick(
    hits.map((h) => ({
      label: h.title,
      description: h.qualified,
      detail: h.snippet || undefined,
      id: h.id,
    })),
    { placeHolder: vscode.l10n.t("Open a documentation page"), matchOnDescription: true, matchOnDetail: true }
  );
  if (pick) {
    await openPage(context, pick.id);
  }
}

export function registerDocs(context: vscode.ExtensionContext): void {
  const provider = new DocsTreeProvider();
  context.subscriptions.push(
    vscode.window.createTreeView("xbslDocs", { treeDataProvider: provider }),
    vscode.commands.registerCommand("xbsl.docs.open", (id: string) => openPage(context, id)),
    vscode.commands.registerCommand("xbsl.docs.search", () => searchDocs(context)),
    vscode.commands.registerCommand("xbsl.docs.showForSymbol", () => openForSymbol(context)),
    vscode.commands.registerCommand("xbsl.docs.refresh", () => provider.refresh())
  );
}
