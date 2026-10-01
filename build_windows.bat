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
  python -m pip install customtkinter pyperclip pynput pystray Pillow pyinstaller
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
echo [2/3] Simge ve EXE olusturuluyor (konsolsuz, tek dosya)...
python anonim_agent.py --export-icon anonim_ajan.ico
if errorlevel 1 (
  echo HATA: simge olusturulamadi.
  pause
  exit /b 1
)
REM --icon: exe'nin Gezgin / masaustu simgesi (varsayilan Python simgesi yerine)
REM --collect-data customtkinter: arayuz tema dosyalari; olmadan exe acilmaz
REM pynput / pystray arka uclari calisma aninda yuklenir; PyInstaller goremedigi icin acikca ekliyoruz.
python -m PyInstaller --noconfirm --noconsole --onefile --name AnonimAjan ^
  --icon anonim_ajan.ico ^
  --collect-data customtkinter ^
  --hidden-import darkdetect ^
  --hidden-import PIL._tkinter_finder ^
  --hidden-import pynput.keyboard._win32 ^
  --hidden-import pynput.mouse._win32 ^
  --hidden-import pystray._win32 ^
  anonim_agent.py
if errorlevel 1 (
  echo HATA: PyInstaller basarisiz.
  pause
  exit /b 1
)

echo.
echo [3/3] TAMAM.
echo Uygulama:  "%cd%\dist\AnonimAjan.exe"
echo Bu .exe Python KURULU OLMAYAN Windows makinelerde de calisir.
echo Not: Gezgin eski simgeyi gosterirse dosyayi baska klasore kopyala; Windows simge onbellegi gec yenilenir.
echo Baslangicta acilsin istersen kisayolunu  Win+R -^> shell:startup  klasorune koy.
echo.
pause
