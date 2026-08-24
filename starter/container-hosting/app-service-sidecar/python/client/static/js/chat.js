const MAX_MESSAGES = 8;
const messages = [];

const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const sendButton = document.getElementById("send-button");
const clearButton = document.getElementById("clear-button");
const messagesElement = document.getElementById("messages");
const emptyState = document.getElementById("empty-state");
const errorElement = document.getElementById("error-message");
const characterCount = document.getElementById("character-count");
const modelStatus = document.getElementById("model-status");
const statusText = document.getElementById("status-text");
const modelDetails = document.getElementById("model-details");

let modelReady = false;
let sending = false;

function updateControls() {
    const hasMessage = messageInput.value.trim().length > 0;
    sendButton.disabled = !modelReady || sending || !hasMessage;
    messageInput.disabled = sending;
    clearButton.disabled = sending;
    sendButton.textContent = sending ? "Generating..." : "Send";
    characterCount.textContent = `${messageInput.value.length} / 2000`;
}

function setStatus(state, text) {
    modelStatus.className = `status status-${state}`;
    statusText.textContent = text;
    modelReady = state === "ready";
    updateControls();
}

function showError(message) {
    errorElement.textContent = message;
    errorElement.hidden = false;
}

function clearError() {
    errorElement.textContent = "";
    errorElement.hidden = true;
}

function addMessage(message) {
    emptyState.hidden = true;
    const article = document.createElement("article");
    article.className = `message message-${message.role}`;

    const role = document.createElement("span");
    role.className = "message-role";
    role.textContent = message.role === "user" ? "You" : "Phi-3";

    const content = document.createElement("span");
    content.textContent = message.content;

    article.append(role, content);
    messagesElement.appendChild(article);
    messagesElement.scrollTop = messagesElement.scrollHeight;
    return article;
}

function boundedMessages() {
    const bounded = messages.slice(-MAX_MESSAGES);
    if (bounded[0]?.role === "assistant") {
        bounded.shift();
    }
    return bounded;
}

async function checkModel() {
    setStatus("loading", "Checking model...");
    try {
        const response = await fetch("/health/ready", { cache: "no-store" });
        if (!response.ok) {
            throw new Error("The model is still loading.");
        }
        const infoResponse = await fetch("/model-info", { cache: "no-store" });
        if (infoResponse.ok) {
            const info = await infoResponse.json();
            modelDetails.textContent = `${info.model} - ${info.quantization} - ${info.runtime}`;
        }
        setStatus("ready", "Model ready");
    } catch (error) {
        setStatus("error", "Azure model loading");
        window.setTimeout(checkModel, 10000);
    }
}

chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const content = messageInput.value.trim();
    if (!content || sending || !modelReady) {
        return;
    }

    clearError();
    const userMessage = { role: "user", content };
    messages.push(userMessage);
    const userMessageElement = addMessage(userMessage);
    messageInput.value = "";
    sending = true;
    updateControls();

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ messages: boundedMessages() }),
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || "The chat request failed.");
        }
        messages.push(result.message);
        addMessage(result.message);
        modelDetails.textContent = `${result.model} - ${result.usage.generated_tokens} generated tokens`;
    } catch (error) {
        messages.pop();
        userMessageElement.remove();
        emptyState.hidden = messages.length > 0;
        showError(error.message);
        setStatus("error", "Model unavailable");
        window.setTimeout(checkModel, 10000);
    } finally {
        sending = false;
        updateControls();
        messageInput.focus();
    }
});

messageInput.addEventListener("input", updateControls);
messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        chatForm.requestSubmit();
    }
});

clearButton.addEventListener("click", () => {
    messages.length = 0;
    messagesElement.querySelectorAll(".message").forEach((message) => message.remove());
    emptyState.hidden = false;
    clearError();
    messageInput.focus();
});

updateControls();
checkModel();
