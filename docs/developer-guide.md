# Developer Guide

Welcome to the JARVIS Developer Guide. This document provides setup instructions and developer guidelines.

## Local Development Setup

1. Clone the repository and install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Build the frontend distribution bundle:
   ```bash
   cd frontend
   npm install
   npm run build
   cd ..
   ```

3. Launch the application server:
   ```bash
   python app.py
   ```

## Running Diagnostics & Tests

- **Run Automated Tests**:
  ```bash
  python -m pytest -v
  ```

- **Run System Diagnostics**:
  ```bash
  python tools/health_check.py
  ```
