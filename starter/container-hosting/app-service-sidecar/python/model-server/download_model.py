from huggingface_hub import snapshot_download

MODEL_REPOSITORY = "microsoft/Phi-3-mini-4k-instruct-onnx"
MODEL_REVISION = "5f5f794c1c23c9d5ee142af85df02a6cc52d6945"
MODEL_VARIANT = "cpu_and_mobile/cpu-int4-rtn-block-32-acc-level-4"

snapshot_download(
    repo_id=MODEL_REPOSITORY,
    revision=MODEL_REVISION,
    local_dir="/download",
    allow_patterns=[
        f"{MODEL_VARIANT}/*",
        "LICENSE",
    ],
)
