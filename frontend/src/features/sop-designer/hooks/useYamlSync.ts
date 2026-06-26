import { useCallback, useEffect, useRef, useState } from 'react';
import * as jsYaml from 'js-yaml';
import { sopToYaml, yamlToSop, validateSopData } from '../../../shared/utils/yaml';
import type { SOPDefinition } from '../../../shared/types/sop';

interface UseYamlSyncOptions {
  getSop: () => SOPDefinition;
  loadSop: (sop: SOPDefinition) => void;
  debounceMs?: number;
}

export function useYamlSync({ getSop, loadSop, debounceMs = 800 }: UseYamlSyncOptions) {
  const [yamlText, setYamlText] = useState('');
  const [errors, setErrors] = useState<string[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const syncToYaml = useCallback(() => {
    const sop = getSop();
    setYamlText(sopToYaml(sop));
    setErrors([]);
  }, [getSop]);

  const onYamlChange = useCallback(
    (value: string) => {
      setYamlText(value);
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        try {
          const parsed = jsYaml.load(value);
          const validationErrors = validateSopData(parsed);
          if (validationErrors.length > 0) {
            setErrors(validationErrors);
            return;
          }
          const sop = yamlToSop(value);
          setErrors([]);
          loadSop(sop);
        } catch (e) {
          setErrors([String((e as Error).message)]);
        }
      }, debounceMs);
    },
    [debounceMs, loadSop]
  );

  useEffect(() => () => clearTimeout(timerRef.current), []);

  return { yaml: yamlText, errors, syncToYaml, onYamlChange };
}
