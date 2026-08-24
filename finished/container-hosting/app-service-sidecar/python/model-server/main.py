import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import onnxruntime_genai as og
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

MODEL_NAME = os.getenv("MODEL_NAME", "microsoft/Phi-3-mini-4k-instruct-onnx")
MODEL_PATH = os.getenv("MODEL_PATH", "/opt/model/phi3")
MANIFEST_PATH = Path(os.getenv("MODEL_MANIFEST_PATH", "/home/models/manifest.json"))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

model: og.Model | None = None
tokenizer: og.Tokenizer | None = None
generation_lock = threading.Lock()


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class GenerateRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=8)
    max_new_tokens: int = Field(default=128, ge=1, le=128)


def write_manifest(load_seconds: float) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "model": MODEL_NAME,
        "quantization": "CPU INT4",
        "runtime": "Microsoft ONNX Runtime GenAI",
        "status": "ready",
        "load_seconds": round(load_seconds, 2),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


@asynccontextmanager
async def lifespan(_: FastAPI):
    global model, tokenizer

    started = time.monotonic()
    logger.info("Loading model from %s", MODEL_PATH)
    model = og.Model(MODEL_PATH)
    tokenizer = og.Tokenizer(model)
    load_seconds = time.monotonic() - started
    write_manifest(load_seconds)
    logger.info("Model loaded in %.2f seconds", load_seconds)
    yield
    tokenizer = None
    model = None


app = FastAPI(title="Phi-3 Model Server", lifespan=lifespan)


@app.get("/health")
def health():
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model is loading.")
    return {"status": "ready", "model": MODEL_NAME}


@app.post("/generate")
def generate(request: GenerateRequest):
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model is loading.")

    if request.messages[-1].role != "user":
        raise HTTPException(status_code=400, detail="The final message must be from the user.")

    prompt_parts = [
        "<|system|>\n"
        "You are a helpful, concise AI assistant. Answer accurately and say when "
        "you do not know. Keep responses under 120 words.<|end|>\n"
    ]
    for message in request.messages:
        prompt_parts.append(
            f"<|{message.role}|>\n{message.content.strip()}<|end|>\n"
        )
    prompt_parts.append("<|assistant|>\n")
    prompt = "".join(prompt_parts)

    with generation_lock:
        input_tokens = tokenizer.encode(prompt)
        if len(input_tokens) + request.max_new_tokens > 4096:
            raise HTTPException(
                status_code=400,
                detail="The conversation exceeds the model context window.",
            )
        params = og.GeneratorParams(model)
        params.set_search_options(
            max_length=len(input_tokens) + request.max_new_tokens,
            do_sample=False,
        )
        generator = og.Generator(model, params)
        generator.append_tokens(input_tokens)
        stream = tokenizer.create_stream()
        output_parts: list[str] = []
        generated_tokens = 0

        while not generator.is_done():
            generator.generate_next_token()
            token = generator.get_next_tokens()[0]
            output_parts.append(stream.decode(token))
            generated_tokens += 1

        del generator

    text = "".join(output_parts).strip()
    if not text:
        raise HTTPException(status_code=500, detail="The model returned an empty response.")
    return {
        "model": MODEL_NAME,
        "message": {"role": "assistant", "content": text},
        "usage": {
            "prompt_tokens": len(input_tokens),
            "generated_tokens": generated_tokens,
        },
    }
