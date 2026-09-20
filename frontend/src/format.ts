export function round(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : String(Math.round(value))
}
