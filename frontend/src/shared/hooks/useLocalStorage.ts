import { useState } from 'react';

export function useLocalStorage<T>(key: string, initial: T): [T, (v: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const item = localStorage.getItem(key);
      return item ? JSON.parse(item) : initial;
    } catch {
      return initial;
    }
  });

  const set = (v: T | ((prev: T) => T)) => {
    const next = v instanceof Function ? v(value) : v;
    setValue(next);
    localStorage.setItem(key, JSON.stringify(next));
  };

  return [value, set];
}
