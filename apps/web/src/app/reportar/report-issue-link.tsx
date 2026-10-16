"use client";

import { Suspense } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { IoBugOutline } from "react-icons/io5";
import { safeReportPath } from "./report-context";

type Props = { className?: string; icon?: boolean; iconOnly?: boolean; label: string; prefetch?: boolean };

function ContextLink({ className, icon, iconOnly, label, prefetch }: Props) {
  const path = usePathname();
  const query = useSearchParams();
  const from = safeReportPath(path + (query.size ? `?${query}` : ""));
  const href = from ? `/reportar?from=${encodeURIComponent(from)}` : "/reportar";
  return <Link href={href} className={className} aria-label={label} prefetch={prefetch}>
    {icon && <IoBugOutline aria-hidden="true" />}{iconOnly ? <span className="sr-only">{label}</span> : label}
  </Link>;
}

export function ReportIssueLink(props: { className?: string; icon?: boolean; iconOnly?: boolean; label?: string; prefetch?: boolean }) {
  const label = props.label || "Reportar un problema";
  return <Suspense fallback={<Link href="/reportar" className={props.className} aria-label={label} prefetch={props.prefetch}>
    {props.icon && <IoBugOutline aria-hidden="true" />}{props.iconOnly ? <span className="sr-only">{label}</span> : label}
  </Link>}>
    <ContextLink {...props} label={label} />
  </Suspense>;
}
