import { ShieldCheck } from "lucide-react";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="brand-lockup">
      <span className="brand-mark" aria-hidden="true">
        <ShieldCheck size={compact ? 22 : 28} strokeWidth={2.2} />
      </span>
      <span>
        <span className="brand-name">
          Agent<span>Guard</span>
        </span>
        {!compact && (
          <span className="brand-tagline">
            Secure agents. Safer operations.
          </span>
        )}
      </span>
    </div>
  );
}
