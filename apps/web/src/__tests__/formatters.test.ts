import { describe, expect, it } from "vitest";
import {
  formatDelay,
  formatObservationAge,
  formatPredictionSource,
  formatTime,
} from "../lib/formatters";

describe("formatters", () => {
  describe("formatTime", () => {
    it("returns placeholder on null, undefined, or empty input", () => {
      expect(formatTime(null)).toBe("--:--");
      expect(formatTime(undefined)).toBe("--:--");
      expect(formatTime("")).toBe("--:--");
    });

    it("returns placeholder on invalid date string", () => {
      expect(formatTime("not-a-valid-date")).toBe("--:--");
    });

    it("formats a valid ISO timestamp in local or specified timezone", () => {
      const iso = "2026-11-10T12:30:00Z";
      const formattedUtc = formatTime(iso, "UTC");
      expect(formattedUtc).toMatch(/12:30:00/);

      const formattedTz = formatTime(iso, "America/New_York");
      // UTC 12:30 in New York (EST, UTC-5) is 7:30 AM
      expect(formattedTz).toMatch(/7:30:00/);
    });

    it("falls back gracefully when timezone is unrecognized", () => {
      const iso = "2026-11-10T12:30:00Z";
      const formatted = formatTime(iso, "Invalid/TimeZone_DoesNotExist");
      expect(formatted).not.toBe("--:--");
      expect(typeof formatted).toBe("string");
    });
  });

  describe("formatDelay", () => {
    it("identifies significant positive delay as late", () => {
      const delay = formatDelay(180); // 3 minutes late
      expect(delay.label).toBe("+3 min late");
      expect(delay.isDelayed).toBe(true);
      expect(delay.isOnTime).toBe(false);
      expect(delay.isEarly).toBe(false);
      expect(delay.badgeClass).toContain("text-amber-300");
    });

    it("identifies significant negative delay as early", () => {
      const delay = formatDelay(-120); // 2 minutes early
      expect(delay.label).toBe("2 min early");
      expect(delay.isEarly).toBe(true);
      expect(delay.isDelayed).toBe(false);
      expect(delay.isOnTime).toBe(false);
      expect(delay.badgeClass).toContain("text-cyan-300");
    });

    it("identifies delays within +-60s as on time", () => {
      const onTimeZero = formatDelay(0);
      expect(onTimeZero.label).toBe("On time");
      expect(onTimeZero.isOnTime).toBe(true);
      expect(onTimeZero.isDelayed).toBe(false);
      expect(onTimeZero.badgeClass).toContain("text-emerald-300");

      const onTime40s = formatDelay(45);
      expect(onTime40s.label).toBe("On time");
      expect(onTime40s.isOnTime).toBe(true);

      const onTimeNeg40s = formatDelay(-45);
      expect(onTimeNeg40s.label).toBe("On time");
      expect(onTimeNeg40s.isOnTime).toBe(true);
    });
  });

  describe("formatPredictionSource", () => {
    it("formats HISTORY_ADJUSTED badge", () => {
      const info = formatPredictionSource("HISTORY_ADJUSTED");
      expect(info.label).toBe("Live + History");
      expect(info.badgeClass).toContain("text-indigo-300");
      expect(info.description).toContain("real-time vehicle telemetry");
    });

    it("formats SCHEDULE_ONLY badge", () => {
      const info = formatPredictionSource("SCHEDULE_ONLY");
      expect(info.label).toBe("Schedule");
      expect(info.badgeClass).toContain("text-gray-300");
      expect(info.description).toContain("timetable schedule");
    });

    it("formats unrecognized source safely", () => {
      const info = formatPredictionSource("CUSTOM_HEURISTIC");
      expect(info.label).toBe("CUSTOM_HEURISTIC");
      expect(info.badgeClass).toContain("text-gray-300");
    });
  });

  describe("formatObservationAge", () => {
    const fixedNow = new Date("2026-11-10T12:00:00Z").getTime();

    it("returns placeholder on null or invalid date", () => {
      expect(formatObservationAge(null, fixedNow)).toBe(
        "No recent telemetry",
      );
      expect(formatObservationAge("invalid", fixedNow)).toBe(
        "Telemetry time unavailable",
      );
    });

    it("formats seconds ago (< 60s)", () => {
      const obsTime = new Date("2026-11-10T11:59:35Z").toISOString(); // 25s ago
      expect(formatObservationAge(obsTime, fixedNow)).toBe("25s ago");
    });

    it("formats minutes ago", () => {
      const obsTime = new Date("2026-11-10T11:55:00Z").toISOString(); // 5m ago
      expect(formatObservationAge(obsTime, fixedNow)).toBe("5m ago");
    });

    it("formats hours ago", () => {
      const obsTime = new Date("2026-11-10T10:00:00Z").toISOString(); // 2h ago
      expect(formatObservationAge(obsTime, fixedNow)).toBe("2h ago");
    });
  });
});
