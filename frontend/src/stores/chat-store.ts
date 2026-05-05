import { create } from 'zustand';

interface ChatStore {
  open: boolean;
  hasMessages: boolean;
  setOpen: (v: boolean) => void;
  toggle: () => void;
  setHasMessages: (v: boolean) => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  open: false,
  hasMessages: false,
  setOpen: (v) => set({ open: v }),
  toggle: () => set((s) => ({ open: !s.open })),
  setHasMessages: (v) => set({ hasMessages: v }),
}));
