"use client";
import { useEffect, useId, useRef } from "react";
import { IoCloseOutline } from "react-icons/io5";
/** Native dialog provides focus containment, escape handling and inert background. */
export function Overlay({
  title,
  children,
  onClose,
  className = "",
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  className?: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null),
    heading = useId(),
    callback = useRef(onClose);
  callback.current = onClose;
  useEffect(() => {
    const el = dialog.current!;
    const focus = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    el.showModal();
    const token = heading;
    if (window.history.state?.agroOverlay !== token)
      window.history.pushState(
        { ...window.history.state, agroOverlay: token },
        "",
      );
    const pop = () => {
      if (window.history.state?.agroOverlay !== token) callback.current();
    };
    window.addEventListener("popstate", pop);
    return () => {
      window.removeEventListener("popstate", pop);
      el.close();
      document.body.style.overflow = overflow;
      focus?.focus({ preventScroll: true });
    };
  }, []);
  const dismiss = () => {
    if (window.history.state?.agroOverlay) window.history.back();
    else callback.current();
  };
  return (
    <dialog
      ref={dialog}
      className={`app-overlay ${className}`}
      aria-labelledby={heading}
      onCancel={(e) => {
        e.preventDefault();
        dismiss();
      }}
    >
      <header className="overlay-header">
        <h2 id={heading}>{title}</h2>
        <button
          type="button"
          className="button secondary icon-button"
          aria-label="Cerrar ventana"
          onClick={dismiss}
        >
          <IoCloseOutline />
        </button>
      </header>
      {children}
    </dialog>
  );
}
