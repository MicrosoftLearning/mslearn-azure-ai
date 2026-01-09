FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir flask

# Copy application code
COPY app.py .

# Set environment variables
ENV APP_VERSION=1.0.0
ENV MODEL_VERSION=v1

# Expose the application port
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]