"use client";

import { useId, useMemo, useState, type ReactNode } from "react";
import { SearchBox, type SearchOption } from "./SearchBox";
import styles from "./SearchableSelect.module.css";

/** An exact-ID choice control backed by the shared searchable combobox. */
export function SearchableSelect({
  label,
  value,
  options,
  onChange,
  placeholder,
  loading = false,
  error = false,
  emptyLabel,
  selectedLabel,
  selectionActions,
  allowClear = true,
  className = "",
}: {
  label: string;
  value: string;
  options: SearchOption[];
  onChange: (id: string) => void;
  placeholder?: string;
  loading?: boolean;
  error?: boolean;
  emptyLabel?: string;
  selectedLabel?: string;
  selectionActions?: ReactNode;
  allowClear?: boolean;
  className?: string;
}) {
  const selected = useMemo(
    () => options.find((option) => option.id === value),
    [options, value],
  );
  const labelForValue = selected?.label || selectedLabel || "Selección no disponible";
  const [query, setQuery] = useState("");
  const selectedStatusId = useId();

  return (
    <div className={`form-field searchable-select ${className}`.trim()} role="group" aria-label={label} data-selected-value={value}>
      <span>{label}</span>
      <SearchBox
        label={label}
        placeholder={placeholder || emptyLabel || `Busca ${label.toLowerCase()}`}
        value={query}
        onChange={setQuery}
        options={options}
        onSelect={(option) => {
          setQuery("");
          onChange(option.id);
        }}
        replaceValueOnSelect={false}
        loading={loading}
        error={error}
        descriptionId={selectedStatusId}
      />
      {value ? (
        <div id={selectedStatusId} className={styles.selected} role="status">
          <span>Seleccionado: <strong>{labelForValue}</strong>
            {selected?.detail ? ` · ${selected.detail}` : ""}
          </span>
          {allowClear && (
            <button type="button" onClick={() => { setQuery(""); onChange(""); }}>
              Quitar selección
            </button>
          )}
        </div>
      ) : emptyLabel ? (
        <small id={selectedStatusId}>{emptyLabel}</small>
      ) : (
        <small id={selectedStatusId}>Ninguna selección aplicada</small>
      )}
      {selected && selectionActions && (
        <div className={styles.actions}>{selectionActions}</div>
      )}
      {value && !selected && !loading && !selectedLabel && (
        <small role="status">
          La opción guardada no está en la lista actual. Busca otra opción o borra la selección.
        </small>
      )}
    </div>
  );
}
