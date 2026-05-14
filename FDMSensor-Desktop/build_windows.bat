@echo off
echo Masaüstü uygulaması derleniyor (Windows)...
echo.

echo 1. Python Bagimliliklari kontrol ediliyor...
pip install -r requirements.txt
pip install pyinstaller waitress

echo.
echo 2. Python Sunucusu Derleniyor...
pyinstaller --name api_server --onefile --windowed ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --hidden-import waitress ^
  --hidden-import sqlalchemy ^
  --hidden-import flask_login ^
  --hidden-import openpyxl ^
  --hidden-import pandas ^
  --hidden-import db_sqlite ^
  --hidden-import scraper ^
  --hidden-import weather_service ^
  --hidden-import simulation_engine ^
  --hidden-import jaraco ^
  --hidden-import jaraco.text ^
  --hidden-import jaraco.functools ^
  --hidden-import jaraco.context ^
  api_server.py

IF %ERRORLEVEL% NEQ 0 (
  echo Python derleme hatasi!
  exit /b %ERRORLEVEL%
)

echo.
echo 3. Olusturulan exe klasore kopyalaniyor...
copy dist\api_server.exe .

echo.
echo 4. Electron Uygulamasi Paketleniyor...
call npm run dist

echo.
echo Islem Tamam! Olusturulan setup dosyasi "dist" klasorundedir.
pause
