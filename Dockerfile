# Use official Python 3.10 image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Install system dependencies (ffmpeg is required for edge-tts audio generation)
RUN apt-get update && apt-get install -y ffmpeg curl && rm -rf /var/lib/apt/lists/*

# Copy your files into the cloud container
COPY . /app

# Install Python requirements
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary data directories so storage.py doesn't crash
RUN mkdir -p data/processed data/daily data/archive data/audio

# Expose the Hugging Face web port
EXPOSE 7860

# Run the app
CMD ["python", "app.py"]