// Unit tests for the pure form-structure core (src/formStructureCore.ts). No test runner and
// no vscode: plain Node asserts, bundled by esbuild. Run with `npm test` from editors/vscode.

import * as assert from "assert";
import {
  decodePaletteDrag,
  decodeStructureDrag,
  dropPlan,
  editsOverlap,
  encodePaletteDrag,
  encodeStructureDrag,
  FormNode,
  indexTree,
  insertPlanForSelection,
  isContainerNode,
  isDescendantOf,
  nodeDescription,
  nodeIconId,
  nodeLabel,
  planRemoval,
  projectDiagnostics,
  remapIds,
  ROOT_ID,
  siblingInfo,
  validMoveTarget,
  visibleWithNamedFilter,
} from "../src/formStructureCore";

let failed = 0;
let passed = 0;

function test(name: string, fn: () => void): void {
  try {
    fn();
    passed++;
    console.log(`ok   ${name}`);
  } catch (e) {
    failed++;
    console.error(`FAIL ${name}`);
    console.error(e instanceof Error ? e.message : e);
  }
}

// --- fixture builders (the shapes the engine's node_dict emits) ---------------------------

function comp(
  id: string,
  type: string | null,
  name: string | null,
  span: [number, number],
  children: FormNode[] = [],
  properties: Array<{ key: string; kind: string; valuePreview: string }> = []
): FormNode {
  return {
    id,
    kind: "component",
    span: { start: span[0], end: span[1] },
    type,
    typeFull: type,
    name,
    slot: null,
    properties,
    children,
  };
}

function slot(id: string, name: string, span: [number, number], children: FormNode[]): FormNode {
  return { id, kind: "slot", span: { start: span[0], end: span[1] }, name, list: true, children };
}

// Наследует
//   Содержимое
//     [0] Группа Шапка
//         Содержимое
//           [0] Надпись Заголовок
//           [1] Кнопка (unnamed)
//     [1] ПолеВвода Поиск
//   Подвал
//     [0] Кнопка (unnamed)
const LABEL = comp(
  "Наследует/Содержимое[0]/Содержимое[0]",
  "Надпись",
  "Заголовок",
  [40, 100],
  [],
  [{ key: "Заголовок", kind: "scalar", valuePreview: "О сервисе" }]
);
const BUTTON = comp("Наследует/Содержимое[0]/Содержимое[1]", "Кнопка", null, [100, 190]);
const INNER_SLOT = slot("Наследует/Содержимое[0]/Содержимое", "Содержимое", [30, 190], [LABEL, BUTTON]);
const GROUP = comp("Наследует/Содержимое[0]", "Группа", "Шапка", [20, 200], [INNER_SLOT]);
const FIELD = comp("Наследует/Содержимое[1]", "ПолеВвода", "Поиск", [200, 300]);
const CONTENT_SLOT = slot("Наследует/Содержимое", "Содержимое", [10, 300], [GROUP, FIELD]);
const FOOTER_BUTTON = comp("Наследует/Подвал[0]", "Кнопка", null, [310, 400]);
const FOOTER_SLOT = slot("Наследует/Подвал", "Подвал", [300, 400], [FOOTER_BUTTON]);
const ROOT = comp(ROOT_ID, "Форма", null, [0, 500], [CONTENT_SLOT, FOOTER_SLOT]);
const INDEX = indexTree(ROOT);

// --- indexing -----------------------------------------------------------------------------

test("indexTree collects every node with its parent", () => {
  assert.strictEqual(INDEX.byId.size, 9);
  assert.strictEqual(INDEX.parentOf.get(LABEL.id), INNER_SLOT.id);
  assert.strictEqual(INDEX.parentOf.get(INNER_SLOT.id), GROUP.id);
  assert.strictEqual(INDEX.parentOf.get(ROOT_ID), undefined);
});

test("isDescendantOf walks the parent chain (self included)", () => {
  assert.ok(isDescendantOf(INDEX, LABEL.id, GROUP.id));
  assert.ok(isDescendantOf(INDEX, GROUP.id, GROUP.id));
  assert.ok(!isDescendantOf(INDEX, FIELD.id, GROUP.id));
});

// --- labels and icons ---------------------------------------------------------------------

test("labels combine the type and the name; slots show the key", () => {
  assert.strictEqual(nodeLabel(GROUP), "Группа Шапка");
  assert.strictEqual(nodeLabel(BUTTON), "Кнопка");
  assert.strictEqual(nodeLabel(INNER_SLOT), "Содержимое");
});

test("descriptions: property preview for components, child count for slots", () => {
  assert.strictEqual(nodeDescription(LABEL), "О сервисе");
  assert.strictEqual(nodeDescription(BUTTON), "");
  assert.strictEqual(nodeDescription(CONTENT_SLOT), "2");
});

test("icons by kind: root, slot, container, leaf", () => {
  assert.strictEqual(nodeIconId(ROOT), "window");
  assert.strictEqual(nodeIconId(INNER_SLOT), "layers");
  assert.strictEqual(nodeIconId(GROUP), "layout"); // has a slot child
  assert.strictEqual(nodeIconId(BUTTON), "symbol-field");
  // A schema-known container without slot children yet is painted as a container too.
  const emptyCard = comp("x", "СпецКарточка", null, [0, 1]);
  assert.strictEqual(nodeIconId(emptyCard, (t) => t === "СпецКарточка"), "layout");
});

test("container detection: slot children, the known list, the schema callback", () => {
  assert.ok(isContainerNode(GROUP));
  assert.ok(isContainerNode(comp("x", "Группа", null, [0, 1]))); // known type, no slots yet
  assert.ok(!isContainerNode(BUTTON));
  assert.ok(!isContainerNode(INNER_SLOT)); // a slot is not a component
});

// --- drop and insert planning -------------------------------------------------------------

test("drop on a container goes inside, to the slot end", () => {
  const plan = dropPlan(GROUP, INDEX);
  assert.deepStrictEqual(plan, { parentId: GROUP.id, slot: "Содержимое" });
});

test("drop on a leaf lands right after it", () => {
  const plan = dropPlan(LABEL, INDEX);
  assert.deepStrictEqual(plan, { parentId: GROUP.id, slot: "Содержимое", after: LABEL.id });
});

test("drop on a slot goes into that slot", () => {
  const plan = dropPlan(FOOTER_SLOT, INDEX);
  assert.deepStrictEqual(plan, { parentId: ROOT_ID, slot: "Подвал" });
});

test("drop on the root goes into the root content slot", () => {
  const plan = dropPlan(ROOT, INDEX);
  assert.deepStrictEqual(plan, { parentId: ROOT_ID, slot: "Содержимое" });
});

test("palette insertion targets the selection (empty selection - the root)", () => {
  assert.deepStrictEqual(insertPlanForSelection(undefined, INDEX), { parentId: ROOT_ID, slot: "Содержимое" });
  assert.deepStrictEqual(insertPlanForSelection(FIELD, INDEX), {
    parentId: ROOT_ID,
    slot: "Содержимое",
    after: FIELD.id,
  });
  assert.deepStrictEqual(insertPlanForSelection(GROUP, INDEX), { parentId: GROUP.id, slot: "Содержимое" });
});

test("a move into a dragged subtree is rejected", () => {
  assert.ok(!validMoveTarget(INDEX, [GROUP.id], LABEL.id)); // target inside the dragged node
  assert.ok(!validMoveTarget(INDEX, [GROUP.id], GROUP.id));
  assert.ok(validMoveTarget(INDEX, [GROUP.id], FIELD.id));
  assert.ok(!validMoveTarget(INDEX, [GROUP.id], "нет-такого"));
});

test("siblingInfo reports the slot, the parent component and the neighbours", () => {
  const info = siblingInfo(LABEL, INDEX);
  assert.strictEqual(info?.parentId, GROUP.id);
  assert.strictEqual(info?.slot, "Содержимое");
  assert.strictEqual(info?.prev, undefined);
  assert.strictEqual(info?.next?.id, BUTTON.id);
  const info2 = siblingInfo(FIELD, INDEX);
  assert.strictEqual(info2?.prev?.id, GROUP.id);
  assert.strictEqual(info2?.next, undefined);
});

// --- removal planning ---------------------------------------------------------------------

test("removal drops descendants of selected nodes and orders bottom-up", () => {
  const plan = planRemoval([LABEL.id, GROUP.id, FIELD.id], INDEX);
  assert.deepStrictEqual(plan.ids, [FIELD.id, GROUP.id]); // LABEL is inside GROUP; FIELD is later in text
});

test("removal covering a whole multi-child slot goes sequential", () => {
  const partial = planRemoval([LABEL.id], INDEX);
  assert.strictEqual(partial.sequential, false);
  const whole = planRemoval([LABEL.id, BUTTON.id], INDEX);
  assert.strictEqual(whole.sequential, true);
  // A single-child slot: the engine removes the slot key together with the child in one call.
  const single = planRemoval([FOOTER_BUTTON.id], INDEX);
  assert.deepStrictEqual(single, { ids: [FOOTER_BUTTON.id], sequential: false });
});

test("slots and the root are not removable", () => {
  const plan = planRemoval([INNER_SLOT.id, ROOT_ID], INDEX);
  assert.deepStrictEqual(plan.ids, []);
});

test("editsOverlap detects intersecting spans", () => {
  assert.ok(!editsOverlap([
    { start: 0, end: 10, newText: "" },
    { start: 10, end: 20, newText: "" },
  ]));
  assert.ok(editsOverlap([
    { start: 0, end: 11, newText: "" },
    { start: 10, end: 20, newText: "" },
  ]));
});

// --- diagnostics projection ---------------------------------------------------------------

test("diagnostics land on the deepest containing node", () => {
  const badges = projectDiagnostics(INDEX, [
    { start: 50, severity: 1, message: "первая" },
    { start: 60, severity: 0, message: "вторая" },
    { start: 250, severity: 2, message: "поле" },
    { start: 5, severity: 3, message: "корень" }, // inside the root, outside every slot
    { start: 600, severity: 0, message: "вне дерева" },
  ]);
  const label = badges.get(LABEL.id);
  assert.strictEqual(label?.count, 2);
  assert.strictEqual(label?.severity, 0); // the strongest of warning + error
  assert.strictEqual(label?.firstMessage, "первая");
  assert.strictEqual(badges.get(FIELD.id)?.count, 1);
  assert.strictEqual(badges.get(ROOT_ID)?.count, 1);
  assert.strictEqual(badges.size, 3);
});

// --- named-only filter --------------------------------------------------------------------

test("the named filter keeps named components with their ancestor chain", () => {
  const visible = visibleWithNamedFilter(INDEX);
  assert.ok(visible.has(LABEL.id)); // named
  assert.ok(visible.has(INNER_SLOT.id)); // ancestor of a named node
  assert.ok(visible.has(GROUP.id));
  assert.ok(visible.has(FIELD.id));
  assert.ok(visible.has(ROOT_ID));
  assert.ok(!visible.has(BUTTON.id)); // unnamed leaf
  assert.ok(!visible.has(FOOTER_SLOT.id)); // no named descendants
  assert.ok(!visible.has(FOOTER_BUTTON.id));
});

// --- expansion remapping ------------------------------------------------------------------

test("expansion survives positional id shifts via unique names", () => {
  // The same form after inserting a new first child: every index under Содержимое shifted.
  const label2 = comp(
    "Наследует/Содержимое[1]/Содержимое[0]",
    "Надпись",
    "Заголовок",
    [140, 200],
    [],
    []
  );
  const innerSlot2 = slot("Наследует/Содержимое[1]/Содержимое", "Содержимое", [130, 290], [label2]);
  const group2 = comp("Наследует/Содержимое[1]", "Группа", "Шапка", [120, 300], [innerSlot2]);
  const inserted = comp("Наследует/Содержимое[0]", "Надпись", null, [20, 120]);
  const field2 = comp("Наследует/Содержимое[2]", "ПолеВвода", "Поиск", [300, 400]);
  const content2 = slot("Наследует/Содержимое", "Содержимое", [10, 400], [inserted, group2, field2]);
  const root2 = comp(ROOT_ID, "Форма", null, [0, 500], [content2]);
  const newIndex = indexTree(root2);

  const remapped = remapIds([ROOT_ID, GROUP.id, INNER_SLOT.id, FIELD.id, BUTTON.id], INDEX, newIndex);
  assert.ok(remapped.has(ROOT_ID)); // untouched id
  assert.ok(remapped.has(group2.id)); // followed the unique name Шапка
  assert.ok(remapped.has(innerSlot2.id)); // slot re-attached to the remapped parent
  assert.ok(remapped.has(field2.id)); // followed Поиск
  assert.strictEqual(remapped.size, 4); // the unnamed Кнопка is not traceable
});

// --- drag payloads ------------------------------------------------------------------------

test("drag payloads round-trip and reject foreign data", () => {
  const structure = encodeStructureDrag({ uri: "file:///a.yaml", ids: [GROUP.id] });
  assert.deepStrictEqual(decodeStructureDrag(structure), { uri: "file:///a.yaml", ids: [GROUP.id] });
  assert.strictEqual(decodeStructureDrag("мусор"), undefined);
  assert.strictEqual(decodeStructureDrag('{"uri": 5, "ids": []}'), undefined);

  const palette = encodePaletteDrag({ componentType: "Надпись" });
  assert.deepStrictEqual(decodePaletteDrag(palette), { componentType: "Надпись" });
  assert.strictEqual(decodePaletteDrag("{}"), undefined);
  assert.strictEqual(decodePaletteDrag("мусор"), undefined);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) {
  process.exit(1);
}
