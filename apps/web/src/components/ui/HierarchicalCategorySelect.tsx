"use client";

import { useMemo } from "react";
import { categoryChoices, categoryPath } from "@/lib/category-hierarchy";
import { SearchableSelect } from "./SearchableSelect";

/** Search whole breadcrumbs and select an observed path or one of its parents. */
export function HierarchicalCategorySelect({
  label = "Categoría", value, paths, onChange, emptyLabel = "Todas las categorías", loading = false, className = "",
}: {
  label?: string;
  value: string;
  paths: string[];
  onChange: (path: string) => void;
  emptyLabel?: string;
  loading?: boolean;
  className?: string;
}) {
  const options = useMemo(() => categoryChoices(paths).map((choice) => ({
    ...choice,
    hierarchy: { depth: choice.depth, leaf: choice.leaf, parentPath: choice.parentPath, children: choice.children },
  })), [paths]);
  return <SearchableSelect
    className={className}
    label={label}
    placeholder="Busca categoría o subcategoría…"
    emptyLabel={emptyLabel}
    value={categoryPath(value)}
    selectedLabel={categoryPath(value)}
    options={options}
    onChange={onChange}
    loading={loading}
  />;
}
