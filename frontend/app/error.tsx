"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <p className="font-medium">Something went wrong talking to the backend.</p>
      <p className="mt-1 font-mono text-xs">{error.message}</p>
      <button
        onClick={reset}
        className="mt-3 rounded border border-red-300 px-3 py-1 text-xs hover:bg-red-100"
      >
        Try again
      </button>
    </div>
  );
}
