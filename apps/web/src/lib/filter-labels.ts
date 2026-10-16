/** Known spellings in retained DANE originals; quote labels remain literal. */
const departmentAliases: Record<string, string[]> = {
  "bolívar": ["Bolívar", "Bolivar"],
  "córdoba": ["Córdoba", "Cordoba"],
  "quindío": ["Quindío", "Quindio"],
  "bogotá, d.c.": ["Bogotá, D.C.", "Bogotá D.C.", "Bogotá, D. C."],
};
const literalDepartmentKey = (value: string) => value.trim().toLocaleLowerCase("es");
export function departmentKey(value: string): string {
  const key = literalDepartmentKey(value);
  return Object.entries(departmentAliases).find(([, aliases]) =>
    aliases.some((alias) => literalDepartmentKey(alias) === key),
  )?.[0] || key;
}

export const categoryKey = (value: string) => departmentKey(value)
  .normalize("NFD").replace(/[\u0300-\u036f]/g, "");

export function departmentLabel(value: string): string {
  return departmentKey(value).split(" ").map((word, index) =>
    index && ["de", "del", "la", "el", "y"].includes(word)
      ? word : word.slice(0, 1).toLocaleUpperCase("es") + word.slice(1),
  ).join(" ").replace(/\bd\.c\./gi, "D.C.");
}

export function departmentLabels(values: string[]): string[] {
  return [...new Set(values.filter((value) => value.trim()).map(departmentLabel))]
    .sort((a, b) => a.localeCompare(b, "es"));
}

/** Keep indexed equality reads across the source's retained case spellings. */
export function departmentVariants(value: string): string[] {
  const literal = value.trim();
  if (!literal) return [];
  const label = departmentLabel(literal);
  const aliases = departmentAliases[departmentKey(literal)] || [];
  const variants = [literal, label, ...aliases].flatMap((alias) => [alias,
    alias.split(" ").map((word) => word.slice(0, 1).toLocaleUpperCase("es") + word.slice(1)).join(" "),
    alias.toLocaleUpperCase("es"), alias.toLocaleLowerCase("es")]);
  return [...new Set(variants)];
}

export function categoryLabels(values: string[]): string[] {
  const labels = new Map<string, { label: string; priority: number }>();
  for (const value of values) {
    const label = value.trim();
    if (!label) continue;
    const key = categoryKey(label);
    const previous = labels.get(key);
    // Keep accents from the original and display uppercase headings in sentence case.
    const uppercase = label === label.toLocaleUpperCase("es");
    const priority = (/[\u0300-\u036f]/.test(label.normalize("NFD")) ? 2 : 0) + (uppercase ? 0 : 1);
    const display = uppercase ? label.toLocaleLowerCase("es") : label;
    if (!previous || priority > previous.priority)
      labels.set(key, { label: display.slice(0, 1).toLocaleUpperCase("es") + display.slice(1), priority });
  }
  return [...labels.values()].map(({ label }) => label).sort((a, b) => a.localeCompare(b, "es"));
}
