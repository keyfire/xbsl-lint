// Thin cached client of the engine's xbsl/metadataSchema request - the metadata counterpart of
// uiSchemaClient. It answers "which properties may an element of this kind have", so the
// properties panel can offer the ones a file does not set yet (Представление, Иерархический,
// ВводПоСтроке ... of a Справочник). The engine is the only source: names, types, defaults and
// enumeration values all come from the platform metamodel. Everything degrades to "no schema"
// when the LSP server is down or the dataset has no generated metamodel - the panel then shows
// the set properties alone, exactly as before.

import { lspRequest } from "./lspClient";
import { MetaSchema } from "./propsModes";

interface MetaSchemaResponse {
  available?: boolean;
  kind?: string;
  class?: string;
  props?: MetaSchema["props"];
  enums?: Record<string, string[]>;
}

const cache = new Map<string, MetaSchema | undefined>();

export function resetMetaSchemaCache(): void {
  cache.clear();
}

// The schema of one element kind (ВидЭлемента), or undefined when unavailable. Cached for the
// session: the metamodel is generated data, it does not change while the editor runs.
export async function metaSchema(kind: string): Promise<MetaSchema | undefined> {
  if (cache.has(kind)) {
    return cache.get(kind);
  }
  const res = await lspRequest<MetaSchemaResponse>("xbsl/metadataSchema", { kind });
  const props = res?.available ? res.props : undefined;
  const schema = props && Object.keys(props).length
    ? { kind, props, enums: res?.enums ?? {} }
    : undefined;
  cache.set(kind, schema);
  return schema;
}
