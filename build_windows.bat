@echo off
chcp 65001 >nul
echo ===== Building FinancialStatements.exe =====
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller==6.16.0
python -m PyInstaller --noconfirm --clean --windowed --name FinancialStatements ^
  --add-data "sample;sample" main.py
echo.
echo Done. The program is in: dist\FinancialStatements\FinancialStatements.exe
pause
