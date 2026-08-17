# Import Flask framework for creating the web API
from flask import Flask, jsonify
# Import os module to read environment variables
import os

# Create the Flask application instance
app = Flask(__name__)


# -----------------------------------------------------------------------------
# Health Check Endpoint
# Used by container orchestrators (like Kubernetes) to verify the app is running
# -----------------------------------------------------------------------------
@app.route('/health')
def health():
    """Health check endpoint for container orchestrators."""
    return jsonify({
        "status": "healthy",
        "version": os.getenv("APP_VERSION", "1.0.0")  # Read version from env var
    })


# -----------------------------------------------------------------------------
# Prediction Endpoint
# Simulates an ML inference endpoint - in production, this would call a model
# -----------------------------------------------------------------------------
@app.route('/predict')
def predict():
    """Simulated inference endpoint."""
    return jsonify({
        "prediction": "sample-result",
        "confidence": 0.95,
        "model_version": os.getenv("MODEL_VERSION", "v1")  # Model version from env var
    })


# -----------------------------------------------------------------------------
# Root Endpoint
# Provides API information and lists available endpoints
# -----------------------------------------------------------------------------
@app.route('/')
def root():
    """Root endpoint with API information."""
    return jsonify({
        "name": "Inference API",
        "version": os.getenv("APP_VERSION", "1.0.0"),
        "endpoints": ["/health", "/predict"]  # Available routes
    })


# -----------------------------------------------------------------------------
# Application Entry Point
# Runs the Flask development server on port 5000, accessible from any IP
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    # host='0.0.0.0' allows connections from outside the container
    # port=5000 is the default Flask port
    app.run(host='0.0.0.0', port=5000)