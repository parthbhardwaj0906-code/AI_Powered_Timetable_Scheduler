@echo off
REM Windows CMD:  setup.bat
python -m venv venv
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
python run_smoke_test.py
echo.
echo Setup complete. Start the app with:
echo   venv\Scripts\activate.bat
echo   streamlit run app.py
