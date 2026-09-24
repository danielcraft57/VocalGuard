/** Tests moteur sync offline. */
import { createMemoryDb } from "../db/client";
import { applySyncDelta, enqueuePendingAction, replayPendingActions, syncFromServer } from "./sync";

describe("sync", () => {
  it("merge delta appels et voicemails", async () => {
    const db = createMemoryDb();
    const n = await applySyncDelta(db, {
      calls: [{ id: 5, phone_number: "0611111111", status: "missed", duration: 0 }],
      voicemails: [{ id: 9, phone_number: "0622222222", is_read: false, duration: 12, created_at: "2026-01-01T12:00:00Z" }],
    });
    expect(n).toBe(2);
  });

  it("conserve le numero si le delta STT ne le renvoie plus", async () => {
    const db = createMemoryDb();
    await applySyncDelta(db, {
      voicemails: [
        {
          id: 3,
          phone_number: "0611223344",
          caller_name: "Paul",
          is_read: false,
          duration: 8,
          created_at: "2026-01-02T10:00:00Z",
        },
      ],
    });
    await applySyncDelta(db, {
      voicemails: [
        {
          id: 3,
          phone_number: "",
          caller_name: null,
          transcription: "Bonjour c est Paul",
          is_read: false,
          duration: 8,
          created_at: "2026-01-02T10:00:00Z",
        },
      ],
    });
    const row = await db.getFirstAsync<{ caller_number: string; caller_name: string | null; transcription: string | null }>(
      "SELECT caller_number, caller_name, transcription FROM voicemails WHERE id = ?",
      [3],
    );
    expect(row?.caller_number).toBe("0611223344");
    expect(row?.caller_name).toBe("Paul");
    expect(row?.transcription).toBe("Bonjour c est Paul");
  });

  it("conserve la transcription locale si le delta renvoie null", async () => {
    const db = createMemoryDb();
    await applySyncDelta(db, {
      voicemails: [
        {
          id: 4,
          phone_number: "0611223344",
          is_read: false,
          duration: 8,
          created_at: "2026-01-02T10:00:00Z",
          transcription: "deja transcrit",
        },
      ],
    });
    await applySyncDelta(db, {
      voicemails: [
        {
          id: 4,
          phone_number: "0611223344",
          is_read: false,
          duration: 8,
          created_at: "2026-01-02T10:00:00Z",
          transcription: null,
        },
      ],
    });
    const row = await db.getFirstAsync<{ transcription: string | null }>(
      "SELECT transcription FROM voicemails WHERE id = ?",
      [4],
    );
    expect(row?.transcription).toBe("deja transcrit");
  });

  it("stocke transcription et cues karaoke des appels", async () => {
    const db = createMemoryDb();
    await applySyncDelta(db, {
      calls: [
        {
          id: 163,
          phone_number: "0780833873",
          status: "answered",
          duration: 14,
          transcription: "Voila, voila, c est Louis.",
          transcription_cues: [
            {
              start: 0,
              end: 2,
              words: [
                { text: "Voila,", start: 0, end: 0.5 },
                { text: "voila,", start: 0.5, end: 1 },
                { text: "c", start: 1, end: 1.2 },
                { text: "est", start: 1.2, end: 1.5 },
                { text: "Louis.", start: 1.5, end: 2 },
              ],
            },
          ],
          osint: { operator: "Orange", reputation: "neutral" },
        },
      ],
    });
    const row = await db.getFirstAsync<{
      transcription: string | null;
      transcription_cues_json: string | null;
      osint_json: string | null;
    }>("SELECT transcription, transcription_cues_json, osint_json FROM calls WHERE id = ?", [163]);
    expect(row?.transcription).toBe("Voila, voila, c est Louis.");
    expect(row?.transcription_cues_json).toContain("Louis");
    expect(row?.osint_json).toContain("Orange");
  });

  it("conserve transcription et cues appels si le delta renvoie null", async () => {
    const db = createMemoryDb();
    await applySyncDelta(db, {
      calls: [
        {
          id: 10,
          phone_number: "0600000000",
          transcription: "deja la",
          transcription_cues: [{ start: 0, end: 1, text: "deja la" }],
        },
      ],
    });
    await applySyncDelta(db, {
      calls: [
        {
          id: 10,
          phone_number: "0600000000",
          transcription: null,
          transcription_cues: null,
        },
      ],
    });
    const row = await db.getFirstAsync<{
      transcription: string | null;
      transcription_cues_json: string | null;
    }>("SELECT transcription, transcription_cues_json FROM calls WHERE id = ?", [10]);
    expect(row?.transcription).toBe("deja la");
    expect(row?.transcription_cues_json).toContain("deja la");
  });

  it("enqueue pending action offline", async () => {
    const db = createMemoryDb();
    await enqueuePendingAction(db, "mark_read", { voicemail_id: 3 });
    const rows = await db.getAllAsync<{ action: string }>("SELECT action FROM pending_actions");
    expect(rows).toHaveLength(1);
  });

  it("replay pending actions", async () => {
    const db = createMemoryDb();
    await enqueuePendingAction(db, "trusted_import", { phone: "0612345678" });
    const executed: string[] = [];
    const done = await replayPendingActions(db, async (action) => {
      executed.push(action);
    });
    expect(done).toBe(1);
    expect(executed).toEqual(["trusted_import"]);
  });

  it("syncFromServer appelle l API delta", async () => {
    const db = createMemoryDb();
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        calls: [{ id: 1, phone_number: "0600000000" }],
        server_time: "2026-02-01T10:00:00Z",
      }),
    }) as jest.Mock;
    const merged = await syncFromServer(db, { baseUrl: "https://test", token: "tok" }, null);
    expect(merged).toBe(1);
  });
});
