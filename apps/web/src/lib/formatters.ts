/**
 * Time, delay, and prediction source formatting utilities for Transit Explorer.
 */

/**
 * Format an ISO 8601 timestamp string into human-readable 12-hour or 24-hour time.
 * If timeZone is specified and valid, it formats in that timezone; otherwise falls back to local.
 */
export function formatTime(
  isoString: string | null | undefined,
  timeZone?: string | null,
): string {
  if (!isoString) {
    return "--:--";
  }

  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return "--:--";
  }

  const options: Intl.DateTimeFormatOptions = {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  };

  if (timeZone && timeZone.trim()) {
    try {
      return new Intl.DateTimeFormat(undefined, {
        ...options,
        timeZone: timeZone.trim(),
      }).format(date);
    } catch {
      // Fallback to local time if timezone string is unknown/invalid
    }
  }

  return new Intl.DateTimeFormat(undefined, options).format(date);
}

/**
 * Returns delay information with appropriate badge styling and passenger-facing text.
 */
export interface DelayInfo {
  label: string;
  badgeClass: string;
  isDelayed: boolean;
  isEarly: boolean;
  isOnTime: boolean;
}

export function formatDelay(delaySeconds: number): DelayInfo {
  // If delayed by more than 60 seconds (1 minute)
  if (delaySeconds > 60) {
    const minutes = Math.max(1, Math.round(delaySeconds / 60));
    return {
      label: `+${minutes} min late`,
      badgeClass:
        "bg-amber-900/60 text-amber-300 border border-amber-700/60",
      isDelayed: true,
      isEarly: false,
      isOnTime: false,
    };
  }

  // If early by more than 60 seconds (1 minute)
  if (delaySeconds < -60) {
    const minutes = Math.max(1, Math.round(Math.abs(delaySeconds) / 60));
    return {
      label: `${minutes} min early`,
      badgeClass:
        "bg-cyan-900/60 text-cyan-300 border border-cyan-700/60",
      isDelayed: false,
      isEarly: true,
      isOnTime: false,
    };
  }

  return {
    label: "On time",
    badgeClass:
      "bg-emerald-900/60 text-emerald-300 border border-emerald-700/60",
    isDelayed: false,
    isEarly: false,
    isOnTime: true,
  };
}

/**
 * Returns metadata and styles for a prediction source badge.
 */
export interface PredictionSourceInfo {
  label: string;
  badgeClass: string;
  description: string;
}

export function formatPredictionSource(source: string): PredictionSourceInfo {
  switch (source) {
    case "HISTORY_ADJUSTED":
      return {
        label: "Live + History",
        badgeClass:
          "bg-indigo-900/60 text-indigo-300 border border-indigo-700/60",
        description:
          "Estimated using live vehicle positions and historical delay patterns.",
      };
    case "TRIP_UPDATE":
      return {
        label: "Live TripUpdate",
        badgeClass:
          "bg-emerald-900/60 text-emerald-300 border border-emerald-700/60",
        description:
          "Estimated using official real-time transit updates.",
      };
    case "SCHEDULE_ONLY":
      return {
        label: "Schedule",
        badgeClass: "bg-gray-800 text-gray-300 border border-gray-700",
        description:
          "Based on timetable schedule; live tracking is not currently reporting for this trip.",
      };
    default:
      return {
        label: source,
        badgeClass: "bg-gray-800 text-gray-300 border border-gray-700",
        description: `Prediction source: ${source}`,
      };
  }
}

/**
 * Formats a live observation timestamp into a concise relative description.
 */
export function formatObservationAge(
  isoString: string | null | undefined,
  nowMs: number = Date.now(),
): string {
  if (!isoString) {
    return "No live update";
  }

  const date = new Date(isoString);
  const timeMs = date.getTime();
  if (Number.isNaN(timeMs)) {
    return "Time unavailable";
  }

  const diffSeconds = Math.max(0, Math.floor((nowMs - timeMs) / 1000));
  if (diffSeconds < 60) {
    return `${diffSeconds}s ago`;
  }
  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }
  const diffHours = Math.floor(diffMinutes / 60);
  return `${diffHours}h ago`;
}

/**
 * Formats a local millisecond timestamp into a human-readable clock time for last updated badges.
 */
export function formatLastUpdated(
  timestampMs: number | null | undefined,
  timeZone?: string | null,
): string {
  if (!timestampMs || timestampMs <= 0) {
    return "Never";
  }

  const date = new Date(timestampMs);
  if (Number.isNaN(date.getTime())) {
    return "Never";
  }

  const options: Intl.DateTimeFormatOptions = {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  };

  if (timeZone && timeZone.trim()) {
    try {
      return new Intl.DateTimeFormat(undefined, {
        ...options,
        timeZone: timeZone.trim(),
      }).format(date);
    } catch {
      // Fallback to local time if timezone is invalid
    }
  }

  return new Intl.DateTimeFormat(undefined, options).format(date);
}
