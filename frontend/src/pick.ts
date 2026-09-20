export function pickRandom<T>(items: T[], exclude?: (item: T) => boolean): T | null {
  const pool = exclude ? items.filter((item) => !exclude(item)) : items;
  const choices = pool.length > 0 ? pool : items;
  return choices.length === 0
    ? null
    : choices[Math.floor(Math.random() * choices.length)];
}
