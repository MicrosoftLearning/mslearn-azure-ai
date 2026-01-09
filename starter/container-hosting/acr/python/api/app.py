from flask import Flask, jsonify
import os

app = Flask(__name__)

@app.route('/health')
def health():
    """Health check endpoint for container orchestrators."""
    return jsonify({
        "status": "healthy",
        "version": os.getenv("APP_VERSION", "1.0.0")
    })

@app.route('/predict')
def predict():
    """Simulated inference endpoint."""
    return jsonify({
        "prediction": "sample-result",
        "confidence": 0.95,
        "model_version": os.getenv("MODEL_VERSION", "v1")
    })

@app.route('/')
def root():
    """Root endpoint with API information."""
    return jsonify({
        "name": "Inference API",
        "version": os.getenv("APP_VERSION", "1.0.0"),
        "endpoints": ["/health", "/predict"]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)