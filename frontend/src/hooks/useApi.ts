import { useCallback, useEffect, useRef, useState } from "react";
import type { DependencyList } from "react";
import { ApiError } from "../api/client";

export interface ApiState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  /** Load again. Keeps the current data on screen while it loads. */
  reload: () => Promise<void>;
  /** Replace the data locally, for optimistic updates. */
  setData: (update: T | ((current: T | null) => T | null)) => void;
}

/** Load data from the API with loading, error and reload states. No data library. */
export function useApi<T>(load: () => Promise<T>, deps: DependencyList): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const latest = useRef(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const loader = useCallback(load, deps);

  const run = useCallback(async () => {
    const call = ++latest.current;
    setLoading(true);
    try {
      const result = await loader();
      if (call === latest.current) {
        setData(result);
        setError(null);
      }
    } catch (caught) {
      if (call === latest.current) {
        setError(caught instanceof ApiError ? caught : new ApiError(0, "Something went wrong."));
      }
    } finally {
      if (call === latest.current) setLoading(false);
    }
  }, [loader]);

  useEffect(() => {
    void run();
  }, [run]);

  return {
    data,
    error,
    loading,
    reload: run,
    setData: setData as ApiState<T>["setData"],
  };
}
