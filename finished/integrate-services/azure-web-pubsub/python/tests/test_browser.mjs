import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";

const source = fs.readFileSync(new URL("../client/static/js/investigation.js", import.meta.url), "utf8");
const context = vm.createContext({});
vm.runInContext(source, context);
const State = context.InvestigationState;
const View = context.InvestigationView;
const id = "a".repeat(32);
const event = (sequence, type, payload, operationId = id) => ({
    schema_version: 1, operation_id: operationId, sequence,
    event_id: `${operationId}:${sequence}`, type, payload,
});
const snapshot = (sequence = 0, text = "") => ({
    operation_id: id, sequence, text, status: "running",
    stage: "Investigating", progress: 10, worker_starts: 1,
});

test("duplicate events never duplicate findings", () => {
    const state = new State(id);
    const first = event(1, "findings", { text: "one " });
    state.receive(first);
    assert.equal(state.receive(first), "duplicate");
    assert.equal(state.value.text, "one ");
    assert.equal(state.liveEvents, 1);
    assert.equal(state.duplicates, 1);
});

test("snapshots do not count as live events and already-covered events count as ignored", () => {
    const state = new State(id);
    state.snapshot(snapshot(6, "Stored findings. "));
    assert.equal(state.liveEvents, 0);
    assert.equal(state.duplicates, 0);
    assert.equal(state.receive(event(6, "findings", { text: "already stored" })), "duplicate");
    assert.equal(state.liveEvents, 0);
    assert.equal(state.duplicates, 1);
    state.receive(event(7, "findings", { text: "New live findings." }));
    assert.equal(state.liveEvents, 1);
    assert.equal(state.duplicates, 1);
    assert.equal(state.value.text, "Stored findings. New live findings.");
});

test("a gap waits for reconciliation without appending incomplete text", () => {
    const state = new State(id);
    assert.equal(state.receive(event(3, "findings", { text: "three" })), "gap");
    assert.equal(state.value.text, "");
    state.snapshot(snapshot(2, "one two "));
    assert.equal(state.value.text, "one two three");
    assert.equal(state.value.sequence, 3);
    assert.equal(state.pending.size, 0);
});

test("events arriving around a snapshot watermark are applied once", () => {
    const state = new State(id);
    state.receive(event(2, "findings", { text: "two" }));
    state.snapshot(snapshot(2, "one two"));
    assert.equal(state.value.text, "one two");
    assert.equal(state.pending.size, 0);
    state.receive(event(3, "findings", { text: " three" }));
    state.snapshot(snapshot(2, "stale"));
    assert.equal(state.value.text, "one two three");
});

test("reordered events drain in sequence", () => {
    const state = new State(id);
    state.receive(event(2, "findings", { text: "two" }));
    state.receive(event(1, "findings", { text: "one " }));
    assert.equal(state.value.text, "one two");
});

test("missed completion is restored from the authoritative snapshot", () => {
    const state = new State(id);
    state.snapshot({ ...snapshot(8, "complete result"), status: "completed", progress: 100,
        result_ref: `/api/operations/${id}/result` });
    assert.equal(state.value.status, "completed");
    assert.equal(state.value.text, "complete result");
    assert.equal(state.liveEvents, 0);
});

test("another operation cannot contaminate the selected findings", () => {
    const state = new State(id);
    assert.equal(state.receive(event(1, "findings", { text: "wrong" }, "b".repeat(32))), "other-operation");
    assert.equal(state.value.text, "");
    assert.throws(() => state.snapshot({ ...snapshot(), operation_id: "b".repeat(32) }));
});

test("completion and validation preserve the exact result reference", () => {
    const state = new State(id);
    assert.throws(() => state.receive({ ...event(1, "findings", { text: "x" }), schema_version: 2 }));
    state.receive(event(1, "findings", { text: "result" }));
    state.receive(event(2, "completed", { result_ref: `/api/operations/${id}/result` }));
    assert.equal(state.value.status, "completed");
    assert.equal(state.value.text, "result");
});

test("start acknowledgement updates worker count without overwriting newer live progress", () => {
    const state = new State(id);
    state.receive(event(1, "progress", { progress: 8, stage: "Inspecting application logs" }));
    state.snapshot({ ...snapshot(), stage: "Starting investigation" });
    assert.equal(state.value.sequence, 1);
    assert.equal(state.value.stage, "Inspecting application logs");
    assert.equal(state.value.worker_starts, 1);
});

function root(token) {
    const fields = new Map();
    const availableFields = new Set(["connection", "processing", "stage", "progress",
        "findings", "empty-findings", "delivery", "diagnostics", "error"].map((name) => `[data-field="${name}"]`));
    const buttons = ["disconnect", "reconnect"].map((action) => ({
        dataset: { action }, disabled: true, addEventListener() {},
    }));
    return {
        dataset: { token },
        querySelector(selector) {
            if (!availableFields.has(selector)) return null;
            if (!fields.has(selector)) fields.set(selector, { textContent: "", hidden: false, value: 0 });
            return fields.get(selector);
        },
        querySelectorAll() { return buttons; },
    };
}

function workspace() {
    const clients = [];
    const requests = [];
    let current = { ...snapshot(), status: "pending", stage: "Ready to start", worker_starts: 0 };
    class Client {
        constructor(credentials) {
            this.credentials = credentials;
            this.handlers = {};
            this.stopped = false;
            clients.push(this);
        }
        on(name, handler) { this.handlers[name] = handler; }
        async start() {
            await this.credentials.getClientAccessUrl();
            this.handlers.connected();
        }
        async joinGroup(group) { this.group = group; }
        async stop() { this.stopped = true; this.handlers.stopped(); }
    }
    const request = async (path, method, data, token) => {
        requests.push({ path, method, token });
        if (path.endsWith("/negotiate")) return { url: "wss://test.invalid", group: `investigation-${id}` };
        return { ...current };
    };
    const make = (token) => new View(root(token), request, async () => ({ WebPubSubClient: Client }), () => {});
    return { clients, requests, make, setSnapshot(value) { current = value; } };
}

test("the findings placeholder is replaced by real text and restored for a new investigation", async () => {
    const app = workspace();
    const view = app.make("oncall-context");
    await view.select(id);
    assert.equal(view.field("empty-findings").hidden, false);
    assert.equal(view.field("findings").hidden, true);
    assert.equal(view.field("findings").textContent, "");
    view.receive(event(1, "findings", { text: "Actual findings." }), view.generation);
    assert.equal(view.field("empty-findings").hidden, true);
    assert.equal(view.field("findings").hidden, false);
    assert.equal(view.field("findings").textContent, "Actual findings.");
    await view.select("b".repeat(32));
    assert.equal(view.field("empty-findings").hidden, false);
    assert.equal(view.field("findings").hidden, true);
    assert.equal(view.field("findings").textContent, "");
});

test("two same-page views use distinct contexts and negotiate once per connection", async () => {
    const app = workspace();
    const oncall = app.make("oncall-context");
    const database = app.make("database-context");
    await Promise.all([oncall.select(id), database.select(id)]);
    await Promise.all([oncall.connect(), database.connect()]);
    assert.equal(oncall.joined, true);
    assert.equal(database.joined, true);
    assert.equal(app.clients.length, 2);
    const negotiations = app.requests.filter((request) => request.path.endsWith("/negotiate"));
    assert.equal(negotiations.length, 2);
    assert.deepEqual(negotiations.map((request) => request.token).sort(), ["database-context", "oncall-context"]);
    assert.equal(oncall.state.value.worker_starts, 0);
    assert.equal(database.state.value.worker_starts, 0);
});

test("group notifications update findings and live diagnostics without polling", async () => {
    const app = workspace();
    const view = app.make("oncall-context");
    await view.select(id);
    await view.connect();
    const receive = app.clients[0].handlers["group-message"];
    assert.equal(typeof receive, "function");
    const message = { message: { data: event(1, "findings", { text: "Live findings." }) } };
    receive(message);
    assert.equal(view.state.value.text, "Live findings.");
    assert.equal(view.state.liveEvents, 1);
    assert.match(view.field("diagnostics").textContent, /Live events: 1/);
    receive(message);
    assert.equal(view.state.value.text, "Live findings.");
    assert.equal(view.state.duplicates, 1);
    assert.match(view.field("diagnostics").textContent, /Duplicates ignored: 1/);
});

test("reconnect is disabled while connected and enabled after disconnection", async () => {
    const app = workspace();
    const view = app.make("oncall-context");
    const button = name => view.root.querySelectorAll("[data-action]")
        .find(control => control.dataset.action === name);
    await view.select(id);
    await view.connect();
    assert.equal(button("disconnect").disabled, false);
    assert.equal(button("reconnect").disabled, true);

    app.clients[0].handlers.disconnected();
    assert.equal(button("reconnect").disabled, false);

    await view.action("disconnect");
    assert.equal(button("disconnect").disabled, true);
    assert.equal(button("reconnect").disabled, false);

    await view.action("reconnect");
    assert.equal(button("disconnect").disabled, false);
    assert.equal(button("reconnect").disabled, true);
});

test("disconnecting one view leaves the other live and reconnect restores its snapshot", async () => {
    const app = workspace();
    const oncall = app.make("oncall-context");
    const database = app.make("database-context");
    await Promise.all([oncall.select(id), database.select(id)]);
    await Promise.all([oncall.connect(), database.connect()]);
    await database.action("disconnect");
    assert.equal(app.clients[1].stopped, true);
    assert.equal(app.clients[0].stopped, false);
    const message = { message: { data: event(1, "findings", { text: "live findings" }) } };
    app.clients[0].handlers["group-message"](message);
    app.clients[1].handlers["group-message"](message);
    assert.equal(oncall.state.value.text, "live findings");
    assert.equal(database.state.value.text, "");
    app.setSnapshot({ ...snapshot(1, "live findings"), worker_starts: 1 });
    await database.action("reconnect");
    assert.equal(database.state.value.text, oncall.state.value.text);
    assert.equal(database.state.value.worker_starts, 1);
    assert.equal(database.joined, true);
    assert.equal(app.requests.filter((request) => request.path.endsWith("/start")).length, 0);
});

test("a failed observer connection does not stop the other observer", async () => {
    const app = workspace();
    const oncall = app.make("oncall-context");
    const database = app.make("database-context");
    await Promise.all([oncall.select(id), database.select(id)]);
    await oncall.connect();
    database.request = async () => { throw new Error("Observer access denied"); };
    await assert.rejects(database.connect(), /Observer access denied/);
    assert.equal(oncall.joined, true);
    assert.equal(app.clients[0].stopped, false);
    assert.equal(database.joined, false);
});
