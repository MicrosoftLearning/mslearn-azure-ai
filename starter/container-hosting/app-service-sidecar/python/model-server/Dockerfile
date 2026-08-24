FROM python:3.11-slim AS model-downloader

RUN pip install --no-cache-dir huggingface-hub==0.34.4
COPY download_model.py /download_model.py
RUN python /download_model.py

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY --from=model-downloader \
    /download/cpu_and_mobile/cpu-int4-rtn-block-32-acc-level-4 \
    /opt/model/phi3
COPY --from=model-downloader /download/LICENSE /licenses/Phi-3-LICENSE

EXPOSE 11434

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "11434", "--workers", "1"]
