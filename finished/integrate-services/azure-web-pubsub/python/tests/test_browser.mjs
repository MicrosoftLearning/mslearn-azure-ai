import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";

const source = fs.readFileSync(new URL("../client/static/js/investigation.js", import.meta.url), "utf8");
const context = vm.createContext({});
vm.runInContext(source, context);
const State = context.InvestigationState;
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
