import { loginAction } from "@/app/actions";
import { SubmitButton } from "@/components/SubmitButton";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; error?: string }>;
}) {
  const { next, error } = await searchParams;

  return (
    <div className="mx-auto mt-16 max-w-sm space-y-4">
      <div>
        <h1 className="text-xl font-bold">LinkIntel</h1>
        <p className="text-sm text-slate-500">Enter the shared password to continue.</p>
      </div>
      <form action={loginAction} className="space-y-3">
        <input type="hidden" name="next" value={next ?? "/"} />
        <div>
          <label className="block text-xs text-slate-500">Password</label>
          <input
            type="password"
            name="password"
            required
            autoFocus
            className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm"
          />
        </div>
        {error && <p className="text-sm text-red-600">Wrong password. Try again.</p>}
        <SubmitButton pendingLabel="Checking…">Continue</SubmitButton>
      </form>
    </div>
  );
}
