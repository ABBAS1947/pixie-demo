"use client";

import { formatDistanceToNow } from "date-fns";

interface Props {
  connected: boolean;
  email?: string | null;
  lastSyncAt?: string | null;
  isSyncing: boolean;
  onConnect: () => void;
  onSync: () => void;
  onDisconnect: () => void;
}

// Guide §4.1 Google section: connect button, or status badge with
// email / last-sync / disconnect.
export default function GoogleConnection({
  connected,
  email,
  lastSyncAt,
  isSyncing,
  onConnect,
  onSync,
  onDisconnect,
}: Props) {
  return (
    <div className="mt-4 border-t border-[var(--border)] pt-4">
      {connected ? (
        <div>
          <p
            className="truncate text-xs font-medium text-[var(--fg-2)]"
            style={{ fontFamily: "var(--font-dm-sans)" }}
          >
            {email ?? "Connected"}
          </p>
          <p
            className="mt-0.5 text-xs text-[var(--meta)]"
            style={{ fontFamily: "var(--font-dm-sans)" }}
          >
            {lastSyncAt
              ? `Synced ${formatDistanceToNow(new Date(lastSyncAt), { addSuffix: true })}`
              : "Not synced yet"}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <button
              onClick={onSync}
              disabled={isSyncing}
              className="btn-3d"
              style={{ fontFamily: "var(--font-dm-sans)" }}
            >
              <span className="bs" />
              <span className="be" />
              <span className="bf text-xs">
                {isSyncing ? "Syncing…" : "Sync now"}
              </span>
            </button>
            <button
              onClick={onDisconnect}
              className="rounded-[6px] px-2 py-1 text-xs font-medium text-[var(--danger)] transition-colors hover:bg-[var(--danger)]/10"
              style={{ fontFamily: "var(--font-dm-sans)" }}
            >
              Disconnect
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={onConnect}
          className="btn-3d"
          style={{ fontFamily: "var(--font-dm-sans)" }}
        >
          <span className="bs" />
          <span className="be" />
          <span className="bf text-sm">
            + Connect Google
          </span>
        </button>
      )}
    </div>
  );
}
