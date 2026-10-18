import type { JobRun } from "../types";

const ACTIVE = new Set(["QUEUED", "RUNNING"]);
const TERMINAL = new Set(["SUCCESS", "FAILED", "CANCELLED", "PARTIAL"]);

// Heartbeats change frequently but do not mean derived data has been committed.
function progressSignature(jobs: JobRun[]) {
  return JSON.stringify(jobs.map((job) => [
    job.id, job.status, job.step, job.row_count, job.metadata.progress_pct,
    job.metadata.current_trade_date, job.metadata.completed_trade_days
  ]));
}

export function createJobPoller(options: {
  fetchJobs: (signal: AbortSignal) => Promise<JobRun[]>;
  publishJobs: (jobs: JobRun[]) => void;
  refreshCoverage: (signal: AbortSignal) => Promise<void>;
  onError: (error: unknown) => void;
  now?: () => number;
  coverageIntervalMs?: number;
}) {
  const now = options.now || Date.now;
  const interval = options.coverageIntervalMs ?? 60_000;
  let controller = new AbortController();
  let generation = 0;
  let jobFlight: Promise<void> | null = null;
  let coverageFlight: Promise<boolean> | null = null;
  let latestJobs: JobRun[] = [];
  let observed = new Map<string, string>();
  let lastSignature = "";
  let lastAttempt = -Infinity;
  let terminalVersion = 0;
  let attemptedTerminalVersion = 0;
  let completedTerminalVersion = 0;

  function refreshCoverage(force = true): Promise<boolean> {
    if (coverageFlight) return coverageFlight;
    const terminalPending = terminalVersion > completedTerminalVersion;
    const newlyTerminal = terminalVersion > attemptedTerminalVersion;
    const signature = progressSignature(latestJobs);
    const advancing = latestJobs.some((job) => job.status === "RUNNING" && !job.heartbeat_stale)
      && signature !== lastSignature;
    if (!force && (!terminalPending && !advancing
      || !newlyTerminal && now() - lastAttempt < interval)) return Promise.resolve(false);

    const token = generation;
    const version = terminalVersion;
    const signal = controller.signal;
    attemptedTerminalVersion = version;
    lastAttempt = now();
    coverageFlight = (async () => {
      try {
        await options.refreshCoverage(signal);
        if (token !== generation) return false;
        lastSignature = signature;
        completedTerminalVersion = version;
        return true;
      } catch (error) {
        if (token === generation && !signal.aborted) options.onError(error);
        return false;
      } finally {
        if (token === generation) coverageFlight = null;
      }
    })();
    return coverageFlight;
  }

  function observe(jobs: JobRun[], coverageLoaded = false) {
    for (const job of jobs) {
      if (ACTIVE.has(observed.get(job.id) || "") && TERMINAL.has(job.status)) terminalVersion++;
    }
    observed = new Map(jobs.map((job) => [job.id, job.status]));
    latestJobs = jobs;
    if (coverageLoaded) lastSignature = progressSignature(jobs);
  }

  function refresh(): Promise<void> {
    if (jobFlight) return jobFlight;
    const token = generation;
    const signal = controller.signal;
    jobFlight = (async () => {
      try {
        const jobs = await options.fetchJobs(signal);
        if (token !== generation || signal.aborted) return;
        observe(jobs);
        options.publishJobs(jobs);
        // Slow historical statistics must not block lightweight task polling.
        void refreshCoverage(false);
      } catch (error) {
        if (token === generation && !signal.aborted) options.onError(error);
      } finally {
        if (token === generation) jobFlight = null;
      }
    })();
    return jobFlight;
  }

  function reset() {
    generation++;
    controller.abort();
    controller = new AbortController();
    jobFlight = coverageFlight = null;
    latestJobs = [];
    observed = new Map();
    lastSignature = "";
    lastAttempt = -Infinity;
    terminalVersion = attemptedTerminalVersion = completedTerminalVersion = 0;
  }

  return { refresh, refreshCoverage, observe, reset };
}
