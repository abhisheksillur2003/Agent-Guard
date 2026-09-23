# AgentGuard frontend

The Phase 7 console uses Next.js, React, TypeScript, Tailwind CSS, TanStack Query, Zustand, Recharts, and Lucide icons. A same-origin Next.js route proxy keeps the FastAPI access token in an HttpOnly cookie.

## Start locally

```powershell
Copy-Item frontend/.env.example frontend/.env.local
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend dev
```

The console is available at `http://127.0.0.1:3000`. Start FastAPI at `http://127.0.0.1:8000` before signing in.

For visual review without backend data, set `NEXT_PUBLIC_DEMO_MODE=true` in `frontend/.env.local`. Demo mode contains synthetic records only and is disabled by default.

## Verify

```powershell
pnpm --dir frontend format:check
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build
```
