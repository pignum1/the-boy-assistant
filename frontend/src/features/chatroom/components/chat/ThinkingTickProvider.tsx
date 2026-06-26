/** 全局每秒 tick：提供给所有 ThinkingRow 共享，避免每行各起一个 timer */
import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';

const TickContext = createContext<number>(Date.now());

export function ThinkingTickProvider({ children }: { children: ReactNode }) {
  const [tick, setTick] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setTick(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return <TickContext.Provider value={tick}>{children}</TickContext.Provider>;
}

export function useThinkingTick(): number {
  return useContext(TickContext);
}
