/* The snapshot is authoritative; Web PubSub is the live notification path. */
class InvestigationState {
    constructor(operationId) {
        this.operationId = operationId;
        this.value = { operation_id: operationId, sequence: 0, text: "", progress: 0,
            status: "pending", stage: "Loading", worker_starts: 0 };
        this.pending = new Map();
        this.liveEvents = 0;
        this.duplicates = 0;
    }

    receive(event) {
        if (event.operation_id !== this.operationId) return "other-operation";
        if (event.schema_version !== 1 || !Number.isSafeInteger(event.sequence) ||
            event.sequence < 1 || event.event_id !== `${this.operationId}:${event.sequence}` ||
            !["progress", "findings", "completed", "failed"].includes(event.type) ||
            !event.payload || typeof event.payload !== "object") {
            throw new Error("Invalid investigation event.");
        }
        if (event.sequence <= this.value.sequence || this.pending.has(event.sequence)) {
            this.duplicates += 1;
            return "duplicate";
        }
        this.liveEvents += 1;
        this.pending.set(event.sequence, event);
        this.drain();
        return this.pending.size ? "gap" : "applied";
    }

    drain() {
        let event;
        while ((event = this.pending.get(this.value.sequence + 1))) {
            const payload = event.payload;
            if (event.type === "findings") {
                if (typeof payload.text !== "string") throw new Error("Invalid findings.");
                this.value.text += payload.text;
            } else if (event.type === "progress") {
                if (!Number.isInteger(payload.progress) || payload.progress < 0 ||
                    payload.progress >= 100 || typeof payload.stage !== "string") {
                    throw new Error("Invalid progress.");
                }
                Object.assign(this.value, { progress: payload.progress,
                    stage: payload.stage, status: "running" });
            } else if (event.type === "completed") {
                if (payload.result_ref !== `/api/operations/${this.operationId}/result`) {
                    throw new Error("Invalid result reference.");
                }
                Object.assign(this.value, { status: "completed", stage: "Complete",
                    progress: 100, result_ref: payload.result_ref });
            } else {
                Object.assign(this.value, { status: "failed", error: payload.error,
                    stage: "Investigation failed" });
            }
            this.value.sequence = event.sequence;
            this.pending.delete(event.sequence);
        }
    }

    snapshot(snapshot) {
        if (snapshot.operation_id !== this.operationId || !Number.isSafeInteger(snapshot.sequence) ||
            snapshot.sequence < 0 || typeof snapshot.text !== "string") {
            throw new Error("Invalid investigation snapshot.");
        }
        if (snapshot.sequence >= this.value.sequence) this.value = { ...snapshot };
        for (const sequence of this.pending.keys()) {
            if (sequence <= this.value.sequence) this.pending.delete(sequence);
        }
        this.drain();
    }
}

globalThis.InvestigationState = InvestigationState;

if (typeof document !== "undefined") {
    (async function () {
        const el = (id) => document.getElementById(id);
        const csrf = document.querySelector('meta[name="csrf-token"]').content;
        const terminal = new Set(["completed", "failed", "interrupted"]);
        let state = null;
        let client = null;
        let generation = 0;
        let reconciling = null;
        let intentionalDisconnect = false;
        let sdkPromise = null;
        let snapshotInFlight = false;
        let actionInFlight = false;
        const queuedEvents = [];

        function showError(error) {
            el("error").textContent = error.message || String(error);
            el("error").hidden = false;
        }

        async function api(path, method = "GET", data) {
            const response = await fetch(path, {
                method, credentials: "same-origin", cache: "no-store",
                headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
                body: data === undefined ? undefined : JSON.stringify(data),
            });
            const body = await response.json();
            if (!response.ok) throw new Error(body.error || `Request failed (${response.status}).`);
            return body;
        }

        function render() {
            if (!state) {
                el("start").disabled = true;
                el("load-result").disabled = true;
                return;
            }
            const value = state.value;
            el("processing").textContent = value.status;
            el("stage").textContent = value.stage;
            el("progress").value = value.progress;
            el("findings").textContent = value.text;
            el("diagnostics").textContent =
                `Snapshot sequence: ${value.sequence} | Live events: ${state.liveEvents}` +
                ` | Worker starts: ${value.worker_starts} | Duplicate events ignored: ${state.duplicates}`;
            el("delivery").textContent = value.delivery_error || "";
            el("load-result").disabled = actionInFlight || value.status !== "completed";
            el("start").disabled = actionInFlight || value.status !== "pending" || el("persona").value !== "oncall";
            if (value.error) showError(new Error(value.error));
        }

        function receive(event, epoch) {
            if (epoch !== generation || !state) return;
            if (snapshotInFlight) {
                queuedEvents.push(event);
                return;
            }
            if (state.receive(event) === "gap") refresh().catch(showError);
            render();
        }

        async function refresh() {
            if (!state) return;
            if (reconciling) return reconciling;
            const epoch = generation;
            const selected = state;
            snapshotInFlight = true;
            const work = (async () => {
                try {
                    const snapshot = await api(`/api/operations/${selected.operationId}`);
                    if (epoch !== generation || selected !== state) return;
                    selected.snapshot(snapshot);
                    for (const event of queuedEvents.splice(0)) selected.receive(event);
                    render();
                } catch (error) {
                    if (epoch === generation) throw error;
                } finally {
                    if (epoch === generation) snapshotInFlight = false;
                }
            })();
            reconciling = work;
            try {
                await work;
            } finally {
                if (reconciling === work) reconciling = null;
            }
        }

        async function stop() {
            const epoch = ++generation;
            reconciling = null;
            snapshotInFlight = false;
            queuedEvents.length = 0;
            const old = client;
            client = null;
            if (old) await old.stop();
            return epoch;
        }

        async function connect() {
            if (!state) throw new Error("Create or open an investigation first.");
            const epoch = await stop();
            if (epoch !== generation) return;
            intentionalDisconnect = false;
            el("connection").textContent = "Connecting";
            try {
                if (!sdkPromise) {
                    sdkPromise = import(
                        "https://esm.sh/@azure/web-pubsub-client@1.1.0?bundle&target=es2022&conditions=browser"
                    ).catch((error) => { sdkPromise = null; throw error; });
                }
                const { WebPubSubClient } = await sdkPromise;
                if (epoch !== generation) return;
                const operationId = state.operationId;
                const negotiation = () => api(`/api/operations/${operationId}/negotiate`, "POST");
                const details = await negotiation();
                if (epoch !== generation) return;
                const next = new WebPubSubClient({
                    getClientAccessUrl: async () => (await negotiation()).url,
                });
                client = next;
                // REST group publishing arrives as a server message, not a client group message.
                next.on("server-message", (message) => {
                    if (epoch !== generation) return;
                    try {
                        receive(typeof message.message.data === "string" ?
                            JSON.parse(message.message.data) : message.message.data, epoch);
                    } catch (error) { showError(error); }
                });
                next.on("connected", () => {
                    if (epoch === generation) {
                        el("connection").textContent = "Connected";
                        refresh().catch(showError);
                    }
                });
                next.on("disconnected", () => {
                    if (epoch === generation) el("connection").textContent = "Disconnected; recovering";
                });
                next.on("rejoin-group-failed", () => {
                    if (epoch === generation) {
                        el("connection").textContent = "Group recovery failed";
                        showError(new Error("Group recovery failed. Select Reconnect to retry."));
                    }
                });
                next.on("stopped", () => {
                    if (epoch === generation && !intentionalDisconnect) {
                        el("connection").textContent = "Stopped";
                        showError(new Error("Live delivery stopped. Select Reconnect to retry."));
                    }
                });
                await next.start();
                if (epoch !== generation) return;
                await next.joinGroup(details.group);
                if (epoch !== generation) return;
                await refresh();
            } catch (error) {
                if (epoch === generation) {
                    el("connection").textContent = "Connection failed";
                    throw error;
                }
            }
        }

        async function open(operationId) {
            if (!/^[a-f0-9]{32}$/.test(operationId)) throw new Error("Enter a valid investigation ID.");
            const epoch = await stop();
            if (epoch !== generation) return;
            state = new InvestigationState(operationId);
            el("operation-id").value = operationId;
            el("result").textContent = "";
            el("error").hidden = true;
            el("start").disabled = true;
            const url = new URL(location.href);
            url.searchParams.set("operation", operationId);
            history.replaceState(null, "", url);
            el("share-link").href = url.href;
            el("share-link").hidden = false;
            await refresh();
            if (epoch !== generation) return;
            await connect();
        }

        function action(id, handler) {
            el(id).addEventListener(id.endsWith("-form") ? "submit" : "click", async (event) => {
                event.preventDefault();
                if (actionInFlight) return;
                actionInFlight = true;
                el("error").hidden = true;
                const buttons = document.querySelectorAll("button");
                buttons.forEach((button) => { button.disabled = true; });
                try { await handler(); } catch (error) { showError(error); }
                finally {
                    actionInFlight = false;
                    buttons.forEach((button) => { button.disabled = false; });
                    render();
                }
            });
        }

        action("persona-form", async () => {
            await stop();
            el("connection").textContent = "Disconnected";
            const selection = await api("/api/persona", "POST", { persona: el("persona").value });
            el("persona-label").textContent = el("persona").selectedOptions[0].textContent;
            if (state) await open(state.operationId);
            return selection;
        });
        action("create-form", async () => {
            const operation = await api("/api/operations", "POST");
            await open(operation.operation_id);
        });
        action("open-form", () => open(el("operation-id").value.trim()));
        action("start-form", async () => {
            if (!state) throw new Error("Open an investigation first.");
            await api(`/api/operations/${state.operationId}/start`, "POST");
            await refresh();
        });
        action("disconnect", async () => {
            intentionalDisconnect = true;
            await stop();
            el("connection").textContent = "Disconnected by you";
        });
        action("reconnect", connect);
        action("refresh", refresh);
        action("load-result", async () => {
            if (!state) return;
            const selected = state;
            const result = await api(`/api/operations/${selected.operationId}/result`);
            if (selected === state) el("result").textContent = result.text;
        });
        setInterval(() => {
            if (state && !terminal.has(state.value.status) && !intentionalDisconnect) {
                refresh().catch(showError);
            }
        }, 5000);
        const initial = new URL(location.href).searchParams.get("operation");
        if (initial) await open(initial);
    })().catch((error) => {
        document.getElementById("error").textContent = error.message;
        document.getElementById("error").hidden = false;
    });
}
