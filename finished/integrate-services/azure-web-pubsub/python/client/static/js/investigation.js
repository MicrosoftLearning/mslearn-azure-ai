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
        this.value.worker_starts = Math.max(this.value.worker_starts || 0, snapshot.worker_starts || 0);
        for (const sequence of this.pending.keys()) {
            if (sequence <= this.value.sequence) this.pending.delete(sequence);
        }
        this.drain();
    }
}

globalThis.InvestigationState = InvestigationState;

class InvestigationView {
    constructor(root, request, loadSdk, changed) {
        this.root = root;
        this.request = (path, method, data) => request(path, method, data, root.dataset.token);
        this.loadSdk = loadSdk;
        this.changed = changed;
        this.state = null;
        this.client = null;
        this.generation = 0;
        this.joined = false;
        this.intentionalDisconnect = false;
        this.reconciling = null;
        this.snapshotInFlight = false;
        this.queuedEvents = [];
        this.busy = false;
        this.workspaceBusy = false;
        for (const button of root.querySelectorAll("[data-action]")) {
            button.addEventListener("click", () => this.action(button.dataset.action));
        }
    }

    field(name) { return this.root.querySelector(`[data-field="${name}"]`); }

    showError(error) {
        this.field("error").textContent = error.message || String(error);
        this.field("error").hidden = false;
    }

    render() {
        const value = this.state?.value;
        if (value) {
            this.field("processing").textContent = value.status;
            this.field("stage").textContent = value.stage;
            this.field("progress").value = value.progress;
            this.field("findings").textContent = value.text;
            this.field("findings").hidden = !value.text;
            this.field("empty-findings").hidden = Boolean(value.text);
            this.field("delivery").textContent = value.delivery_error || "";
            this.field("diagnostics").textContent = `Sequence: ${value.sequence}` +
                ` | Live events: ${this.state.liveEvents} | Worker starts: ${value.worker_starts}` +
                ` | Duplicates ignored: ${this.state.duplicates}`;
            if (value.error) this.showError(new Error(value.error));
        }
        for (const button of this.root.querySelectorAll("[data-action]")) {
            button.disabled = !value || this.busy || this.workspaceBusy ||
                (button.dataset.action === "reconnect" && this.joined) ||
                (button.dataset.action === "disconnect" && !this.client);
        }
        this.changed();
    }

    acceptSnapshot(snapshot) {
        this.state.snapshot(snapshot);
        this.render();
    }

    async select(operationId) {
        await this.stop();
        this.state = new InvestigationState(operationId);
        this.intentionalDisconnect = false;
        this.field("connection").textContent = "Not connected";
        this.field("error").hidden = true;
        this.render();
    }

    receive(event, epoch) {
        if (epoch !== this.generation || !this.state) return;
        if (this.snapshotInFlight) {
            this.queuedEvents.push(event);
            return;
        }
        if (this.state.receive(event) === "gap") this.refresh().catch((error) => this.showError(error));
        this.render();
    }

    async refresh() {
        if (!this.state) return;
        if (this.reconciling) return this.reconciling;
        const epoch = this.generation;
        const selected = this.state;
        this.snapshotInFlight = true;
        const work = (async () => {
            try {
                const snapshot = await this.request(`/api/operations/${selected.operationId}`);
                if (epoch !== this.generation || selected !== this.state) return;
                selected.snapshot(snapshot);
                for (const event of this.queuedEvents.splice(0)) selected.receive(event);
                this.render();
            } catch (error) {
                if (epoch === this.generation) throw error;
            } finally {
                if (epoch === this.generation) this.snapshotInFlight = false;
            }
        })();
        this.reconciling = work;
        try { await work; }
        finally { if (this.reconciling === work) this.reconciling = null; }
    }

    async stop() {
        const epoch = ++this.generation;
        this.reconciling = null;
        this.snapshotInFlight = false;
        this.queuedEvents.length = 0;
        this.joined = false;
        const old = this.client;
        this.client = null;
        if (old) await old.stop();
        return epoch;
    }

    async connect() {
        if (!this.state) throw new Error("Create an investigation first.");
        const epoch = await this.stop();
        if (epoch !== this.generation) return;
        this.intentionalDisconnect = false;
        this.field("error").hidden = true;
        this.field("connection").textContent = "Connecting";
        this.render();
        try {
            const { WebPubSubClient } = await this.loadSdk();
            if (epoch !== this.generation) return;
            const operationId = this.state.operationId;
            const negotiate = () => this.request(`/api/operations/${operationId}/negotiate`, "POST");
            const details = await negotiate();
            if (epoch !== this.generation) return;
            let firstUrl = details.url;
            const next = new WebPubSubClient({
                getClientAccessUrl: async () => {
                    if (firstUrl) {
                        const url = firstUrl;
                        firstUrl = null;
                        return url;
                    }
                    return (await negotiate()).url;
                },
            });
            this.client = next;
            let initialConnection = true;
            const restore = async () => {
                await next.joinGroup(details.group);
                if (epoch !== this.generation) return;
                this.joined = true;
                this.field("connection").textContent = "Connected";
                this.render();
                await this.refresh();
            };
            const report = (error) => { if (epoch === this.generation) this.showError(error); };
            next.on("group-message", (message) => {
                if (epoch !== this.generation) return;
                try {
                    this.receive(typeof message.message.data === "string" ?
                        JSON.parse(message.message.data) : message.message.data, epoch);
                } catch (error) { report(error); }
            });
            next.on("connected", () => {
                if (epoch !== this.generation) return;
                this.field("connection").textContent = "Joining investigation";
                if (!initialConnection) restore().catch(report);
            });
            next.on("disconnected", () => {
                if (epoch !== this.generation) return;
                this.joined = false;
                this.field("connection").textContent = "Disconnected; recovering";
                this.render();
            });
            next.on("rejoin-group-failed", () => {
                if (epoch !== this.generation) return;
                this.joined = false;
                this.field("connection").textContent = "Group recovery failed";
                this.showError(new Error("Select Reconnect for this view to restore live delivery."));
                this.render();
            });
            next.on("stopped", () => {
                if (epoch !== this.generation || this.intentionalDisconnect) return;
                this.joined = false;
                this.field("connection").textContent = "Stopped";
                this.showError(new Error("Live delivery stopped. Select Reconnect for this view."));
                this.render();
            });
            await next.start();
            if (epoch !== this.generation) return;
            await restore();
            initialConnection = false;
        } catch (error) {
            if (epoch === this.generation) {
                this.joined = false;
                this.field("connection").textContent = "Connection failed";
                this.render();
                throw error;
            }
        }
    }

    async action(name) {
        if (this.busy || this.workspaceBusy) return;
        this.busy = true;
        this.field("error").hidden = true;
        this.render();
        try {
            if (name === "disconnect") {
                this.intentionalDisconnect = true;
                await this.stop();
                this.field("connection").textContent = "Disconnected by you";
            } else if (name === "reconnect") await this.connect();
            else throw new Error("Unknown observer action.");
        } catch (error) { this.showError(error); }
        finally { this.busy = false; this.render(); }
    }
}

globalThis.InvestigationView = InvestigationView;

if (typeof document !== "undefined") {
    (async function () {
        const el = (id) => document.getElementById(id);
        const csrf = document.querySelector('meta[name="csrf-token"]').content;
        const terminal = new Set(["completed", "failed", "interrupted"]);
        let operationId = null;
        let workspaceBusy = false;
        let sdkPromise = null;
        const views = [];
        const activity = (text) => {
            el("activity").textContent = text;
            el("activity").hidden = false;
        };
        const showError = (error) => {
            el("error").textContent = error.message || String(error);
            el("error").hidden = false;
        };
        async function api(path, method = "GET", data, token = views[0].root.dataset.token) {
            const response = await fetch(path, {
                method, credentials: "same-origin", cache: "no-store",
                headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "X-Demo-Viewer": token },
                body: data === undefined ? undefined : JSON.stringify(data),
            });
            const body = await response.json();
            if (!response.ok) throw new Error(body.error || `Request failed (${response.status}).`);
            return body;
        }
        function loadSdk() {
            if (!sdkPromise) sdkPromise = import(
                "https://esm.sh/@azure/web-pubsub-client@1.1.0?bundle&target=es2022&conditions=browser"
            ).catch((error) => { sdkPromise = null; throw error; });
            return sdkPromise;
        }
        function renderControls() {
            const busy = workspaceBusy || views.some((view) => view.busy);
            const value = views
                .filter((view) => view.state?.operationId === operationId)
                .map((view) => view.state.value)
                .reduce((latest, current) => !latest || current.sequence > latest.sequence ? current : latest, null);
            el("create-form").querySelector("button").disabled = busy;
            el("start").disabled = busy || !value || value.status !== "pending" || !views[0].joined;
            if (busy || !value) return;
            if (value.status === "pending") activity(views[0].joined ?
                "Workspace ready. Select Start investigation to begin the analysis." :
                "Workspace created. Reconnect the on-call view before starting.");
            else if (value.status === "running") activity(value.sequence ?
                "Investigation running. Each connected view receives live updates independently." :
                "Investigation started. Waiting for the first live update.");
            else if (value.status === "completed") activity("Investigation complete. The findings have been saved.");
            else activity(value.error || "This investigation stopped. Create a new investigation to run again.");
        }
        for (const root of document.querySelectorAll("[data-observer]")) {
            views.push(new InvestigationView(root, api, loadSdk, renderControls));
        }
        async function selectOperation(id) {
            if (!/^[a-f0-9]{32}$/.test(id)) throw new Error("Invalid investigation ID.");
            operationId = id;
            el("selection").hidden = false;
            el("current-id").textContent = id;
            const url = new URL(location.href);
            url.searchParams.set("operation", id);
            history.replaceState(null, "", url);
            await Promise.all(views.map((view) => view.select(id)));
            activity("Connecting both responder views to the investigation...");
            await Promise.all(views.map((view) => view.connect().catch((error) => view.showError(error))));
        }
        async function workspaceAction(handler) {
            if (workspaceBusy || views.some((view) => view.busy)) return;
            workspaceBusy = true;
            el("error").hidden = true;
            for (const view of views) { view.workspaceBusy = true; view.render(); }
            try { await handler(); }
            catch (error) { showError(error); }
            finally {
                workspaceBusy = false;
                el("start").textContent = "Start investigation";
                for (const view of views) { view.workspaceBusy = false; view.render(); }
                renderControls();
            }
        }
        const actions = {
            "create-form": async () => {
                activity("Creating the investigation in Azure Blob Storage...");
                const operation = await api("/api/operations", "POST");
                await selectOperation(operation.operation_id);
            },
            "start-form": async () => {
                if (!operationId) throw new Error("Create an investigation first.");
                el("start").textContent = "Starting...";
                activity("Starting investigation... waiting for the backend to accept the request.");
                const result = await api(`/api/operations/${operationId}/start`, "POST");
                for (const view of views) {
                    if (view === views[0] || view.joined) view.acceptSnapshot(result.operation);
                }
            },
        };
        for (const [id, handler] of Object.entries(actions)) {
            el(id).addEventListener("submit", (event) => {
                event.preventDefault();
                workspaceAction(handler);
            });
        }
        setInterval(() => {
            if (workspaceBusy) return;
            for (const view of views) {
                if (view.state && !terminal.has(view.state.value.status) && !view.intentionalDisconnect && !view.busy) {
                    view.refresh().catch((error) => view.showError(error));
                }
            }
        }, 5000);
        renderControls();
        const initial = new URL(location.href).searchParams.get("operation");
        if (initial) await workspaceAction(() => selectOperation(initial));
    })().catch((error) => {
        document.getElementById("error").textContent = error.message;
        document.getElementById("error").hidden = false;
    });
}
