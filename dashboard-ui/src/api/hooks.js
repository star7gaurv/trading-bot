/**
 * Reusable polling hooks. Pattern:
 *   const { data, error, loading, lastUpdated } = usePolling(getThing, 5000);
 *
 * No external state library needed.
 */
import { useEffect, useRef, useState } from "react";

export function usePolling(fetcher, intervalMs = 5000, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    let timer = null;

    const tick = async () => {
      try {
        const result = await fetcher();
        if (!aliveRef.current) return;
        setData(result);
        setError(null);
        setLastUpdated(Date.now());
      } catch (e) {
        if (!aliveRef.current) return;
        setError(e.message || String(e));
      } finally {
        if (aliveRef.current) setLoading(false);
      }
      if (aliveRef.current && intervalMs > 0) {
        timer = setTimeout(tick, intervalMs);
      }
    };

    tick();

    return () => {
      aliveRef.current = false;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading, lastUpdated };
}

/** One-shot fetch with manual refresh. */
export function useFetch(fetcher, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetcher()
      .then((d) => {
        if (alive) {
          setData(d);
          setError(null);
        }
      })
      .catch((e) => {
        if (alive) setError(e.message || String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, refreshKey]);

  return { data, error, loading, refresh: () => setRefreshKey((k) => k + 1) };
}
