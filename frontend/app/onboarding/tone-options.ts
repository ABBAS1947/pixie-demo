// Tone options for the onboarding wizard (onboarding-redesign-guide §4).
// The preview line is the entire point of the component: one real line of
// pixie speaking in that tone — never a placeholder. ids are the backend
// tone values (app/api/onboarding.py _TONES), labels are user-facing.

import type { Tone } from "@/lib/types";

export interface ToneOption {
  id: Tone;
  label: string;
  preview: string;
}

export const TONE_OPTIONS: ToneOption[] = [
  {
    id: "playful_sarcastic",
    label: "Playful",
    preview: "Let's make this one click.",
  },
  {
    id: "calm_steady",
    label: "Calm",
    preview: "One step at a time.",
  },
  {
    id: "blunt",
    label: "Direct",
    preview: "Here's what to work on next.",
  },
];
