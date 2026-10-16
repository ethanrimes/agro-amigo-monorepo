import { normalizeLabel } from "./label-normalization";
import { fold } from "./planning-math";

/** Only an explicit source path separator establishes a parent relationship. */
export function categoryParts(value: string): string[] {
  return value.split(/\s*>\s*/).map((part) => normalizeLabel(part.trim(), "category")).filter(Boolean);
}

export function categoryPath(value: string): string {
  return categoryParts(value).join(" > ");
}

/** Preserve explicit city classifications rather than reducing them to a parent. */
export function productCategoryPaths(product: { category: string; category_paths?: string[][] }): string[] {
  return product.category_paths?.length
    ? product.category_paths.map((path) => path.join(" > "))
    : [product.category];
}

function exactPart(value: string): string {
  return value.toLocaleLowerCase("es").replace(/[áéíóúü]/gu, (letter) => ({
    á: "a", é: "e", í: "i", ó: "o", ú: "u", ü: "u",
  })[letter]!);
}

/** A parent includes only descendants explicitly present under that path. */
export function categoryMatches(source: string, selected: string): boolean {
  if (!selected || selected === "Todos") return true;
  const parts = categoryParts(source), choice = categoryParts(selected);
  return choice.length > 0 && choice.length <= parts.length &&
    choice.every((part, index) => fold(part) === fold(parts[index]));
}

export function categoryChoices(sourcePaths: string[]): {
  id: string; label: string; detail: string; depth: number; leaf: string; parentPath: string; children: boolean;
}[] {
  const choices = new Map<string, { id: string; label: string; depth: number; children: boolean; leaf: string; parentPath: string }>();
  for (const source of sourcePaths) {
    const parts = categoryParts(source);
    for (let depth = 1; depth <= parts.length; depth++) {
      const id = parts.slice(0, depth).join(" > ");
      const key = parts.slice(0, depth).map(exactPart).join(" > ");
      const previous = choices.get(key);
      choices.set(key, { id, label: id, depth, leaf: parts[depth - 1],
        parentPath: parts.slice(0, depth - 1).join(" > "),
        children: Boolean(previous?.children || depth < parts.length) });
    }
  }
  return [...choices.values()].sort((a, b) => a.label.localeCompare(b.label, "es"))
    .map(({ id, label, depth, leaf, parentPath, children }) => ({
      id, label, depth, leaf, parentPath, children,
      detail: children ? "Incluye las subcategorías de esta ruta" : depth > 1 ? "Subcategoría" : "Categoría principal",
    }));
}
