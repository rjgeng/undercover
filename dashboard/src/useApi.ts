import { useCallback, useEffect, useState } from "react";

export const EVERY = 2000;

export interface Loaded<T> {
  data: T | undefined;
  error: string | undefined;
  reload: () => void;
}

export function useApi<T>(load: () => Promise<T>, poll = true): Loaded<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string>();
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => {
    setTick((n) => n + 1);
  }, []);

  useEffect(() => {
    let live = true;
    const refresh = () => {
      load().then(
        (value) => {
          if (!live) return;
          setData(value);
          setError(undefined);
        },
        (reason: unknown) => {
          if (live)
            setError(reason instanceof Error ? reason.message : "Failed");
        },
      );
    };
    refresh();
    const timer = poll ? setInterval(refresh, EVERY) : undefined;
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [load, poll, tick]);

  return { data, error, reload };
}
