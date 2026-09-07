"use client";
import { useId } from "react";
import { IoPricetagOutline, IoCubeOutline } from "react-icons/io5";
export type InformationMode = "price" | "supply";
export function DetailTabs({
  mode,
  onChange,
}: {
  mode: InformationMode;
  onChange: (mode: InformationMode) => void;
}) {
  const id = useId();
  return (
    <div
      className="information-tabs"
      role="tablist"
      aria-label="Información del detalle"
    >
      {(
        [
          ["price", "Precios", IoPricetagOutline],
          ["supply", "Abastecimiento", IoCubeOutline],
        ] as const
      ).map(([value, label, Icon]) => (
        <button
          type="button"
          key={value}
          id={`${id}-${value}`}
          role="tab"
          aria-selected={mode === value}
          onClick={() => onChange(value)}
        >
          <Icon />
          {label}
        </button>
      ))}
    </div>
  );
}
