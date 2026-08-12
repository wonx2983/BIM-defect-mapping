'use client';

import { create } from 'zustand';
import {
  detectSingleImage,
  detectBatch,
  type DetectionResponse,
  type DetectionItem,
  type BatchDetectionStatus,
} from '@/lib/api/detection';

interface UploadedFile {
  file: File;
  preview: string;
  status: 'pending' | 'processing' | 'done' | 'error';
  result: DetectionResponse | null;
  error: string | null;
}

interface DetectionState {
  files: UploadedFile[];
  selectedFileIndex: number | null;
  selectedDetectionIndex: number | null;
  isProcessing: boolean;
  batchResult: BatchDetectionStatus | null;
  projectId: string | null;
  error: string | null;

  setProjectId: (id: string) => void;
  addFiles: (files: File[]) => void;
  removeFile: (index: number) => void;
  clearFiles: () => void;
  selectFile: (index: number | null) => void;
  selectDetection: (index: number | null) => void;
  processAll: () => Promise<void>;
  processSingle: (index: number) => Promise<void>;
}

export const useDetectionStore = create<DetectionState>((set, get) => ({
  files: [],
  selectedFileIndex: null,
  selectedDetectionIndex: null,
  isProcessing: false,
  batchResult: null,
  projectId: null,
  error: null,

  setProjectId: (id) => set({ projectId: id }),

  addFiles: (newFiles) => {
    const uploaded: UploadedFile[] = newFiles.map((file) => ({
      file,
      preview: URL.createObjectURL(file),
      status: 'pending' as const,
      result: null,
      error: null,
    }));
    set((state) => ({ files: [...state.files, ...uploaded], error: null }));
  },

  removeFile: (index) => {
    set((state) => {
      const updated = [...state.files];
      if (updated[index]?.preview) {
        URL.revokeObjectURL(updated[index].preview);
      }
      updated.splice(index, 1);
      return {
        files: updated,
        selectedFileIndex:
          state.selectedFileIndex === index ? null : state.selectedFileIndex,
      };
    });
  },

  clearFiles: () => {
    const { files } = get();
    files.forEach((f) => URL.revokeObjectURL(f.preview));
    set({
      files: [],
      selectedFileIndex: null,
      selectedDetectionIndex: null,
      batchResult: null,
      error: null,
    });
  },

  selectFile: (index) => set({ selectedFileIndex: index, selectedDetectionIndex: null }),

  selectDetection: (index) => set({ selectedDetectionIndex: index }),

  processSingle: async (index) => {
    const { projectId, files } = get();
    if (!projectId) {
      set({ error: 'Please select a project first' });
      return;
    }

    const updated = [...files];
    updated[index] = { ...updated[index], status: 'processing' };
    set({ files: updated, isProcessing: true, error: null });

    try {
      const result = await detectSingleImage(updated[index].file, projectId);
      const final = [...get().files];
      final[index] = { ...final[index], status: 'done', result };
      set({ files: final, isProcessing: false, selectedFileIndex: index });
    } catch (err) {
      const final = [...get().files];
      final[index] = {
        ...final[index],
        status: 'error',
        error: err instanceof Error ? err.message : 'Detection failed',
      };
      set({ files: final, isProcessing: false });
    }
  },

  processAll: async () => {
    const { projectId, files } = get();
    if (!projectId) {
      set({ error: 'Please select a project first' });
      return;
    }
    if (files.length === 0) return;

    set({ isProcessing: true, error: null });

    // Process sequentially so we get per-file results
    for (let i = 0; i < files.length; i++) {
      if (files[i].status === 'done') continue;
      await get().processSingle(i);
    }

    set({ isProcessing: false });
  },
}));
