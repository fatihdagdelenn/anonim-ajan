@echo off
REM ============================================================
REM  Anonim Ajan - Windows paketleme (tek .exe uretir)
REM  Bu .bat dosyasini anonim_agent.py ile AYNI klasore koy,
REM  sonra cift tikla. Python 3.9-3.13 onerilir.
REM ============================================================
setlocal
cd /d "%~dp0"

echo Calisma klasoru: %cd%
echo.

if not exist "anonim_agent.py" (
  echo HATA: "anonim_agent.py" bu klasorde yok.
  echo Bu .bat dosyasini anonim_agent.py ile AYNI klasore koyup tekrar calistir.
  echo.
  pause
  exit /b 1
)

echo [1/3] Gerekli paketler kuruluyor...
python -m pip install --upgrade pip
if exist "requirements.txt" (
  python -m pip install -r requirements.txt pyinstaller
) else (
  python -m pip install pyperclip pynput pystray Pillow pyinstaller
)
if errorlevel 1 (
  echo.
  echo HATA: paket kurulumu basarisiz.
  echo   - Python kurulu mu? "python --version" ile bak.
  echo   - Python 3.14 cok yeni olabilir; pystray/Pillow tekerlekleri henuz cikmadiysa
  echo     Python 3.12 veya 3.13 kurup tekrar dene.
  echo.
  pause
  exit /b 1
)

echo.
echo [2/3] EXE olusturuluyor (konsolsuz, tek dosya)...
pyinstaller --noconsole --onefile --name AnonimAjan anonim_agent.py
if errorlevel 1 (
  echo HATA: PyInstaller basarisiz.
  pause
  exit /b 1
)

echo.
echo [3/3] TAMAM.
echo Uygulama:  "%cd%\dist\AnonimAjan.exe"
echo Bu .exe Python KURULU OLMAYAN Windows makinelerde de calisir.
echo Baslangicta acilsin istersen kisayolunu  Win+R -^> shell:startup  klasorune koy.
echo.
pause
