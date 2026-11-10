import { create } from "zustand";
import type { StopSummary } from "../types/transit";

export interface AppState {
  /** Currently selected transit feed slug */
  selectedFeedSlug: string | null;

  /** Currently selected transit stop */
  selectedStop: StopSummary | null;

  /** Backwards-compatible alias for selected city / feed slug */
  selectedCity: string | null;

  /** Update selected feed slug (resets selectedStop to enforce feed isolation) */
  setSelectedFeedSlug: (slug: string | null) => void;

  /** Select a specific stop within the active feed */
  setSelectedStop: (stop: StopSummary | null) => void;

  /** Backwards-compatible alias for setSelectedFeedSlug */
  setSelectedCity: (city: string | null) => void;

  /** Reset all selections */
  reset: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  selectedFeedSlug: null,
  selectedStop: null,
  selectedCity: null,

  setSelectedFeedSlug: (slug) =>
    set({
      selectedFeedSlug: slug,
      selectedCity: slug,
      // Feed isolation: changing feed clears previously selected stop
      selectedStop: null,
    }),

  setSelectedStop: (stop) =>
    set({
      selectedStop: stop,
    }),

  setSelectedCity: (city) =>
    set({
      selectedCity: city,
      selectedFeedSlug: city,
      selectedStop: null,
    }),

  reset: () =>
    set({
      selectedFeedSlug: null,
      selectedStop: null,
      selectedCity: null,
    }),
}));
