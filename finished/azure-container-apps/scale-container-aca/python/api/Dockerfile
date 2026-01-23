FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Health endpoint port for Container Apps probes
ENV HEALTH_PORT=8080
EXPOSE 8080

CMD ["python", "main.py"]
