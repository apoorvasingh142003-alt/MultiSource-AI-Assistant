"use client";
import React from "react";
import type { Session } from "@/lib/types";
import * as api from "@/lib/api";
import { Button, Icons, cn } from "./ui";

function timeGroup(dateStr: string): string {
  const d = new Date(dateStr + "Z");
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const day = 24 * 60 * 60 * 1000;
  if (diff < day) return "Today";
  if (diff < 2 * day) return "Yesterday";
  if (diff < 7 * day) return "Last 7 Days";
  return "Older";
}

function groupSessions(
  sessions: Session[]
): { group: string; items: Session[] }[] {
  const groups: Record<string, Session[]> = {};
  const order = ["Today", "Yesterday", "Last 7 Days", "Older"];
  for (const s of sessions) {
    const g = timeGroup(s.created_at);
    if (!groups[g]) groups[g] = [];
    groups[g].push(s);
  }
  return order
    .filter((g) => groups[g]?.length)
    .map((g) => ({ group: g, items: groups[g] }));
}

export default function ChatSidebar({
  sessions,
  activeSessionId,
  collapsed,
  onToggle,
  onSelectSession,
  onNewSession,
  onDeleteSession,
  onRenameSession,
}: {
  sessions: Session[];
  activeSessionId: string | null;
  collapsed: boolean;
  onToggle: () => void;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onDeleteSession: (id: string) => void;
  onRenameSession: (id: string, title: string) => void;
}) {
  const [search, setSearch] = React.useState("");
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editTitle, setEditTitle] = React.useState("");
  const [contextMenu, setContextMenu] = React.useState<{
    id: string;
    x: number;
    y: number;
  } | null>(null);

  const filtered = sessions.filter(
    (s) =>
      !search ||
      (s.title || "New Chat").toLowerCase().includes(search.toLowerCase())
  );
  const grouped = groupSessions(filtered);

  const handleContextMenu = (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    setContextMenu({ id, x: e.clientX, y: e.clientY });
  };

  React.useEffect(() => {
    const close = () => setContextMenu(null);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, []);

  if (collapsed) {
    return (
      <div className="flex w-12 flex-col items-center gap-2 border-r border-line bg-surface py-3">
        <button
          onClick={onToggle}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-faint transition hover:bg-surface-2 hover:text-fg"
          title="Expand sidebar"
        >
          <Icons.chevron className="h-4 w-4" />
        </button>
        <button
          onClick={onNewSession}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-faint transition hover:bg-accent-soft hover:text-accent"
          title="New Chat"
        >
          <Icons.plus className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex w-[280px] shrink-0 flex-col border-r border-line bg-surface">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-line px-3 py-2.5">
        <span className="text-[12px] font-semibold uppercase tracking-wider text-muted">
          Chat History
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={onNewSession}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-accent transition hover:bg-accent-soft"
            title="New Chat"
          >
            <Icons.plus className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={onToggle}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-faint transition hover:bg-surface-2 hover:text-fg"
            title="Collapse sidebar"
          >
            <Icons.chevron className="h-3.5 w-3.5 rotate-180" />
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="px-3 py-2">
        <div className="relative">
          <Icons.search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-faint" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search chats…"
            className="focus-ring w-full rounded-lg border border-line bg-surface-2 py-1.5 pl-8 pr-3 text-[12px] text-fg placeholder:text-faint"
          />
        </div>
      </div>

      {/* Session list */}
      <div className="scroll-thin flex-1 overflow-y-auto px-2 pb-3">
        {grouped.length === 0 && (
          <p className="px-2 py-4 text-center text-[12px] text-faint">
            No conversations yet
          </p>
        )}
        {grouped.map(({ group, items }) => (
          <div key={group} className="mb-2">
            <div className="px-2 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-faint">
              {group}
            </div>
            {items.map((s) => (
              <div
                key={s.id}
                onClick={() => onSelectSession(s.id)}
                onContextMenu={(e) => handleContextMenu(e, s.id)}
                className={cn(
                  "group flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-[12.5px] transition",
                  activeSessionId === s.id
                    ? "bg-accent-soft text-accent ring-1 ring-accent/30"
                    : "text-body hover:bg-surface-2"
                )}
              >
                {editingId === s.id ? (
                  <input
                    autoFocus
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onBlur={() => {
                      if (editTitle.trim()) {
                        onRenameSession(s.id, editTitle.trim());
                      }
                      setEditingId(null);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        if (editTitle.trim()) {
                          onRenameSession(s.id, editTitle.trim());
                        }
                        setEditingId(null);
                      }
                      if (e.key === "Escape") setEditingId(null);
                    }}
                    className="min-w-0 flex-1 rounded border border-accent/50 bg-surface px-1.5 py-0.5 text-[12px] text-fg"
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <span className="min-w-0 flex-1 truncate">
                    {s.title || "New Chat"}
                  </span>
                )}
                {s.message_count > 0 && editingId !== s.id && (
                  <span className="shrink-0 rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-muted ring-1 ring-inset ring-line">
                    {s.message_count}
                  </span>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* Context menu */}
      {contextMenu && (
        <div
          className="animate-scale-in fixed z-50 min-w-[130px] rounded-lg border border-line bg-overlay py-1 shadow-pop"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            onClick={() => {
              const s = sessions.find((s) => s.id === contextMenu.id);
              if (s) {
                setEditTitle(s.title || "");
                setEditingId(s.id);
              }
              setContextMenu(null);
            }}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-body hover:bg-surface-2"
          >
            <Icons.doc className="h-3 w-3" /> Rename
          </button>
          <button
            onClick={() => {
              if (window.confirm("Delete this chat?")) {
                onDeleteSession(contextMenu.id);
              }
              setContextMenu(null);
            }}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] text-rose-600 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-500/10"
          >
            <Icons.x className="h-3 w-3" /> Delete
          </button>
        </div>
      )}
    </div>
  );
}
