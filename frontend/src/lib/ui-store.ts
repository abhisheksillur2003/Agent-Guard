import { create } from "zustand";

interface UiState {
  mobileNavigationOpen: boolean;
  setMobileNavigationOpen: (open: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  mobileNavigationOpen: false,
  setMobileNavigationOpen: (open) => set({ mobileNavigationOpen: open }),
}));
