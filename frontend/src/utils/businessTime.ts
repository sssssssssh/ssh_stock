const BUSINESS_TIME_ZONE = "Asia/Shanghai";

function businessDateParts(now: Date): { year: number; month: number; day: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: BUSINESS_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return {
    year: Number(values.year),
    month: Number(values.month),
    day: Number(values.day)
  };
}

function formatIsoDate(year: number, month: number, day: number): string {
  return `${year.toString().padStart(4, "0")}-${month.toString().padStart(2, "0")}-${day.toString().padStart(2, "0")}`;
}

export function businessTodayIso(now: Date = new Date()): string {
  const { year, month, day } = businessDateParts(now);
  return formatIsoDate(year, month, day);
}

export function businessDaysAgoIso(days: number, now: Date = new Date()): string {
  const { year, month, day } = businessDateParts(now);
  const shifted = new Date(Date.UTC(year, month - 1, day - days));
  return formatIsoDate(
    shifted.getUTCFullYear(),
    shifted.getUTCMonth() + 1,
    shifted.getUTCDate()
  );
}
