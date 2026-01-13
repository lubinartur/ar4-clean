import { useEffect, useRef } from 'react';

export type UsePollingOptions = {
  enabled?: boolean;              // default true
  intervalMs?: number;            // default 5000
  maxIntervalMs?: number;         // default 60000
  backoffFactor?: number;         // default 2
  pauseWhenHidden?: boolean;      // default true
  pauseWhenOffline?: boolean;     // default true
};

/**
 * Recursive setTimeout-based polling hook that prevents overlapping calls.
 * Only schedules next poll after current one completes.
 * 
 * Features:
 * - Pauses when tab is hidden (visibilityState !== "visible") if pauseWhenHidden is true
 * - Pauses when browser is offline (navigator.onLine === false) if pauseWhenOffline is true
 * - Exponential backoff on errors (interval increases up to maxIntervalMs)
 * - Resets backoff to base interval on successful calls
 */
export function usePolling(
  callback: () => void | Promise<void>,
  options: UsePollingOptions | number = {},
  legacyEnabled?: boolean
) {
  // Support legacy API: usePolling(callback, intervalMs, enabled)
  const opts: UsePollingOptions = typeof options === 'number'
    ? { intervalMs: options, enabled: legacyEnabled ?? true }
    : options;

  const {
    enabled = true,
    intervalMs = 5000,
    maxIntervalMs = 60000,
    backoffFactor = 2,
    pauseWhenHidden = true,
    pauseWhenOffline = true,
  } = opts;

  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isRunningRef = useRef(false);
  const currentIntervalRef = useRef(intervalMs);
  const pausedRef = useRef(false);
  const callbackRef = useRef(callback);
  const optionsRef = useRef({ enabled, intervalMs, maxIntervalMs, backoffFactor, pauseWhenHidden, pauseWhenOffline });

  // Keep refs up to date
  useEffect(() => {
    callbackRef.current = callback;
    optionsRef.current = { enabled, intervalMs, maxIntervalMs, backoffFactor, pauseWhenHidden, pauseWhenOffline };
    currentIntervalRef.current = intervalMs;
  }, [callback, enabled, intervalMs, maxIntervalMs, backoffFactor, pauseWhenHidden, pauseWhenOffline]);

  useEffect(() => {
    const opts = optionsRef.current;

    // Check if polling should be paused
    const shouldPause = (): boolean => {
      if (!opts.enabled) return true;
      if (opts.pauseWhenHidden && document.visibilityState !== 'visible') return true;
      if (opts.pauseWhenOffline && !navigator.onLine) return true;
      return false;
    };

    // Stop polling (clear timer, mark as paused)
    const stopPolling = () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      pausedRef.current = true;
    };

    // Execute poll callback
    const executePoll = async () => {
      if (shouldPause()) {
        pausedRef.current = true;
        return;
      }

      if (isRunningRef.current) {
        return;
      }

      isRunningRef.current = true;
      try {
        await callbackRef.current();
        // Success: reset backoff to base interval
        currentIntervalRef.current = opts.intervalMs;
      } catch (error) {
        // Error: increase interval with backoff, but not more than maxIntervalMs
        currentIntervalRef.current = Math.min(
          currentIntervalRef.current * opts.backoffFactor,
          opts.maxIntervalMs
        );
        // Errors are propagated, no console.error spam
      } finally {
        isRunningRef.current = false;
        scheduleNext();
      }
    };

    // Schedule next poll
    const scheduleNext = () => {
      if (shouldPause()) {
        pausedRef.current = true;
        return;
      }

      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }

      timeoutRef.current = setTimeout(executePoll, currentIntervalRef.current);
    };

    // Resume polling (reset backoff and start)
    const resumePolling = () => {
      if (!shouldPause()) {
        currentIntervalRef.current = opts.intervalMs; // Reset backoff
        pausedRef.current = false;
        executePoll();
      }
    };

    // Handle visibility changes
    const handleVisibilityChange = () => {
      if (shouldPause()) {
        if (!pausedRef.current) {
          stopPolling();
        }
      } else {
        if (pausedRef.current) {
          resumePolling();
        }
      }
    };

    // Handle online event
    const handleOnline = () => {
      if (!shouldPause() && pausedRef.current) {
        resumePolling();
      }
    };

    // Handle offline event
    const handleOffline = () => {
      if (shouldPause()) {
        stopPolling();
      }
    };

    // Initialize: start polling if conditions are met
    if (!shouldPause()) {
      pausedRef.current = false;
      currentIntervalRef.current = opts.intervalMs;
      executePoll();
    } else {
      pausedRef.current = true;
    }

    // Add event listeners
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      stopPolling();
      isRunningRef.current = false;
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [enabled, intervalMs, maxIntervalMs, backoffFactor, pauseWhenHidden, pauseWhenOffline]);
}
