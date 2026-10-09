"use client";

import { useState } from "react";
import { Check, MessageSquare } from "lucide-react";
import { Tag } from "@/components/ui";
import type { Project } from "@/lib/types";

const SEED: Project[] = [
  {
    id: "1",
    title: "Science Fair — Water Filtration",
    milestones: [
      { label: "Research filtration methods", done: true },
      { label: "Draft hypothesis", done: true },
      { label: "Build prototype", done: false },
      { label: "Write report", done: false },
    ],
    deadlineId: "4",
  },
  {
    id: "2",
    title: "History — French Revolution essay",
    milestones: [
      { label: "Outline", done: true },
      { label: "First draft", done: false },
    ],
  },
];

export default function Projects() {
  const [projects, setProjects] = useState<Project[]>(SEED);
  const [activeId, setActiveId] = useState<string>(SEED[0].id);
  const active = projects.find((p) => p.id === activeId) ?? projects[0];

  function toggleMilestone(projectId: string, idx: number) {
    setProjects((ps) =>
      ps.map((p) =>
        p.id === projectId
          ? {
              ...p,
              milestones: p.milestones.map((m, i) => (i === idx ? { ...m, done: !m.done } : m)),
            }
          : p,
      ),
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 lg:px-8">
      <h1 className="text-xl leading-tight">Projects</h1>
      <p className="mt-1 text-muted">Bigger goals, broken into milestones.</p>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[260px_1fr]">
        <div className="space-y-2">
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => setActiveId(p.id)}
              className={`w-full rounded-md px-4 py-3 text-left transition-shadow ${
                p.id === activeId ? "bg-surface-warm text-fg shadow-ring" : "bg-surface text-muted shadow-ring hover:text-fg"
              }`}
            >
              <p className="text-md">{p.title}</p>
              <p className="mt-0.5 text-xs text-meta">
                {p.milestones.filter((m) => m.done).length}/{p.milestones.length} done
              </p>
            </button>
          ))}
        </div>

        <div className="rounded-lg bg-surface p-6 shadow-ring">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-lg leading-tight">{active.title}</h2>
              {active.deadlineId ? <Tag color="var(--tag-bg-soft)">linked deadline</Tag> : null}
            </div>
            <button className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-2 text-sm text-accent-on shadow-ring-accent">
              <MessageSquare size={14} /> Continue in project mode
            </button>
          </div>

          <div className="mt-6 space-y-3">
            {active.milestones.map((m, i) => (
              <button
                key={i}
                onClick={() => toggleMilestone(active.id, i)}
                className="flex w-full items-center gap-3 rounded-md border border-border-soft px-4 py-3 text-left"
              >
                <span
                  className={`flex h-5 w-5 items-center justify-center rounded-sm ${
                    m.done ? "bg-accent text-accent-on" : "border border-border"
                  }`}
                >
                  {m.done ? <Check size={13} /> : null}
                </span>
                <span className={`text-base ${m.done ? "text-meta line-through" : "text-fg"}`}>{m.label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
