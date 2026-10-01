#!/usr/bin/env bash
# ============================================================
#  Anonim Ajan - Linux paketleme (tek calistirilabilir dosya)
#  Bu script'i anonim_agent.py ile AYNI klasore koy.
#  Kullanim:  chmod +x build_linux.sh && ./build_linux.sh
#  Farkli bir Python icin:  PYTHON=python3.12 ./build_linux.sh
# ============================================================
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
echo "Calisma klasoru: $(pwd)   Python: $($PY --version 2>&1)"

if [ ! -f "anonim_agent.py" ]; then
  echo "HATA: anonim_agent.py bu klasorde yok."
  exit 1
fi

echo "[1/4] Sistem bagimliliklari kontrol ediliyor..."
MISSING=""
$PY -c "import tkinter" 2>/dev/null || MISSING="$MISSING python3-tk"
$PY -m venv --help >/dev/null 2>&1 || MISSING="$MISSING python3-venv"
command -v xclip >/dev/null 2>&1 || command -v xsel >/dev/null 2>&1 || MISSING="$MISSING xclip"
if [ -n "$MISSING" ]; then
  echo "  Eksik:$MISSING"
  if command -v apt >/dev/null 2>&1; then
    echo "  Kur:  sudo apt install -y$MISSING libnotify-bin gir1.2-appindicator3-0.1"
  elif command -v dnf >/dev/null 2>&1; then
    echo "  Kur:  sudo dnf install -y python3-tkinter xclip libnotify libappindicator-gtk3"
  fi
  exit 1
fi
echo "  Tamam. (Wayland'da global kisayollar calismayabilir; X11 onerilir.)"

echo "[2/4] Sanal ortam ve Python paketleri (.venv)..."
# Guncel Ubuntu/Debian sistem Python'una pip ile kurulum yapilmasina izin vermez;
# bu yuzden her sey proje klasorundeki .venv icine kurulur.
[ -d .venv ] || $PY -m venv .venv
. .venv/bin/activate
python -m pip install --quiet --upgrade pip
if [ -f "requirements.txt" ]; then
  python -m pip install --quiet -r requirements.txt pyinstaller
else
  python -m pip install --quiet customtkinter pyperclip pynput pystray Pillow pyinstaller
fi

echo "[3/4] Tek dosya olusturuluyor..."
# pynput / pystray arka uclari calisma aninda yuklenir; PyInstaller goremedigi icin acikca ekliyoruz.
# Xlib: klavye kisayollari ve "ayni metni tekrar kopyala" algilamasi (XFixes) icin gerekli.
# --collect-data customtkinter: arayuz tema dosyalari; olmadan uygulama acilmaz.
python -m PyInstaller --noconfirm --onefile --name anonim-ajan \
  --collect-data customtkinter \
  --hidden-import darkdetect \
  --hidden-import PIL._tkinter_finder \
  --hidden-import pynput.keyboard._xorg \
  --hidden-import pynput.mouse._xorg \
  --hidden-import pystray._xorg \
  --hidden-import pystray._appindicator \
  --hidden-import pystray._gtk \
  --collect-submodules Xlib \
  anonim_agent.py

# Masaustu kisayolu (.desktop) icin simge
python anonim_agent.py --export-icon dist/anonim-ajan.png >/dev/null

echo "[4/4] TAMAM."
echo "Uygulama:  $(pwd)/dist/anonim-ajan"
echo "Simge:     $(pwd)/dist/anonim-ajan.png"
echo "Calistir:  ./dist/anonim-ajan"
echo "Menuye eklemek ve acilista baslatmak icin README'deki 'Linux'ta menuye ekleme' adimlarina bak."
echo "Not: Bu dosya ayni mimarideki (x86_64) Linux'larda Python olmadan calisir."
