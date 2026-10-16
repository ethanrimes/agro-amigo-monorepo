"use client";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import {
  IoSearchOutline,
  IoCloseOutline,
  IoArrowForward,
} from "react-icons/io5";
import { fold } from "@/lib/planning-math";
export type SearchOption = {
  id: string; label: string; detail?: string; searchText?: string;
  hierarchy?: { depth: number; leaf: string; parentPath: string; children: boolean };
};
/** A shared, keyboard-accessible search with accent-insensitive suggestions. */
export function SearchBox({
  label,
  placeholder,
  value,
  onChange,
  options,
  onSelect,
  onSubmit,
  filterOptions = true,
  replaceValueOnSelect = true,
  loading = false,
  error = false,
  descriptionId,
  paginateOptions = false,
  onMore,
  moreLoading = false,
  moreError = false,
}: {
  label: string;
  placeholder?: string;
  value: string;
  onChange: (value: string) => void;
  options: SearchOption[];
  onSelect?: (option: SearchOption) => void;
  onSubmit?: () => void;
  filterOptions?: boolean;
  replaceValueOnSelect?: boolean;
  loading?: boolean;
  error?: boolean;
  descriptionId?: string;
  paginateOptions?: boolean;
  onMore?: () => void;
  moreLoading?: boolean;
  moreError?: boolean;
}) {
  const id = useId(),
    input = useRef<HTMLInputElement>(null),
    combo = useRef<HTMLDivElement>(null),
    suggestions = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false),
    [active, setActive] = useState(-1),
    [page, setPage] = useState(0),
    [popup, setPopup] = useState({ above: false, maxHeight: 420 });
  // The server-rendered field can appear before React attaches onChange.
  // Enable editing only after hydration so early input cannot be discarded.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  useEffect(() => {
    if (!open) return;
    let frame: number | undefined;
    let revealPending = false;
    const positionSuggestions = (revealFocusedField = false) => {
      const element = combo.current;
      const field = element?.getBoundingClientRect();
      if (!element || !field) return;
      const viewport = window.visualViewport;
      const top = viewport?.offsetTop || 0;
      const bottom = top + (viewport?.height || window.innerHeight);
      const overlay = element.closest('dialog, [role="dialog"], .maplibregl-map');
      const overlayBounds = overlay?.getBoundingClientRect();
      const dialog = element.closest('dialog, [role="dialog"]');
      // Overlay locks body scrolling. Its workspace, rather than window, owns
      // the scroll position; ordinary pages may have a nested scroll owner too.
      let scrollOwner: HTMLElement | null = null;
      for (let ancestor = element.parentElement; ancestor; ancestor = ancestor.parentElement) {
        const overflow = getComputedStyle(ancestor).overflowY;
        if (/^(auto|scroll|overlay)$/.test(overflow) && ancestor.scrollHeight > ancestor.clientHeight + 1) {
          scrollOwner = ancestor;
          break;
        }
        if (ancestor === dialog) break;
      }
      const scrollBounds = scrollOwner?.getBoundingClientRect();
      const visibleTop = Math.max(top, overlayBounds?.top ?? top, scrollBounds?.top ?? top);
      // A fixed mobile navigation bar can cover the lower part of the visual viewport.
      // Reserve its actual on-screen rectangle only when it overlaps this field's column.
      const nav = !overlay ? document.querySelector<HTMLElement>('.mobile-nav') : null;
      const navBounds = nav?.getBoundingClientRect();
      const navTop = navBounds && getComputedStyle(nav!).position === 'fixed'
        && navBounds.width > 0 && navBounds.height > 0
        && navBounds.top < bottom && navBounds.bottom > top
        && navBounds.left < field.right && navBounds.right > field.left
        ? navBounds.top : bottom;
      const visibleBottom = Math.min(bottom, overlayBounds?.bottom ?? bottom,
        scrollBounds?.bottom ?? bottom, navTop);
      // Native keyboard resize may place the fixed bar over the field, or clip
      // a dialog's scrollable workspace. Scroll only the owning container.
      if (revealFocusedField && document.activeElement === input.current
          && field.bottom > visibleBottom - 12 && visibleBottom > visibleTop) {
        const usable = visibleBottom - visibleTop;
        const targetBottom = Math.min(visibleBottom - 12,
          visibleTop + Math.max(field.height + 16, usable * 0.55));
        const delta = field.bottom - targetBottom;
        if (delta > 2) {
          if (scrollOwner) {
            const previous = scrollOwner.scrollTop;
            scrollOwner.scrollBy({ top: delta, behavior: 'instant' });
            if (scrollOwner.scrollTop !== previous) {
              schedule(false);
              return;
            }
          } else if (!dialog) {
            const previous = window.scrollY;
            window.scrollBy({ top: delta, behavior: 'instant' });
            if (window.scrollY !== previous) {
              schedule(false);
              return;
            }
          }
        }
      }
      const availableAbove = field.top - visibleTop - 8;
      const availableBelow = visibleBottom - field.bottom - 8;
      const above = availableBelow < 180 && availableAbove > availableBelow;
      const maxHeight = Math.max(40, Math.min(420, above ? availableAbove : availableBelow));
      setPopup((previous) => previous.above === above && previous.maxHeight === maxHeight
        ? previous : { above, maxHeight });
    };
    const schedule = (reveal: boolean) => {
      revealPending ||= reveal;
      if (frame !== undefined) return;
      frame = window.requestAnimationFrame(() => {
        frame = undefined;
        const shouldReveal = revealPending;
        revealPending = false;
        positionSuggestions(shouldReveal);
      });
    };
    const revealAndPosition = () => schedule(true);
    const positionOnly = () => schedule(false);
    revealAndPosition();
    window.visualViewport?.addEventListener("resize", revealAndPosition);
    // A scroll caused by our own reveal must not start another reveal loop.
    window.visualViewport?.addEventListener("scroll", positionOnly);
    window.addEventListener("resize", revealAndPosition);
    document.addEventListener("scroll", positionOnly, true);
    return () => {
      window.visualViewport?.removeEventListener("resize", revealAndPosition);
      window.visualViewport?.removeEventListener("scroll", positionOnly);
      window.removeEventListener("resize", revealAndPosition);
      document.removeEventListener("scroll", positionOnly, true);
      if (frame !== undefined) window.cancelAnimationFrame(frame);
    };
  }, [open]);
  useEffect(() => {
    if (open && active >= 0) suggestions.current?.children[active]?.scrollIntoView({ block: "nearest" });
  }, [open, active]);
  useEffect(() => { setPage(0); setActive(-1); }, [value]);
  const allMatches = useMemo(
    () => {
      const words = fold(value).trim().split(/\s+/).filter(Boolean);
      return (loading || error ? [] : Array.from(new Map(options.map((option) => [option.id, option])).values()))
        .filter((o) => {
          if (!filterOptions) return true;
          const text = fold(o.searchText ?? (o.label + " " + (o.detail || "")));
          return words.every((word) => /^\d+$/.test(word)
            ? new RegExp("(^|[^0-9])" + word + "([^0-9]|$)").test(text)
            : text.includes(word));
        });
    },
    [options, value, filterOptions, loading, error],
  );
  const currentPage = paginateOptions ? Math.min(page, Math.max(0, Math.ceil(allMatches.length / 8) - 1)) : 0;
  const matches = allMatches.slice(currentPage * 8, currentPage * 8 + 8);
  const changePage = (next: number) => {
    setPage(next);
    setActive(-1);
    suggestions.current?.parentElement?.scrollTo({ top: 0 });
    input.current?.focus();
  };
  const select = (option: SearchOption, pointerSelection = false) => {
    // A coarse-pointer option tap should dismiss the native keyboard. Keep
    // focus for desktop clicks and Arrow/Enter selection.
    if (pointerSelection && window.matchMedia("(pointer: coarse)").matches)
      input.current?.blur();
    if (replaceValueOnSelect) onChange(option.label);
    setOpen(false);
    setActive(-1);
    onSelect?.(option);
  };
  return (
    <div
      ref={combo}
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
          aria-describedby={descriptionId}
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
          disabled={!mounted}
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
                  ? i < 0
                    ? e.key === "ArrowDown" ? 0 : matches.length - 1
                    : (i + (e.key === "ArrowDown" ? 1 : -1) + matches.length) % matches.length
                  : -1,
              );
            }
            if (e.key === "Escape" && open) {
              e.preventDefault();
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
          data-placement={popup.above ? "above" : "below"}
          style={{ maxHeight: popup.maxHeight }}
        >
        <div
          ref={suggestions}
          id={id}
          role="listbox"
          data-placement={popup.above ? "above" : "below"}
          aria-label={`Sugerencias: ${label}`}
        >
          {matches.map((o, i) => (
            <button
              type="button"
              role="option"
              id={`${id}-${i}`}
              aria-selected={i === active}
              aria-label={o.hierarchy ? `${o.label} · ${o.detail || ""}`.trim() : undefined}
              className={o.hierarchy ? "hierarchy-option" : undefined}
              key={o.id}
              onMouseDown={(e) => e.preventDefault()}
              onClick={(event) => select(o, event.detail > 0)}
            >
              {o.hierarchy ? <>
                <span className="hierarchy-option-title" style={{ paddingInlineStart: Math.min(o.hierarchy.depth - 1, 3) * 12 }}>
                  {o.hierarchy.depth > 1 && <span aria-hidden="true" className="hierarchy-branch">↳</span>}
                  <strong>{o.hierarchy.leaf}</strong>
                  {o.hierarchy.children && <span aria-hidden="true" className="hierarchy-parent-mark">▾</span>}
                </span>
                <small>{o.label} · {o.detail}</small>
              </> : <>
                <span>{o.label}</span>
                {o.detail && <small>{o.detail}</small>}
              </>}
            </button>
          ))}
          {!matches.length && (
            <p role="status">
              {loading
                ? "Buscando sugerencias…"
                : error
                  ? "No pudimos cargar las sugerencias. Intenta de nuevo."
                  : "Sin coincidencias. Prueba otro nombre."}
            </p>
          )}
        </div>
        {paginateOptions && allMatches.length > 0 && (allMatches.length > 8 || onMore) && (
          <div className="search-pages" aria-label="Páginas de sugerencias">
            {moreError && <p role="alert">No pudimos cargar más coincidencias.</p>}
            <span role="status">{currentPage * 8 + 1}–{Math.min((currentPage + 1) * 8, allMatches.length)} de {allMatches.length}</span>
            <div>
              <button type="button" disabled={currentPage === 0}
                onMouseDown={(e) => e.preventDefault()} onClick={() => changePage(currentPage - 1)}>Anteriores</button>
              {((currentPage + 1) * 8 < allMatches.length)
                ? <button type="button" onMouseDown={(e) => e.preventDefault()}
                    onClick={() => changePage(currentPage + 1)}>Siguientes</button>
                : onMore && <button type="button" disabled={moreLoading}
                    onMouseDown={(e) => e.preventDefault()} onClick={onMore}>
                    {moreLoading ? "Cargando…" : moreError ? "Reintentar coincidencias" : "Cargar más coincidencias"}</button>}
            </div>
          </div>
        )}
        </div>
      )}
    </div>
  );
}
