import subprocess
import os
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ JARVIS Intelligence System is Online and Running 24/7 via Free Cloud APIs!"

@app.route('/ping')
def ping():
    return "pong"

if __name__ == "__main__":
    print("[CLOUD] Starting JARVIS Bot...")
    
    # Start the scheduler in the background
    subprocess.Popen(["python", "scheduler.py"])
    
    # Start the web server in the foreground on port 7860 (Hugging Face Default)
    print("[CLOUD] Starting Web Server on port 7860...")
    app.run(host="0.0.0.0", port=7860)