# Windows PowerShell:  .\setup.ps1
# (if scripts are blocked: Set-ExecutionPolicy -Scope Process Bypass)
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python run_smoke_test.py
Write-Host "`nSetup complete. Start the app with:"
Write-Host "  .\venv\Scripts\Activate.ps1"
Write-Host "  streamlit run app.py"
