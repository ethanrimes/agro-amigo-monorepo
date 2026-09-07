"use client";
import { useId, useMemo, useRef, useState } from "react";
import {
  IoSearchOutline,
  IoCloseOutline,
  IoArrowForward,
} from "react-icons/io5";
import { fold } from "@/lib/planning-math";
export type SearchOption = { id: string; label: string; detail?: string };
/** A shared, keyboard-accessible search with accent-insensitive suggestions. */
export function SearchBox({
  label,
  placeholder,
  value,
  onChange,
  options,
  onSelect,
  onSubmit,
}: {
  label: string;
  placeholder?: string;
  value: string;
  onChange: (value: string) => void;
  options: SearchOption[];
  onSelect?: (option: SearchOption) => void;
  onSubmit?: () => void;
}) {
  const id = useId(),
    input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false),
    [active, setActive] = useState(-1);
  const matches = useMemo(
    () =>
      options
        .filter((o) =>
          fold(o.label + " " + (o.detail || "")).includes(fold(value)),
        )
        .slice(0, 8),
    [options, value],
  );
  const select = (option: SearchOption) => {
    onChange(option.label);
    setOpen(false);
    setActive(-1);
    onSelect?.(option);
  };
  return (
    <div
      className="search-combo"
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false);
      }}
    >
      <div className="search-field">
        <IoSearchOutline aria-hidden="true" />
        <input
          ref={input}
          role="combobox"
          aria-label={label}
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={id}
          aria-activedescendant={
            open && active >= 0 && matches[active]
              ? `${id}-${active}`
              : undefined
          }
          placeholder={placeholder || label}
          value={value}
          autoComplete="off"
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            onChange(e.target.value);
            setOpen(true);
            setActive(-1);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              setOpen(true);
              setActive((i) =>
                matches.length
                  ? (i + (e.key === "ArrowDown" ? 1 : -1) + matches.length) %
                    matches.length
                  : -1,
              );
            }
            if (e.key === "Escape") {
              e.stopPropagation();
              setOpen(false);
              setActive(-1);
            }
            if (e.key === "Enter") {
              e.preventDefault();
              if (open && active >= 0 && matches[active])
                select(matches[active]);
              else {
                setOpen(false);
                onSubmit?.();
              }
            }
          }}
        />
        {value && (
          <button
            type="button"
            aria-label={`Borrar ${label.toLowerCase()}`}
            onClick={() => {
              onChange("");
              setActive(-1);
              input.current?.focus();
            }}
          >
            <IoCloseOutline />
          </button>
        )}
        {onSubmit && (
          <button
            type="button"
            aria-label="Ver resultados"
            onClick={() => {
              setOpen(false);
              onSubmit();
            }}
          >
            <IoArrowForward />
          </button>
        )}
      </div>
      {open && (
        <div
          className="search-suggestions"
          id={id}
          role="listbox"
          aria-label={`Sugerencias: ${label}`}
        >
          {matches.map((o, i) => (
            <button
              type="button"
              role="option"
              id={`${id}-${i}`}
              aria-selected={i === active}
              key={o.id}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => select(o)}
            >
              <span>{o.label}</span>
              {o.detail && <small>{o.detail}</small>}
            </button>
          ))}
          {!matches.length && (
            <p role="status">Sin coincidencias. Prueba otro nombre.</p>
          )}
        </div>
      )}
    </div>
  );
}
