import { useCallback, useEffect, useState } from "react";
import { message } from "./api";

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
    let timer: ReturnType<typeof setTimeout> | undefined;
    const refresh = () => {
      load()
        .then(
          (value) => {
            if (!live) return;
            setData(value);
            setError(undefined);
          },
          (reason: unknown) => {
            if (live) setError(message(reason));
          },
        )
        .finally(() => {
          if (live && poll) timer = setTimeout(refresh, EVERY);
        });
    };
    refresh();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [load, poll, tick]);

  return { data, error, reload };
}
