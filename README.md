# Anonim Ajan

Log ve config çıktılarını ChatGPT, Claude gibi AI araçlarına göndermeden önce
**IP, DNS, hostname, kullanıcı, konteyner, ağ arayüzü, config değerlerini ve
parolaları** türünü
söyleyen etiketlerle maskeleyen, AI'ın cevabını da **gerçek değerlere geri
çeviren** masaüstü aracı.

Her şey bilgisayarında çalışır. Hiçbir ağ bağlantısı yoktur, veri dışarı çıkmaz.

![Anonim Ajan](ekran.png)

```
Gerçek :  kemal@web01:~/projects/ithub$ docker logs ithub-web-1
          DATABASE_URL=postgresql://appuser:Gizli42@db01.sirket.com.tr:5432/appdb
          inet 10.10.10.20/24 brd 10.10.10.255 scope global ens192

Maskeli:  USER_1@HOST_1:~/projects/PROJE_1$ docker logs PROJE_1-web-1
          DATABASE_URL=postgresql://USER_2:PAROLA_1@HOST_2.DOMAIN_1:5432/DB_1
          inet IP_PRIV_1/24 brd IP_PRIV_2 scope global ens192
```

Aynı gerçek değer her yerde aynı etikete gider; aynı alan adının sunucuları
aynı `DOMAIN_n`'i paylaşır. AI neyin gizlendiğini ve değerler arasındaki
ilişkiyi görür, cevabında da aynı etiketleri kullanır. Cevabı kopyaladığında
etiketler gerçek değerlere döner.

### Etiketler

| Etiket | Ne gizlenir | Örnek |
|---|---|---|
| `IP_PRIV_n`, `IP_PUB_n` | Özel (RFC1918, CGNAT, link-local) ve genel IPv4; `/prefix` korunur | `10.10.10.0/24` → `IP_PRIV_1/24` |
| `IPV6_PRIV_n`, `IPV6_PUB_n` | IPv6 adresleri (ULA ve link-local özel sayılır) | `fe80::250:56ff:fea1:b2c3/64` → `IPV6_PRIV_1/64` |
| `HOST_n`, `DOMAIN_n` | Sunucu adları ve alan adları | `app01.sirket.com.tr` → `HOST_1.DOMAIN_1` |
| `USER_n` | Kullanıcı adları | `kemal@web01:~$` → `USER_1@HOST_1:~$` |
| `PROJE_n`, `CONTAINER_n` | Proje ve konteyner adları | `ithub-web-1` → `PROJE_1-web-1`, `nostalgic_hopper` → `CONTAINER_1` |
| `IFACE_n` | Standart olmayan ağ arayüzleri | `br-3f2a1b4c5d6e` → `IFACE_1` |
| `MAIL_n` | E-posta adresleri | `admin@sirket.com.tr` → `MAIL_1` |
| `MAC_n` | MAC adresleri | `00:1B:44:11:3A:B7` → `MAC_1` |
| `DS_n`, `JNDI_n`, `DB_n`, `SCHEMA_n`, `AYAR_n` | Datasource, JNDI, veritabanı, şema ve diğer config değerleri | `datasource jboss` → `datasource DS_1` |
| `PAROLA_n`, `TOKEN_n`, `ANAHTAR_n` | Parolalar, token'lar, özel anahtarlar | `şifre: Ankara06` → `şifre: PAROLA_1` |
| `TARIH_n` | Tarihler (isteğe bağlı) | `01.10.2026` → `TARIH_1` |
| `OZEL_n` | Özel terimler alanına yazdıkların | `ACME A.Ş.` → `OZEL_1` |

Etiketler bilerek `<url1>` gibi köşeli parantez içinde değil: ChatGPT ve
Claude cevapları HTML olarak gösterdiği için `<...>` ekranda kaybolabilir,
XML config içinde de etiket gibi görünür. `IP_1` biçimi Markdown, XML, JSON
ve kabukta bozulmadan kalır.

## Dosyalar

| Dosya | Ne işe yarar |
|---|---|
| `anonim_agent.py` | Masaüstü uygulaması (pano yakalama, kısayollar, tepsi ikonu) |
| `anonimlestirici.html` | Tarayıcı sürümü: kurulum gerektirmez, çift tıkla aç |
| `requirements.txt` | Python paketleri |
| `build_windows.bat` | Windows için tek dosya `.exe` üretir |
| `build_linux.sh` | Linux için tek dosya çalıştırılabilir üretir |
| `ekran.png` | README'deki ekran görüntüsü |
| `tests/` | Regresyon testleri: örnek çıktılar, beklenen maskeli halleri, web sürümü için parite testi |

## Hızlı başlangıç

**Windows / macOS**
```bash
pip install -r requirements.txt
python anonim_agent.py
```

**Linux** (güncel Ubuntu/Debian sistem Python'una `pip install` yapılmasına
izin vermez, bu yüzden sanal ortam kullanılır)
```bash
sudo apt install python3-tk python3-venv xclip     # Fedora: sudo dnf install python3-tkinter xclip
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python anonim_agent.py
```

Python kurmadan kullanmak istersen [Paketleme](#paketleme) bölümüne bak.

## Kullanım

### Otomatik: kopyala, yapıştır

Uygulama açılınca pano erişimi varsa **Oto-izle** anahtarı kendiliğinden açılır.
Üstteki durum kartı korumanın açık olup olmadığını ve son işlemi gösterir.

1. Logu kopyala (`Ctrl+C`). Panodaki metin anında maskelenir.
2. AI'a yapıştır (`Ctrl+V`). Giden metin zaten maskelidir.
3. AI'ın cevabını kopyala (`Ctrl+C`). Etiketler gerçek değerlere geri çevrilir.
4. Editörüne veya terminaline yapıştır (`Ctrl+V`).

Uygulama kopyaladığın metnin log mu AI cevabı mı olduğuna içeriğe bakarak karar
verir. Metinde defterdeki etiketler baskınsa geri çevirir, yeni hassas değer
varsa maskeler. Emin olamazsa hep maskeler, böylece gerçek veri yanlışlıkla
AI'a gitmez.

Aynı maskeli metni tekrar kopyalamak da geri çevirmeyi tetikler.

Çıktı kutularında maskelenen değerler yeşil, geri çevrilen gerçek değerler
kırmızı tonla vurgulanır; neyin değiştiğini bir bakışta görürsün.

Sağ üstteki **Yön** seçicisiyle davranışı değiştirebilirsin:
- `Akıllı` (varsayılan): log maskelenir, AI cevabı geri çevrilir.
- `Sadece maskele`: her kopya maskelenir. Geri çevirmeyi elle yaparsın.

### Elle: sekmeler

- **Anonimleştir:** logu yapıştır, kategorileri seç, *Anonimleştir* (veya `Ctrl+Enter`), *Kopyala*.
- **Geri Çevir:** AI cevabını yapıştır, *Geri çevir* (veya `Ctrl+Enter`), *Kopyala*.
- **Defter:** gerçek ↔ etiket tablosu, en yeni kayıt üstte. Arama, dışa/içe
  aktarma ve sıfırlama buradan. Parolalar burada `••••••••` olarak görünür.

Kategoriler iki satırda, tek tıkla açılıp kapanır: **Ağ** (IPv4, IPv6, DNS,
Host, MAC, Iface) ve **Kimlik ve gizli** (User, E-posta, Docker, Config,
Parola, Tarih, Özel). Tarih dışındakiler varsayılan olarak açıktır. Fazla
maskeleyen bir kategori olursa kapatabilirsin.
**Özel terimler** alanına firma adı gibi otomatik yakalanmayan kelimeleri
virgülle ekleyebilirsin.

### Kısayollar

| Kısayol | İşlev |
|---|---|
| `Ctrl+Alt+A` | Panodaki metni anonimleştir |
| `Ctrl+Alt+R` | Panodaki metni geri çevir |
| `Ctrl+Alt+T` | Oto-izlemeyi aç/kapat |
| `Ctrl+Enter` | Kutudaki metni işle (pencere içinde) |
| `Ctrl+Q` | Uygulamadan çık (pencere içinde) |

`Ctrl+Alt` kısayolları her uygulamada çalışır ve `pynput` paketini gerektirir.
Pencereyi kapatınca uygulama kapanmaz: Windows'ta sistem tepsisine iner,
Linux'ta görev çubuğuna küçülür; izleme sürer.

## Neler maskelenir, neler maskelenmez

**Maskelenir:** IPv4/IPv6 (`ada_192.168.22.22` gibi metne gömülü olanlar dahil),
alan adları (`.com.tr` gibi iki seviyeli uzantılar doğru ayrılır), e-posta,
MAC, `server01` / `db-prod-01` gibi sunucu adları, `datasource jboss` /
`jndi-name="java:/AppDS"` / `DB_NAME=appdb` gibi config değerleri.

**Bağlamdan tanınanlar.** Aşağıdaki yapılar bir değerin ne olduğunu kesin
söylediği için önce bunlara bakılır; rakam içermeyen adlar da yakalanır:

| Bağlam | Ne çıkarılır |
|---|---|
| Shell prompt: `user@host:~/dizin$`, `[user@host dizin]$`, `PS C:\Users\…>` | kullanıcı → `USER`, sunucu → `HOST`, proje dizini → `PROJE` |
| `ip a`, `ifconfig`, `ip route`, `dev …`, `master …` | standart olmayan arayüz → `IFACE` |
| `docker ps` tablosu, `--name`, `container_name:`, `docker logs/exec/restart …`, `docker inspect` | konteyner → `PROJE_n-servis-n` ya da `CONTAINER` |
| `com.docker.compose.project`, `COMPOSE_PROJECT_NAME`, `docker compose -p`, `PWD=`, JBoss `Deployed "x.war"`, nginx `upstream x_backend` | proje → `PROJE` |
| `/etc/hosts` satırları, `HOSTNAME=`, journal/syslog sunucu sütunu, `ssh user@host` | sunucu → `HOST` / `DOMAIN` |
| `*_USER`, `*_USERNAME`, `user=`, `--user`, `-u ad` (mysql, psql, sudo, docker exec…), `/home/ad`, `uid=1001(ad)`, sshd ve sudo logları | kullanıcı → `USER` |
| `scheme://kullanıcı:parola@sunucu:port/veritabanı` | her parça ayrı: `USER`, `PAROLA`, `HOST`/`DOMAIN`, `DB` |

Bir kez öğrenilen kullanıcı, proje ve konteyner adları **sonraki mesajlarda
da** aynı etiketi alır; bağlamsız düz bir cümlede geçseler bile. Proje adı
alan adında (`ithub.sirket.com.tr` → `PROJE_1.DOMAIN_1`), imaj yolunda,
compose ağ adında (`PROJE_1_default`) ve nginx log dosyasında da aynı etiketle
görünür.

**Konteyner kuralı:** bütün konteyner adları maskelenir. Compose adlarında
(`proje-servis-n`) yalnızca kullanıcıya özel proje kısmı gizlenir, servis adı
ve sıra numarası AI için korunur: `ithub-web-1` → `PROJE_1-web-1`. Tek istisna,
adı kamusal imajıyla birebir aynı olan konteyner: `ghcr.io/open-webui/open-webui`
imajından çalışan `open-webui` açıkta kalır, çünkü imaj sütunu bu adı zaten
gösteriyor ve kullanıcıya özel bir bilgi taşımıyor.

**İmajlar:** `docker ps` ve `docker images` çıktısındaki yerel imajlar
(`it-system-management-hub`, `dockotp-totp-panel` gibi, registry'siz ve Docker
Hub resmi imajı olmayanlar) proje adı sayılır ve `PROJE_n` olur. Compose ile
oluşturulmuş `proje-servis` imajlarında yalnızca proje kısmı gizlenir:
`vm-inventory-app` → `PROJE_2-app`. `postgres:16-alpine`, `redis:7` gibi resmi
imajlara ve `ghcr.io`, `quay.io` gibi kamusal registry'lerdeki imajlara dokunulmaz.

**Eski defter:** önceki sürümlerden kalan etiketler (`IP_5`, `HOST_10`,
`KULLANICI_1`) bağlam daha kesin bir tür bulduğunda kendiliğinden yeni
biçime geçer (`IP_PRIV_3`, `IFACE_1`, `USER_1`). Eski etiketler defterde
kalır, eski AI cevapları geri çevrilmeye devam eder.

**Sistem hesapları** (`root`, `admin`, `postgres`, `www-data`, `oracle`,
`deploy`…) maskelenmez; hassas değiller ve AI için anlamlılar. Bunları da
gizlemek istersen `anonim_agent.py` içinde `MASK_SYSTEM_USERS = True` yap.

**Parolalar ve anahtarlar:** anahtar adında `password`, `passwd`, `pwd`,
`şifre`, `sifre`, `parola`, `secret`, `token`, `api_key` geçen her değer
(`password=…`, `şifre: …`, `"password": "…"`, `<password>…</password>`,
`spring.datasource.password=…`, `DB_PASSWORD=…`, `--password …`), bağlantı
adresindeki parola (`jdbc:mysql://root:Parola@host`), `Authorization: Bearer …`,
`*_SECRET`, `*_KEY`, `*_TOKEN`, `*_PASS` biçimli ortam değişkenleri, `curl -u
kullanıcı:parola`, JWT, AWS (`AKIA…`), GitHub (`ghp_`, `gho_`, `github_pat_`),
GitLab, Slack, Stripe, Google, Vault anahtarları ve `-----BEGIN … PRIVATE KEY-----`
blokları (başlık satırları görünür kalır, yalnızca gövde gizlenir). Yedek
olarak 20+ karakterlik, büyük/küçük harf ve rakam karışık, rastgele görünen
dizgiler de `TOKEN` olur. Aynı parola metnin başka bir yerinde etiketsiz
geçerse orada da gizlenir.
`${DB_PASS}` gibi değişken atıflarına, `password: null` gibi boş değerlere,
`PASSWORD_MIN_LENGTH`, `TOKEN_URL`, `DB_PASSWORD_FILE` gibi üst bilgi
anahtarlarına ve çalışma dizini olan `PWD=`'ye dokunulmaz.

**Tarihler:** `2026-10-01`, `01.10.2026`, `30/09/2026`, `01/Oct/2026`,
`Oct 1, 2026`, `1 Ekim 2026` her zaman tanınır, böylece asla IP ya da sunucu
adı sanılmaz. Varsayılan olarak maskelenmez, çünkü hata ayıklarken zaman
çizelgesi önemlidir. Tarihleri de gizlemek istersen **TARİH** kategorisini aç.

**Dokunulmaz** (AI'ın logu anlaması için gerekli, hassas değil):
- Java paket ve sınıf adları: `org.jboss.as.controller`, `AbstractPool.java`
- Dosya adları: `server.log`, `standalone.xml`
- Hata kodları: `WFLYCTL0013`, `ORA-00942`, `HHH000412`
- Log gürültüsü: `thread-12`, `pool-3`, `worker-7`, saatler
- Sürümler ve mimariler: `java17`, `rhel8`, `jboss-eap-7.4.12`, `java-17-openjdk-amd64`, `TLSv1.2`, `x86_64`
- Komut anahtar kelimeleri: `inet`, `inet6`, `link/ether`, `qdisc`, `brd`, `scope`, `ssh2`, `overlay2`
- Standart arayüzler: `lo`, `eth*`, `ens*`, `enp*`, `eno*`, `docker0`, `veth*`, `virbr*`, `wg*`, `bond*`
- Özel adresler: `127.0.0.0/8`, `0.0.0.0`, `::1`, `::`, çok yayın, `255.255.255.0` gibi maskeler,
  `10.0.0.0/8` gibi genel ağ blokları, `00:00:00:00:00:00`, `ff:ff:ff:ff:ff:ff`,
  `/etc/hosts`'taki `localhost`, `ip6-localhost`, `ip6-allnodes`…
- Kamusal alan adları ve registry'ler: `docker.io`, `ghcr.io`, `quay.io`, `gcr.io`,
  `registry.k8s.io`, `github.com`, `redhat.com`, `docs.oracle.com`
- Konteyner ID'leri, `sha256` özetleri ve git commit'leri (onaltılık kimlikler)

## Testler

`tests/fixtures/` klasöründe gerçekçi örnekler var: `ip a`, `docker ps`,
`docker images`, `.env`, `/etc/hosts`, `env`, `docker inspect`, nginx config, `journalctl`,
prompt ve bağlantı dizgileri, JBoss logu. `tests/expected/` klasöründe her
birinin beklenen maskeli hali duruyor.

```bash
python tests/test_masking.py            # çalıştır
python tests/test_masking.py --update   # beklenen çıktıları yeniden üret
```

Her örnek için şunlara bakılır: çıktı beklenenle birebir aynı mı, Windows
satır sonlarıyla (`\r\n`) da aynı sonucu veriyor mu, gerçek
değerlerin hiçbiri sızıyor mu, korunması gerekenler (`ens192`, `::1`,
`ghcr.io`…) yerinde mi, geri çevirince orijinal metin dönüyor mu, maskeli
metni tekrar maskelemek bir şey değiştiriyor mu. Ayrıca aynı adın farklı
mesajlarda aynı etiketi aldığı ve AI cevabının doğru geri çevrildiği test
edilir. Arayüz paketleri gerekmez; `pytest tests/` ile de çalışır.

Tarayıcı sürümü de aynı beklenen çıktılarla test edilir:
`tests/test_web_engine.js`, `anonimlestirici.html` içindeki motoru
(`ENGINE START` / `ENGINE END` arası) çıkarıp aynı kontrolleri yapar. Node
kuruluysa `python tests/test_masking.py` bunu da otomatik çalıştırır; tek
başına çalıştırmak için:

```bash
node tests/test_web_engine.js
```

Motorda bir kuralı değiştirirsen ikisini de güncelle: Python'u değiştirip
HTML'i unutursan web testi kırılır.

Motoru değiştirdikten sonra testleri çalıştır. Bir fark çıkarsa önce farkı
incele; `--update`'i ancak yeni çıktının doğru olduğundan eminsen kullan.

## Paketleme

PyInstaller çapraz derleme yapmaz. Windows `.exe` dosyasını Windows'ta, Linux
dosyasını Linux'ta üretmen gerekir.

**Windows:** `build_windows.bat` dosyasını `anonim_agent.py` ile aynı klasöre
koyup çift tıkla. Sonuç `dist\AnonimAjan.exe` olur ve Python kurulu olmayan
makinelerde de çalışır. Uygulama simgesi exe'ye gömülür. Gezgin hâlâ eski
simgeyi gösterirse exe'yi başka bir klasöre kopyala; Windows simge önbelleğini
geç yeniler. Açılışta başlasın istersen kısayolunu `Win+R → shell:startup`
klasörüne koy.

**Linux:**
```bash
chmod +x build_linux.sh && ./build_linux.sh
```
Script eksik sistem paketlerini kontrol eder, eksik varsa kurulum komutunu
yazar. Python paketlerini proje klasöründeki `.venv` içine kurar, sisteme
dokunmaz. Sonuç `dist/anonim-ajan` olur; aynı mimarideki Linux'larda Python
olmadan çalışır. Farklı bir Python ile derlemek için:
`PYTHON=python3.12 ./build_linux.sh`

Masaüstünde derle (ekransız bir sunucuda değil): kısayol modülleri derleme
sırasında ekran bağlantısı arar.

**Linux'ta menüye ekleme ve açılışta başlatma** (build sonrası, aynı klasörde):
```bash
mkdir -p ~/.local/bin ~/.local/share/applications ~/.local/share/icons ~/.config/autostart
cp dist/anonim-ajan ~/.local/bin/
cp dist/anonim-ajan.png ~/.local/share/icons/
cat > ~/.local/share/applications/anonim-ajan.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Anonim Ajan
Comment=Log ve config anonimleştirici
Exec=$HOME/.local/bin/anonim-ajan
Icon=$HOME/.local/share/icons/anonim-ajan.png
Terminal=false
Categories=Utility;
EOF
cp ~/.local/share/applications/anonim-ajan.desktop ~/.config/autostart/
```
Açılışta başlamasın istersen `~/.config/autostart/anonim-ajan.desktop` dosyasını sil.

## Platform notları

- **Windows:** tüm özellikler çalışır.
- **Linux (X11 — Xorg oturumu):** tüm özellikler çalışır; aynı metni tekrar
  kopyalamak da algılanır. Pano için `xclip` veya `xsel` gerekir.
- **Linux (Wayland — güncel Ubuntu/Fedora varsayılanı):** kutular çalışır, pano
  yakalama genellikle çalışır (sorun olursa `sudo apt install wl-clipboard`).
  Global kısayollar ve aynı metni tekrar kopyalama algılaması çalışmayabilir. Hepsini istiyorsan giriş ekranında ⚙ simgesinden
  "Ubuntu on Xorg" / "GNOME on Xorg" oturumunu seç. Oturum türünü görmek için:
  `echo $XDG_SESSION_TYPE`
- **Linux tepsi ikonu:** KDE, XFCE, Cinnamon ve Ubuntu'nun GNOME'unda çıkar.
  Tepsi alanı olmayan masaüstlerinde (ör. Fedora'nın düz GNOME'u) çıkmaz.
  Bu yüzden Linux'ta pencereyi kapatmak uygulamayı kapatmaz, görev çubuğuna
  küçültür; izleme sürer. Tamamen çıkmak için pencerede `Ctrl+Q`.
- **macOS:** kısayol ve pano için Sistem Ayarları → Gizlilik ve Güvenlik →
  Erişilebilirlik ve Girdi İzleme izni gerekir. Aynı metni ikinci kez
  kopyalamayı algılamak için `pip install pyobjc-framework-Cocoa` kurulu olmalı.
  Tepsi ikonu sınırlı çalışabilir.

## Tarayıcı sürümü

`anonimlestirici.html` kurulum gerektirmez ve tamamen tarayıcıda çalışır.
Masaüstü sürümle **aynı motoru** kullanır: aynı girdiye aynı etiketleri verir
(`IP_PRIV_1`, `HOST_1`, `PROJE_1-web-1`…), parola ve tarih tanıma, bağlam
kuralları ve beyaz liste aynıdır. Farkları:

- Pano yakalama ve kısayol yoktur: metni yapıştırıp butonlarla çalışırsın
  (`Ctrl+Enter` ile anonimleştir / geri çevir).
- Defter varsayılan olarak yalnızca açık sekmede durur. "Bu tarayıcıda
  hatırla" işaretlenirse tarayıcının yerel deposuna kaydedilir (parolalar
  hariç); işaret kaldırılınca kayıt silinir.
- Sol kutuya etiketli bir AI cevabı yapıştırırsan uyarır ve tek tıkla geri
  çevir alanına taşır.
- Masaüstünün defteri (`~/.anonim_ajan.json`) ve dışa aktarılan defterler
  içe aktarılabilir; iki sürüm arasında geçiş yapabilirsin.

## Veri ve gizlilik

- Eşleştirme defteri `~/.anonim_ajan.json` dosyasında durur. Bilgisayarı
  kapatıp açsan bile geri çevirme çalışır.
- **Parolalar, token'lar ve anahtarlar diske hiç yazılmaz**, dışa aktarılan
  deftere de girmez; yalnızca uygulama açıkken bellekte tutulur. Uygulamayı
  kapatıp açtıktan sonra `PAROLA_1` gibi etiketler geri çevrilmez, olduğu gibi
  kalır.
- **Bu dosya ve dışa aktarılan defterler gerçek IP, hostname ve e-postaları
  düz metin olarak içerir.** Kimseyle paylaşma, depoya ekleme. `.gitignore`
  bunları zaten dışlıyor.
- AI'a göndermeden önce Defter sekmesine bir göz at. Tespit sezgiseldir ve
  %100 garanti vermez.

## Sorun giderme

- **Uygulama açılmıyor:** açılışta bir hata olursa ekranda uyarı çıkar ve
  ayrıntılar ev klasöründeki `anonim_ajan_hata.log` dosyasına yazılır. O
  dosyanın içeriğini paylaşırsan sorun hızlıca bulunur.
- **Kısayollar çalışmıyor:** durum satırında "Kısayol: ✗" yazıyorsa
  `pip install pynput` gerekir. Kısayol olmadan da OTO-İZLE düğmesi çalışır.
- **"Pano: ✗":** `pip install pyperclip`. Linux'ta ayrıca `sudo apt install xclip`.
- **Kopyalayınca bir şey olmuyor:** OTO-İZLE düğmesi yeşil (AÇIK) olmalı ve
  metinde maskelenecek bir değer bulunmalı.
- **Eski sürümden güncelledin:** eski sürümün gerçekçi sahte değerleri
  (`relay66z.serdivan.systems` gibi) hâlâ geri çevrilir. Açılışta "eski
  biçimde kayıt" uyarısı çıkarsa yeni etiketlere geçmek için Defter sekmesinden
  bir kez **Sıfırla**.
- **Python 3.14:** bazı paketlerin bu sürüm için hazır kurulumu henüz yoksa
  Python 3.12 veya 3.13 kullan.
