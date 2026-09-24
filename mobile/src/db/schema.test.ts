/** Tests schema SQLite. */
import { MIGRATION_V1, SCHEMA_VERSION, parseCallCuesJson, parseCallOsint } from "./schema";
import { createMemoryDb, migrateDb } from "./client";

describe("schema SQLite", () => {
  it("applique la migration v1", async () => {
    const db = createMemoryDb();
    await migrateDb(db);
    expect(SCHEMA_VERSION).toBe(4);
    expect(MIGRATION_V1).toContain("CREATE TABLE IF NOT EXISTS calls");
  });

  it("supporte upsert appels", async () => {
    const db = createMemoryDb();
    await db.runAsync(
      "INSERT OR REPLACE INTO calls (id, phone_number, caller_name, status, call_time, duration, synced_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
      [1, "0612345678", "Test", "completed", "2026-01-01", 30, "2026-01-01T00:00:00Z"],
    );
    const rows = await db.getAllAsync<{ phone_number: string }>("SELECT phone_number FROM calls");
    expect(rows[0].phone_number).toBe("0612345678");
  });

  it("parseCallOsint et parseCallCuesJson", () => {
    expect(parseCallOsint('{"operator":"Orange"}')?.operator).toBe("Orange");
    expect(parseCallOsint("nope")).toBeNull();
    expect(parseCallCuesJson('[{"start":0,"end":1,"text":"hi"}]')).toHaveLength(1);
    expect(parseCallCuesJson("[]")).toBeNull();
    expect(parseCallCuesJson(null)).toBeNull();
  });
});
