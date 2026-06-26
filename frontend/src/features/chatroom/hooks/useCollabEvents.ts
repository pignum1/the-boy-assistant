/** Hook for subscribing to LangGraph collaboration stream events via WebSocket */
import { useState, useCallback, useEffect } from 'react';
import type { CollabEvent, PhaseInfo, HitlRequest, FileChange } from '../../../shared/types/collaboration';

interface CollabState {
  phases: PhaseInfo[];
  currentPhase: number;
  hitlRequest: HitlRequest | null;
  filesChanged: FileChange[];
  nodeStatus: string;
  completed: boolean;
}

const initialState: CollabState = {
  phases: [],
  currentPhase: -1,
  hitlRequest: null,
  filesChanged: [],
  nodeStatus: '',
  completed: false,
};

export function useCollabEvents() {
  const [state, setState] = useState<CollabState>(initialState);

  // Listen for phase updates and HITL requests from WebSocket events
  useEffect(() => {
    const handlePhase = (e: CustomEvent) => {
      const { phases: phaseList, current } = e.detail;
      setState((prev) => ({
        ...prev,
        phases: (phaseList || []).map((p: string | { name: string; role?: string; goal?: string }) =>
          typeof p === 'string' ? { name: p, role: '', goal: '' } : p
        ),
        currentPhase: current ?? 0,
      }));
    };

    const handleHitl = (e: CustomEvent) => {
      setState((prev) => ({
        ...prev,
        hitlRequest: e.detail as HitlRequest,
        nodeStatus: 'hitl',
      }));
    };

    window.addEventListener('collab-phase-update', handlePhase as EventListener);
    window.addEventListener('collab-hitl-request', handleHitl as EventListener);

    return () => {
      window.removeEventListener('collab-phase-update', handlePhase as EventListener);
      window.removeEventListener('collab-hitl-request', handleHitl as EventListener);
    };
  }, []);

  const handleEvent = useCallback((event: CollabEvent) => {
    // Direct event handling for future use
  }, []);

  const respondToHitl = useCallback((value: string) => {
    setState((prev) => ({
      ...prev,
      hitlRequest: null,
      nodeStatus: 'resuming',
    }));
    return value; // Caller should send this via WebSocket
  }, []);

  const reset = useCallback(() => {
    setState(initialState);
  }, []);

  return {
    ...state,
    handleEvent,
    respondToHitl,
    reset,
  };
}
