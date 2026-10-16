"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { relatedScreenLabel, safeReportPath, sourceDocumentId } from "./report-context";
import styles from "./reportar.module.css";

function ReportForm() {
  const search = useSearchParams();
  const pagePath = safeReportPath(search.get("from"));
  const documentId = sourceDocumentId(pagePath);
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [queuedId, setQueuedId] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const text = message.trim();
    if (text.length < 10 || text.length > 5000) {
      setError("Describe el problema con entre 10 y 5.000 caracteres.");
      return;
    }
    if (email.length > 254) {
      setError("El correo no puede superar 254 caracteres.");
      return;
    }
    if (email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError("Escribe un correo válido o deja ese campo vacío.");
      return;
    }
    if (!consent) {
      setError("Confirma que aceptas compartir este reporte con el propietario.");
      return;
    }
    setPending(true);
    try {
      const response = await fetch("/api/bug-reports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          ...(email.trim() ? { reply_email: email.trim() } : {}),
          ...(pagePath ? { page_path: pagePath } : {}),
          ...(documentId ? { source_document_id: documentId } : {}),
          consent: true,
        }),
      });
      if (response.status === 201) {
        const result = await response.json();
        if (result?.status !== "queued" || typeof result?.id !== "string") throw new Error("invalid response");
        setQueuedId(result.id);
        return;
      }
      setError(response.status === 429
        ? "Recibimos demasiados reportes en este momento. Espera un poco e inténtalo de nuevo."
        : response.status === 503
          ? "El servicio de reportes no está disponible ahora. Conservamos tu texto aquí para que puedas reintentarlo."
          : response.status === 400
            ? "Revisa el texto, el correo y el consentimiento antes de reintentar."
            : "No pudimos poner el reporte en cola. Inténtalo de nuevo.");
    } catch {
      setError("No pudimos conectar con el servicio de reportes. Tu texto sigue aquí para reintentar.");
    } finally {
      setPending(false);
    }
  }

  function reset() {
    setMessage("");
    setEmail("");
    setConsent(false);
    setQueuedId(null);
    setError("");
  }

  return <div className={styles.page}>
    <Link href={pagePath || "/sources"} className="back-link">← Volver</Link>
    <h1>Reportar un problema</h1>
    <p>Cuéntanos qué dato o función no salió bien. Tu reporte irá al propietario de AgroAmigo para revisión.</p>
    {pagePath && <p className={styles.context}>Pantalla relacionada: {relatedScreenLabel(pagePath)}</p>}
    {queuedId ? <section className={styles.success} role="status" aria-live="polite">
      <h2>Reporte en cola</h2>
      <p>Guardamos tu reporte para intentar enviarlo. Esto no confirma que el correo ya haya llegado.</p>
      <p>Referencia: <code>{queuedId}</code></p>
      <button type="button" onClick={reset}>Escribir otro reporte</button>
    </section> : <form onSubmit={submit} noValidate>
      <label className="form-field" htmlFor="bug-message">¿Qué pasó?
        <textarea id="bug-message" name="message" required minLength={10} maxLength={5000}
          value={message} onChange={event => setMessage(event.target.value)}
          aria-describedby="bug-message-help" disabled={pending} rows={7} />
        <small id="bug-message-help">Entre 10 y 5.000 caracteres. No incluyas contraseñas ni datos privados.</small>
      </label>
      <label className="form-field" htmlFor="bug-email">Correo para responderte (opcional)
        <input id="bug-email" name="reply_email" type="email" maxLength={254} autoComplete="email"
          value={email} onChange={event => setEmail(event.target.value)} disabled={pending} />
      </label>
      <label className={styles.consent} htmlFor="bug-consent">
        <input id="bug-consent" type="checkbox" checked={consent}
          onChange={event => setConsent(event.target.checked)} disabled={pending} />
        <span>Acepto compartir mi reporte y, si lo escribí, mi correo con el propietario de AgroAmigo
          (<a href="mailto:ekallett@gmail.com">ekallett@gmail.com</a>) para revisar el problema.</span>
      </label>
      <p className={styles.privacy}>Solo adjuntamos la ruta y los filtros de esta pantalla, si llegaste desde la app.
        No adjuntamos tu ubicación exacta, fincas guardadas ni ofertas privadas.</p>
      {error && <p role="alert" className={styles.error}>{error}</p>}
      <button type="submit" disabled={pending} aria-busy={pending} className={styles.submit}>
        {pending ? "Poniendo en cola…" : "Enviar reporte"}
      </button>
    </form>}
  </div>;
}

export default function ReportPage() {
  return <Suspense fallback={<p role="status">Cargando formulario…</p>}><ReportForm /></Suspense>;
}
