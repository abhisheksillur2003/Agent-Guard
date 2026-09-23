# Phase 7: operations console

Phase 7 provides the browser control plane for administrators, developers, approvers, and read-only users. It exposes existing backend contracts without moving security decisions into the browser.

## Architecture

The frontend uses the Next.js App Router, React, TypeScript, TanStack Query, Zustand, Recharts, and a responsive CSS design system. Next.js route handlers form a small backend-for-frontend layer:

1. login credentials are forwarded directly to the FastAPI token endpoint;
2. the returned access token is stored in a secure, same-site, HttpOnly cookie;
3. browser requests use same-origin `/api/backend/*` paths;
4. the server proxy adds the bearer token and forwards sanitized responses; and
5. the token is never exposed to client JavaScript or browser storage.

FastAPI remains responsible for authentication, roles, tenant isolation, validation, authorization, policies, detectors, approvals, and execution authority.

## Views

- dashboard metrics, execution activity, and agent risk distribution
- agent reliability and lifecycle overview
- tool registry and adapter configuration
- immutable policy overview
- approval queue with approve and reject actions
- execution history and attempt state
- detector registry and sanitized findings
- tenant audit history
- local system startup guidance

## Demo mode

`NEXT_PUBLIC_DEMO_MODE=true` loads synthetic local records for UI review. It does not call protected APIs, does not contain credentials, and is disabled by default. Production deployments must leave demo mode disabled.

## Completion criteria

Phase 7 is complete when formatting, ESLint, strict TypeScript checking, and the production Next.js build pass; authentication uses HttpOnly cookies; protected data flows through the server proxy; approval mutations call the FastAPI contract; and desktop and mobile layouts render without clipping or navigation loss.
