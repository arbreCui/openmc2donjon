import { describe, expect, it } from "vitest";
import {
  RECENT_CAPACITY,
  mergeRecentPick,
  parseStoredRecent,
  serializeRecent,
} from "./recentHandoffs";

describe("mergeRecentPick", () => {
  it("prepends to an empty list", () => {
    expect(mergeRecentPick([], "/a.h5", 100)).toEqual([
      { path: "/a.h5", selectedAt: 100 },
    ]);
  });

  it("prepends without touching existing entries when no duplicate", () => {
    const before = [
      { path: "/a.h5", selectedAt: 100 },
      { path: "/b.h5", selectedAt: 50 },
    ];
    expect(mergeRecentPick(before, "/c.h5", 200)).toEqual([
      { path: "/c.h5", selectedAt: 200 },
      { path: "/a.h5", selectedAt: 100 },
      { path: "/b.h5", selectedAt: 50 },
    ]);
  });

  it("dedupes and refreshes the timestamp when path is re-picked", () => {
    const before = [
      { path: "/a.h5", selectedAt: 100 },
      { path: "/b.h5", selectedAt: 50 },
    ];
    expect(mergeRecentPick(before, "/b.h5", 200)).toEqual([
      { path: "/b.h5", selectedAt: 200 },
      { path: "/a.h5", selectedAt: 100 },
    ]);
  });

  it("prunes the oldest entry once over capacity", () => {
    // Real usage keeps the list newest-first (every merge prepends),
    // so the fixture mirrors that: ``/p0.h5`` is most-recently-picked,
    // ``/p7.h5`` is oldest and the one we expect to fall off the tail.
    const before = Array.from({ length: RECENT_CAPACITY }, (_, i) => ({
      path: `/p${i}.h5`,
      selectedAt: RECENT_CAPACITY - i,
    }));
    const after = mergeRecentPick(before, "/fresh.h5", 999);
    expect(after).toHaveLength(RECENT_CAPACITY);
    expect(after[0]).toEqual({ path: "/fresh.h5", selectedAt: 999 });
    expect(
      after.find((e) => e.path === `/p${RECENT_CAPACITY - 1}.h5`),
    ).toBeUndefined();
  });
});

describe("parseStoredRecent", () => {
  it("returns an empty list for null or empty input", () => {
    expect(parseStoredRecent(null)).toEqual([]);
    expect(parseStoredRecent("")).toEqual([]);
  });

  it("returns an empty list for malformed JSON", () => {
    expect(parseStoredRecent("{not json")).toEqual([]);
  });

  it("returns an empty list when the schema version doesn't match", () => {
    const raw = JSON.stringify({
      version: 99,
      entries: [{ path: "/a.h5", selectedAt: 1 }],
    });
    expect(parseStoredRecent(raw)).toEqual([]);
  });

  it("drops individual entries with the wrong shape but keeps the rest", () => {
    const raw = JSON.stringify({
      version: 1,
      entries: [
        { path: "/good.h5", selectedAt: 1 },
        { path: 42, selectedAt: 1 },
        { path: "/missing-ts.h5" },
        null,
        { path: "/also-good.h5", selectedAt: 2 },
      ],
    });
    expect(parseStoredRecent(raw)).toEqual([
      { path: "/good.h5", selectedAt: 1 },
      { path: "/also-good.h5", selectedAt: 2 },
    ]);
  });

  it("round-trips via serializeRecent", () => {
    const list = [
      { path: "/a.h5", selectedAt: 100 },
      { path: "/b.h5", selectedAt: 50 },
    ];
    expect(parseStoredRecent(serializeRecent(list))).toEqual(list);
  });
});
