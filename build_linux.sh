#!/usr/bin/env bash
# ============================================================
#  Anonim Ajan - Linux paketleme (tek calistirilabilir dosya)
#  Bu script'i anonim_agent.py ile AYNI klasore koy.
#  Kullanim:  chmod +x build_linux.sh && ./build_linux.sh
#  Python 3.9+ gerekir.
# ============================================================
set -e
cd "$(dirname "$0")"
echo "Calisma klasoru: $(pwd)"

if [ ! -f "anonim_agent.py" ]; then
  echo "HATA: anonim_agent.py bu klasorde yok."
  echo "Bu script'i anonim_agent.py ile ayni klasore koyup tekrar calistir."
  exit 1
fi

echo "[1/4] Sistem bagimliliklari (pano + tepsi ikonu icin)..."
if command -v apt >/dev/null 2>&1; then
  echo "  Debian/Ubuntu: sudo apt install -y xclip libnotify-bin gir1.2-appindicator3-0.1 python3-tk"
elif command -v dnf >/dev/null 2>&1; then
  echo "  Fedora: sudo dnf install -y xclip libnotify libappindicator-gtk3 python3-tkinter"
fi
echo "  (Wayland'da global kisayollar calismayabilir; X11 onerilir.)"

echo "[2/4] Python paketleri..."
python3 -m pip install --upgrade pip
if [ -f "requirements.txt" ]; then
  python3 -m pip install -r requirements.txt pyinstaller
else
  python3 -m pip install pyperclip pynput pystray Pillow pyinstaller
fi

echo "[3/4] Tek dosya olusturuluyor..."
pyinstaller --onefile --name anonim-ajan anonim_agent.py

echo "[4/4] TAMAM."
echo "Uygulama:  $(pwd)/dist/anonim-ajan"
echo "Calistir:  ./dist/anonim-ajan"
echo "Not: Bu binary ayni mimarideki (x86_64) Linux'larda Python olmadan calisir."
