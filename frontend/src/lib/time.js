const pad = (n) => String(n).padStart(2, "0");

// The value format a <input type="datetime-local"> expects, in local time.
export function toDatetimeInput(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

export function nearestHalfHour(date = new Date()) {
  const halfHour = 30 * 60 * 1000;
  return new Date(Math.round(date.getTime() / halfHour) * halfHour);
}

export function formatDateTime(value) {
  return new Date(value).toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short" });
}
