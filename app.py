import subprocess
import os
from flask import Flask

# Force Python to print logs instantly instead of holding them in a hidden buffer
os.environ["PYTHONUNBUFFERED"] = "1"

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ JARVIS Intelligence System is Online and Running 24/7!"

@app.route('/ping')
def ping():
    return "pong"

if __name__ == "__main__":
    print("[CLOUD] Starting JARVIS Bot...")
    
    # The "-u" flag explicitly unbuffers standard output for real-time logs
    subprocess.Popen(["python", "-u", "scheduler.py"])
    
    # Start the web server in the foreground
    print("[CLOUD] Starting Web Server on port 7860...")
    app.run(host="0.0.0.0", port=7860)