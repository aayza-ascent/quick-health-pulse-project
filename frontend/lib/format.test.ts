import { describe, expect, it } from "vitest";

import {
  directionArrow,
  formatCoverage,
  formatDuration,
  formatPercent,
  formatSignedPercent,
  formatValue,
  isFullyCovered,
} from "./format";

describe("formatDuration", () => {
  it("renders hours and zero-padded minutes so figures align in a column", () => {
    expect(formatDuration(6 * 3600 + 18 * 60)).toBe("6h 18m");
    expect(formatDuration(7 * 3600 + 5 * 60)).toBe("7h 05m");
  });

  it("drops the hours component below an hour", () => {
    expect(formatDuration(45 * 60)).toBe("45m");
  });

  it("rounds to the nearest minute, since seconds are noise here", () => {
    expect(formatDuration(6 * 3600 + 18 * 60 + 29)).toBe("6h 18m");
    expect(formatDuration(6 * 3600 + 18 * 60 + 31)).toBe("6h 19m");
  });

  it("handles zero without producing an empty string", () => {
    expect(formatDuration(0)).toBe("0m");
  });
});

describe("formatValue", () => {
  it("formats each unit in its own idiom", () => {
    expect(formatValue(22_680, "seconds")).toBe("6h 18m");
    expect(formatValue(61.4, "bpm")).toBe("61 bpm");
    expect(formatValue(6421, "steps")).toBe("6,421");
  });

  it("renders a missing measurement as a dash rather than a zero", () => {
    expect(formatValue(null, "seconds")).toBe("—");
    expect(formatValue(null, "steps")).toBe("—");
  });

  it("keeps a genuine zero distinguishable from a gap", () => {
    expect(formatValue(0, "steps")).toBe("0");
  });
});

describe("percentages", () => {
  it("drops the sign when direction is carried by an arrow", () => {
    expect(formatPercent(-17.76)).toBe("18%");
    expect(formatPercent(11.14)).toBe("11%");
  });

  it("keeps an explicit sign where no arrow accompanies it", () => {
    expect(formatSignedPercent(-17.76)).toBe("−18%");
    expect(formatSignedPercent(11.14)).toBe("+11%");
    expect(formatSignedPercent(0.2)).toBe("0%");
  });

  it("renders null as a dash", () => {
    expect(formatPercent(null)).toBe("—");
    expect(formatSignedPercent(null)).toBe("—");
  });
});

describe("directionArrow", () => {
  it("indicates direction only, never a judgement", () => {
    expect(directionArrow("increased")).toBe("↑");
    expect(directionArrow("decreased")).toBe("↓");
    expect(directionArrow("stable")).toBe("→");
    expect(directionArrow("insufficient_data")).toBe("·");
  });
});

describe("coverage", () => {
  it("states coverage in words", () => {
    expect(formatCoverage(19, 21)).toBe("19 of 21 days");
  });

  it("recognises a fully covered window", () => {
    expect(isFullyCovered({ observed_days: 7, expected_days: 7 })).toBe(true);
    expect(isFullyCovered({ observed_days: 5, expected_days: 7 })).toBe(false);
  });
});
