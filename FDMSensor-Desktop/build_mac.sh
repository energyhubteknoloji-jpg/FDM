#!/bin/bash
echo "Masaüstü uygulaması derleniyor (Mac)..."
echo ""

echo "1. Python Bağımlılıkları kontrol ediliyor..."
pip install -r requirements.txt
pip install pyinstaller waitress

echo ""
echo "2. Python Sunucusu Derleniyor..."
pyinstaller --name api_server_mac --onefile --noconsole \
  --add-data "templates:templates" \
  --add-data "static:static" \
  --hidden-import waitress \
  --hidden-import sqlalchemy \
  --hidden-import flask_login \
  --hidden-import flask_wtf \
  --hidden-import openpyxl \
  --hidden-import pandas \
  --hidden-import db_sqlite \
  --hidden-import scraper \
  --hidden-import weather_service \
  --hidden-import simulation_engine \
  --hidden-import jaraco \
  --hidden-import jaraco.text \
  --hidden-import jaraco.functools \
  --hidden-import jaraco.context \
  api_server.py

if [ $? -ne 0 ]; then
  echo "Python derleme hatası!"
  exit 1
fi

echo ""
echo "3. Oluşturulan çalıştırılabilir dosya klasöre kopyalanıyor..."
# --noconsole ile --onefile birlikte kullanıldığında binary doğrudan dist/ altına çıkar
cp dist/api_server_mac ./api_server_mac
chmod +x ./api_server_mac

echo ""
echo "4. Electron Uygulaması Paketleniyor..."
npm run dist

echo ""
echo "İşlem Tamam! Oluşturulan dmg dosyası 'dist' klasöründedir."
