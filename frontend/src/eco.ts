/** Rough client-side footprint estimate for a prompt.
 *
 * Deliberately approximate: the backend owns the real o200k_base count, this only needs to move
 * while you type so the cost of extra words is visible before you spend a generation.
 */

const WH_PER_TOKEN = 0.002;
const GRAMS_CO2_PER_WH = 0.7;
const PHONE_BATTERY_WH = 12;
const BULB_WATTS = 60;
const WH_PER_SEARCH = 0.3;

const FILLER = [
  "hyperrealistic",
  "hyper realistic",
  "photorealistic",
  "ultra realistic",
  "ultra detailed",
  "highly detailed",
  "super detailed",
  "extremely detailed",
  "insanely detailed",
  "masterpiece",
  "award winning",
  "award-winning",
  "trending on artstation",
  "artstation",
  "unreal engine",
  "octane render",
  "8k",
  "4k",
  "hd",
  "uhd",
  "best quality",
  "high quality",
  "very",
  "really",
  "truly",
  "stunning",
  "gorgeous",
  "epic",
  "amazing",
  "beautiful",
];

export type Footprint = {
  tokens: number;
  energyMilliWattHours: number;
  co2Milligrams: number;
  phoneChargePercent: number;
  bulbSeconds: number;
  searches: number;
};

export function estimateTokens(text: string): number {
  const trimmed = text.trim();
  if (!trimmed) return 0;
  const words = trimmed.split(/\s+/).length;
  return Math.max(words, Math.ceil(trimmed.length / 4));
}

export function footprint(text: string): Footprint {
  const tokens = estimateTokens(text);
  const wattHours = tokens * WH_PER_TOKEN;
  return {
    tokens,
    energyMilliWattHours: wattHours * 1000,
    co2Milligrams: wattHours * GRAMS_CO2_PER_WH * 1000,
    phoneChargePercent: (wattHours / PHONE_BATTERY_WH) * 100,
    bulbSeconds: (wattHours * 3600) / BULB_WATTS,
    searches: wattHours / WH_PER_SEARCH,
  };
}

/** Strips hype words that cost tokens without telling the model anything about the target. */
export function trimFiller(text: string): string {
  let trimmed = text;
  for (const word of FILLER) {
    trimmed = trimmed.replace(
      new RegExp(`\\b${word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "gi"),
      " ",
    );
  }
  return trimmed
    .replace(/\s+([,.;:])/g, "$1")
    .replace(/([,;])\s*(?=[,;.])/g, "")
    .replace(/\s{2,}/g, " ")
    .replace(/^[\s,;]+/, "")
    .trim();
}
