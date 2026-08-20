"use client";

import { useFormStatus } from "react-dom";

export function SubmitButton({
  children,
  pendingLabel,
  variant = "primary",
}: {
  children: React.ReactNode;
  pendingLabel?: string;
  variant?: "primary" | "secondary";
}) {
  const { pending } = useFormStatus();
  const base =
    "rounded px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50";
  const styles =
    variant === "primary"
      ? `${base} bg-slate-900 text-white hover:bg-slate-700`
      : `${base} border border-slate-300 text-slate-700 hover:bg-slate-50`;

  return (
    <button type="submit" disabled={pending} className={styles}>
      {pending ? (pendingLabel ?? "Working…") : children}
    </button>
  );
}
