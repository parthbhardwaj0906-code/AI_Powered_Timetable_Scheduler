#!/usr/bin/env bash
# Linux / macOS / WSL / Git-Bash:  bash setup.sh
set -e
python3 -m venv venv
source venv/bin/activate 2>/dev/null || source venv/Scripts/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python run_smoke_test.py
echo
echo "Setup complete. Start the app with:"
echo "  source venv/bin/activate   (Git-Bash: source venv/Scripts/activate)"
echo "  streamlit run app.py"
