import Link from "next/link";

export default function NotFound() {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm">
      <p className="font-medium">Not found.</p>
      <p className="mt-1 text-slate-500">
        <Link href="/" className="text-slate-700 hover:underline">
          Back to domains
        </Link>
      </p>
    </div>
  );
}
