import { create } from "zustand";

interface AppState {
  /** Currently selected city identifier */
  selectedCity: string | null;
  setSelectedCity: (city: string | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  selectedCity: null,
  setSelectedCity: (city) => set({ selectedCity: city }),
}));
