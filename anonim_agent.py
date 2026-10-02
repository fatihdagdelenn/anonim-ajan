#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anonim Ajan — log/config anonimleştirici (masaüstü).

Log ve config çıktılarındaki IP, DNS, hostname, e-posta, MAC ve config
değerlerini AI'a göndermeden önce IP_1, HOST_1 gibi etiketlerle maskeler; AI'ın
cevabını gerçek değerlere geri çevirir. Her şey yerelde çalışır.

Kullanım:
  • Oto-izle açıkken: log kopyala → panoda maskeli hali olur;
    AI cevabını kopyala → panoda gerçek hali olur.
  • Ya da sekmelerdeki kutulara yapıştırıp butonlarla çalış.

Kısayollar (pynput gerekir):
  Ctrl+Alt+A  panodaki metni anonimleştir
  Ctrl+Alt+R  panodaki metni geri çevir
  Ctrl+Alt+T  oto-izlemeyi aç/kapat

Kurulum:   pip install -r requirements.txt
Çalıştır:  python anonim_agent.py
Simge:     python anonim_agent.py --export-icon anonim_ajan.ico   (veya .png)

macOS: kısayol/pano için Sistem Ayarları > Gizlilik ve Güvenlik > Erişilebilirlik
       + Girdi İzleme izni gerekir. Linux: pano için 'xclip' veya 'xsel' gerekir.
"""

import json, os, re, sys, threading, time

try:
    import pyperclip
except ImportError:
    pyperclip = None
try:
    from pynput import keyboard
except Exception:
    keyboard = None
def _import_pystray():
    try:
        import pystray
        from PIL import Image, ImageDraw
        return pystray, Image, ImageDraw
    except Exception:
        pass
    # Linux: GTK/AppIndicator yoksa saf X11 arka ucunu dene (XFCE, i3, minimal kurulumlar)
    if sys.platform.startswith("linux") and os.environ.get("DISPLAY"):
        for m in [k for k in sys.modules if k == "pystray" or k.startswith("pystray.")]:
            del sys.modules[m]
        os.environ["PYSTRAY_BACKEND"] = "xorg"
        try:
            import pystray
            from PIL import Image, ImageDraw
            return pystray, Image, ImageDraw
        except Exception:
            pass
    return None, None, None
pystray, Image, ImageDraw = _import_pystray()

STORE = os.path.join(os.path.expanduser("~"), ".anonim_ajan.json")

# =====================================================================
#  ÇEKİRDEK ANONİMLEŞTİRME MANTIĞI
# =====================================================================
#
#  Hassas değerler türünü söyleyen numaralı etiketlerle değiştirilir:
#     10.10.10.20               → IP_PRIV_1       (RFC1918; genel adres → IP_PUB_n)
#     10.10.10.0/24             → IP_PRIV_2/24    (/prefix korunur)
#     app01.sirket.com.tr       → HOST_1.DOMAIN_1 (aynı alan adı → aynı DOMAIN_n)
#     kemal@web01:~/ithub$      → USER_1@HOST_2:~/PROJE_1$
#     ithub-web-1 (konteyner)   → PROJE_1-web-1   (compose adı: proje kısmı gizlenir)
#     br-3f2a1b4c5d6e           → IFACE_1         (eth0, ens192, docker0, veth… dokunulmaz)
#     password=Gizli123         → password=PAROLA_1   (diske yazılmaz)
#
#  Etiketler bilerek <...> içinde DEĞİL: AI arayüzleri <url1> gibi şeyleri HTML
#  sanıp yutabiliyor, XML config içinde de etiket gibi görünüyor.
#
#  Tespit sırası: önce BAĞLAM (prompt, ip a, docker ps, /etc/hosts, journal,
#  bağlantı dizgisi…) — bu yapılar bir değerin ne olduğunu kesin söyler. Sonra
#  genel kalıplar (IP, alan adı, rakam içeren sunucu adı…). Bir kez öğrenilen
#  kullanıcı / proje / konteyner adları sonraki mesajlarda da aynı etiketi alır.

import ipaddress

# Sistem / servis hesapları maskelenmez (AI için anlamlı, hassas değil).
# Bunları da gizlemek istersen True yap.
MASK_SYSTEM_USERS = False
SYSTEM_USERS = set("""root admin administrator sa sys system postgres mysql mariadb oracle redis
    mongodb www-data nginx apache httpd nobody daemon bin sync games man lp mail news uucp proxy
    backup list irc gnats systemd-network systemd-resolve systemd-timesync messagebus syslog sshd
    ubuntu debian centos ec2-user fedora pi vagrant jboss wildfly tomcat jenkins gitlab-runner git
    docker sudo wheel users staff adm deploy ansible guest test user operator elasticsearch kibana
    grafana prometheus rabbitmq zookeeper kafka hdfs yarn hive spark nagios zabbix""".split())

# Etiket önekleri. Eskiler (KULLANICI, IP, IPV6) geriye dönük geri çevirme için listede.
TOKEN_PREFIXES = ["IPV6_PRIV", "IPV6_PUB", "KULLANICI", "CONTAINER", "IP_PRIV", "IP_PUB", "ANAHTAR",
                  "PAROLA", "DOMAIN", "SCHEMA", "TARIH", "TOKEN", "IFACE", "PROJE", "IPV6", "HOST",
                  "MAIL", "JNDI", "AYAR", "OZEL", "USER", "MAC", "IP", "DS", "DB"]
# Önünde harf/rakam olmasın (MYDB_1 etiket değil); arkasında rakam olmasın (IP_1 ≠ IP_10).
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])(?:%s)_\d+(?!\d)" %
                      "|".join(sorted(TOKEN_PREFIXES, key=len, reverse=True)))
def is_token(s): return bool(TOKEN_RE.fullmatch(s or ""))

TYPE_PREFIX = {"mac": "MAC", "hostname": "HOST", "domain": "DOMAIN", "email": "MAIL", "date": "TARIH",
               "custom": "OZEL", "user": "USER", "container": "CONTAINER", "project": "PROJE",
               "iface": "IFACE"}

# Çakışmada büyük olan kazanır (aynı başlangıçta).
PRIO = {"secret": 7, "custom": 6, "email": 5, "container": 4.8, "project": 4.7, "iface": 4.6,
        "user": 4.5, "domain": 4, "date": 3.5, "ipv6": 3, "ipv4": 2, "mac": 1, "hostname": 0.5,
        "config": 0.3}
P_CONTEXT = 6.5      # prompt / /etc/hosts gibi kesin bağlamlar
P_SPREAD  = 0.6      # önceden öğrenilmiş adların metnin başka yerlerinde geçmesi
P_ENTROPY = 0.45     # yedek: yüksek entropili dizgi

PAT = {
    "ipv4":  re.compile(r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\d.])"),
    "ipv6":  re.compile(r"(?<![0-9A-Fa-f:])(?:(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}|(?:[0-9A-Fa-f]{1,4}:){1,7}:|(?:[0-9A-Fa-f]{1,4}:){1,6}:[0-9A-Fa-f]{1,4}|(?:[0-9A-Fa-f]{1,4}:){1,5}(?::[0-9A-Fa-f]{1,4}){1,2}|(?:[0-9A-Fa-f]{1,4}:){1,4}(?::[0-9A-Fa-f]{1,4}){1,3}|(?:[0-9A-Fa-f]{1,4}:){1,3}(?::[0-9A-Fa-f]{1,4}){1,4}|(?:[0-9A-Fa-f]{1,4}:){1,2}(?::[0-9A-Fa-f]{1,4}){1,5}|[0-9A-Fa-f]{1,4}:(?::[0-9A-Fa-f]{1,4}){1,6}|:(?:(?::[0-9A-Fa-f]{1,4}){1,7}|:))(?![0-9A-Fa-f:])"),
    "email": re.compile(r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]+@(?:[A-Za-z0-9\-]+\.)+[A-Za-z]{2,}(?![A-Za-z0-9\-])"),
    "domain":re.compile(r"(?<![A-Za-z0-9.@\-])(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}(?![A-Za-z0-9\-])"),
    "mac":   re.compile(r"(?<![0-9A-Fa-f:\-])(?:[0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:\-])"),
}

# ---- özel / kamusal adresler ----
_PRIV_NETS = [ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",          # RFC1918
    "100.64.0.0/10", "169.254.0.0/16",                         # CGNAT, link-local
    "fc00::/7", "fe80::/10")]                                  # IPv6 ULA, link-local
PUBLIC_DNS = {"8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1", "9.9.9.9", "208.67.222.222", "208.67.220.220"}

def _ip_prefix(ip, v6=False):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return "IPV6" if v6 else "IP"
    base = "IPV6" if a.version == 6 else "IP"
    priv = any(a in n for n in _PRIV_NETS if n.version == a.version)
    return base + ("_PRIV" if priv else "_PUB")

def _benign_ip(ip):
    """127.0.0.0/8, 0.0.0.0, ::1, ::, çok yayın, maskeler (255.255.255.0) ve kamusal DNS — maskelenmez."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if a.is_loopback or a.is_unspecified or a.is_multicast: return True
    if a.version == 6: return a.is_reserved
    return ip.startswith("255.") or ip in PUBLIC_DNS

# Herkesin bildiği ağ blokları — "allow 10.0.0.0/8" hassas değil
WELL_KNOWN_NETS = {"10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16",
                   "127.0.0.0/8", "0.0.0.0/0", "224.0.0.0/4", "240.0.0.0/4", "::/0", "fc00::/7",
                   "fe80::/10", "ff00::/8"}

BENIGN_MACS = {"00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"}
def _benign_mac(m): return m.lower().replace("-", ":") in BENIGN_MACS

# ---- tarih ----
_D = r"(?:0?[1-9]|[12]\d|3[01])"
_M = r"(?:0?[1-9]|1[0-2])"
_Y = r"(?:19|20)\d{2}"
_MON = ("january|february|march|april|june|july|august|september|october|november|december|"
        "sept|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|"
        "ağustos|agustos|şubat|subat|haziran|temmuz|aralık|aralik|nisan|mayıs|mayis|kasım|kasim|"
        "eylül|eylul|ocak|mart|ekim")
_DATE_BODY = "|".join([
    _Y + r"([\-/.])" + _M + r"\1" + _D,                              # 2026-10-01  2026/10/01
    _D + r"([./\-])" + _M + r"\2" + _Y,                               # 01.10.2026  1/10/2026
    r"(?:0[1-9]|[12]\d|3[01])([./])(?:0[1-9]|1[0-2])\3\d{2}",         # 01.10.26 (sürüm 7.4.12 değil)
    _D + r"[ \-/.]?(?:" + _MON + r")\.?[ \-/.,]*" + _Y,              # 01 Oct 2026  01/Oct/2026  1 Ekim 2026
    r"(?:" + _MON + r")\.?[ \-]" + _D + r",?[ \-]" + _Y,              # Oct 1, 2026
])
DATE_RE = re.compile(r"(?<!\d)(?<!\d[.\-/])(?:" + _DATE_BODY + r")(?!\d|[.\-/]\d)", re.I)

# ---- parola / anahtar / token ----
_PW_CORE  = r"passwd|password|passwort|passphrase|pwd|şifre|sifre|parola"
_TOK_CORE = (r"client[_\-]?secret|secret[_\-]?key|private[_\-]?key|access[_\-]?key|api[_\-]?key|"
             r"apikey|access[_\-]?token|auth[_\-]?token|refresh[_\-]?token|credentials?|secret|token")
_KV_SEP   = r"[\"']?[ \t]*(?::=|=>|->|[:=>])[ \t]*"
_KV_VAL   = r"(?:(?P<q>[\"'])(?P<v1>[^\"'\r\n]{1,256})(?P=q)|(?P<v2>[^\s\"'<>,;&)}\]]{1,256}))"
SECRET_KV_RE = re.compile(
    r"(?<![\w.\-/])(?P<key>[\w.\-]*?(?P<core>" + _PW_CORE + "|" + _TOK_CORE + r")[\w.\-çğıöşüÇĞİÖŞÜ]*"
    r"|[\w.\-]*[_.\-](?P<suf>key|pass)|pass)" + _KV_SEP + _KV_VAL, re.I)
# anahtar adı bunlarla bitiyorsa değer gizli değil, üst bilgi: token_url, password_min_length…
SECRET_KEY_META = ("file", "path", "dir", "url", "uri", "length", "len", "size", "count", "ttl",
                   "timeout", "expiry", "expires", "expiration", "min", "max", "policy", "type",
                   "name", "id", "enabled", "required", "header", "prefix", "field", "param",
                   "algorithm", "alg", "rotation", "store", "location", "hint", "age", "format",
                   "mode", "method", "scope", "lifetime", "interval", "reset", "changed")
SECRET_KEY_NOT = ("primary_key", "foreign_key", "sort_key", "partition_key", "public_key", "hash_key",
                  "range_key", "cache_key", "row_key", "pubkey", "public-key", "publickey")
SECRET_CLI_RE = re.compile(r"(?<![\w\-])--?(?P<core>password|passwd|pass|pwd|token|api-key|secret)"
                           r"[ =](?P<v>[^\s\"']{2,256})", re.I)
CURL_USER_RE = re.compile(r"\bcurl\b[^\n|;]*?\s(?:-u|--user)\s+[\"']?(?P<u>[^:\s'\"]+):(?P<p>[^\s'\"]+)")
SECRET_BEARER_RE = re.compile(r"\b(?:Bearer|Basic)\s+(?P<v>[A-Za-z0-9\-._~+/]{8,}=*)")
SECRET_PEM_RE = re.compile(r"-----BEGIN ([A-Z ]*)PRIVATE KEY-----\r?\n(?P<body>[\s\S]+?)\r?\n-----END \1PRIVATE KEY-----")
SECRET_PATTERNS = [   # biçiminden tanınan anahtarlar
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),                         # AWS erişim anahtarı
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),                        # GitHub token
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"),                      # GitHub ince taneli token
    re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b"),                         # GitLab
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b"),                     # Slack
    re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),                            # Google API
    re.compile(r"\b[sr]k_(?:live|test)_[0-9A-Za-z]{16,}\b"),              # Stripe
    re.compile(r"\bhvs\.[A-Za-z0-9_\-]{20,}\b"),                          # HashiCorp Vault
    re.compile(r"\beyJ[\w\-]{8,}\.[\w\-]{8,}\.[\w\-]{8,}\b"),            # JWT
]
SECRET_SKIP = {"null", "none", "nil", "true", "false", "undefined", "empty", "yes", "no", "required",
               "optional", "string", "hidden", "masked", "redacted", "bearer", "basic"}

# ---- bağlantı dizgisi: scheme://kullanıcı:parola@sunucu:port/veritabanı ----
CONN_RE = re.compile(r"\b(?P<scheme>[a-z][a-z0-9+.\-]*)://(?:(?P<user>[^\s:/@'\"]*)(?::(?P<pw>[^\s/@'\"]*))?@)?"
                     r"(?P<host>\[[0-9A-Fa-f:]+\]|[^\s/:?#,;'\"@\[\]]+)(?::\d+)?(?:/(?P<db>[A-Za-z_][\w\-]*))?", re.I)
DB_SCHEMES = {"postgres", "postgresql", "mysql", "mariadb", "mongodb", "mongodb+srv", "sqlserver", "mssql",
              "oracle", "db2", "clickhouse", "cockroachdb", "redshift", "snowflake", "cassandra"}

def _secret_prefix(core=None, suf=None):
    c = (core or suf or "").lower()
    if re.fullmatch(_PW_CORE + "|pass", c): return "PAROLA"
    if "private" in c: return "ANAHTAR"
    return "TOKEN"

def _secret_ok(v, prefix):
    if not v or len(v) < 2 or is_token(v): return False
    low = v.lower()
    if low in SECRET_SKIP or set(v) <= set("*•#x?."): return False          # boş / zaten maskeli
    if re.match(r"^(\$\{|%\(|\{\{|<|\$[A-Z_])", v): return False             # ${DB_PASS} gibi değişken atıfları
    if prefix == "TOKEN" and v.isdigit(): return False                      # max_tokens: 4096
    return True

def _entropy(s):
    from math import log2
    n = len(s); freq = {}
    for ch in s: freq[ch] = freq.get(ch, 0) + 1
    return -sum(c / n * log2(c / n) for c in freq.values())

ENTROPY_RE = re.compile(r"(?<![\w+/=\-.])[A-Za-z0-9+/_\-]{20,}={0,2}(?![\w+/=\-.])")
def _looks_random(s):
    """Yedek gizli bilgi tespiti: 20+ karakter, büyük+küçük harf+rakam, yüksek entropi.
    Onaltılık kimlikler (konteyner ID, sha256, git commit) ve CamelCase adlar hariç."""
    if s.startswith("/") or s.count("/") > 2 or is_token(s): return False
    if re.fullmatch(r"[0-9a-fA-F\-]+", s): return False
    if not (re.search(r"[a-z]", s) and re.search(r"[A-Z]", s) and re.search(r"\d", s)): return False
    if re.search(r"(?:[A-Z][a-z]{2,}){3,}", s): return False                # AbstractConnectionFactory9
    return _entropy(s) >= 3.6

# ---- kullanıcı adları ----
_USER_VAL = (r"(?:(?P<q>[\"'])(?P<v1>[^\"'\r\n<>()]{1,64})(?P=q)|"
             r"(?P<v2>[^\s\"'<>,;&(){}\[\]|]{1,64}))")
USER_KV_RE = re.compile(
    r"(?<![\w.\-/])(?P<key>[\w.\-]*?(?:user(?:[_\-]?name)?|login|logname|user[ _\-]?id|uid))" + _KV_SEP + _USER_VAL, re.I)
USER_ID_RE  = re.compile(r"(?<![\w])(?:uid|gid|groups|euid)=(?:\d+\([\w.\-]+\),?)+")
USER_ID_ONE = re.compile(r"\d+\((?P<u>[\w.\-]+)\)")
USER_CLI_RE = re.compile(r"(?<![\w\-])--(?:user|username|login)(?:=|\s+)[\"']?(?P<v>[\w.\-@]+)")
USER_U_RE = re.compile(r"\b(?:mysql|mysqldump|mysqladmin|mariadb|psql|pg_dump|pg_dumpall|pg_restore|createdb|"
                       r"dropdb|sudo|su|crontab|mongosh|mongo|redis-cli|sqlcmd|influx|(?:docker|podman)\s+(?:exec|run))"
                       r"\b[^\n|;&]*?\s-[uU][ \t]*[\"']?(?P<v>[A-Za-z_][\w.\-@]*)")
SSH_RE  = re.compile(r"\b(?:ssh|scp|sftp|rsync|ssh-copy-id|mosh)\b[^\n|;&]*?\s(?P<u>[A-Za-z_][\w.\-]*)@"
                     r"(?P<h>[A-Za-z0-9][\w.\-]*)")
HOME_RE = re.compile(r"(?:/home/|/Users/|[A-Za-z]:\\Users\\|\\\\Users\\\\)(?P<u>[A-Za-z_][\w.\-]*)")
SSHD_RE = re.compile(r"\b(?:Accepted \w+ for|Failed \w+ for(?: invalid user)?|Invalid user|"
                     r"session (?:opened|closed) for user|Disconnected from(?: invalid| authenticating)? user|"
                     r"pam_unix\([^)]*\): [^\n]*? user)\s+(?P<u>[A-Za-z_][\w.\-]*)")
SUDO_RE = re.compile(r"\bsudo(?:\[\d+\])?:\s+(?P<u>[A-Za-z_][\w.\-]*)\s+:")
USER_SKIP = {"unknown", "invalid", "none", "null", "anonymous", "public", "default", "shared",
             "all users", "everyone", "local", "remote", "true", "false"}

# ---- shell prompt ----
PROMPT_RE1 = re.compile(r"(?m)(?:^|(?<=[\s)\]]))(?P<u>[a-z_][\w.\-]{0,31})@(?P<h>[A-Za-z0-9][\w.\-]{0,62}):"
                        r"(?P<d>[^\s$#]*)[$#](?=\s|$)")
PROMPT_RE2 = re.compile(r"\[(?P<u>[a-z_][\w.\-]{0,31})@(?P<h>[A-Za-z0-9][\w.\-]{0,62})\s+(?P<d>[^\]\s]+)\]\s?[$#]")
PROMPT_PS  = re.compile(r"(?m)^PS (?P<d>[A-Za-z]:\\[^>\n]*)>")
# Bu dizinlerin altındaki adlar sistem/ürün dizinidir, proje sayılmaz (/var/lib/postgresql…)
SYSTEM_PATHS = ("/var/lib", "/var/log", "/var/cache", "/var/spool", "/var/run", "/etc", "/usr", "/proc",
                "/sys", "/dev", "/run", "/boot", "/lib", "/bin", "/sbin", "/tmp", "/snap", "/nix")
DIR_CTX_RE = re.compile(r"\b(?:PWD|OLDPWD|working_dir|WorkingDir|workdir|project\.working_dir)[\"']?\s*[=:]\s*"
                        r"[\"']?(?P<d>/[^\s\"';,]+)")
DEPLOY_RE = re.compile(r"(?:Deployed|Undeployed|Replaced deployment|Starting deployment of|Stopped deployment|"
                       r"runtime-name\s*:)\s*\\?\"(?P<p>[A-Za-z][\w\-]*?)\.(?:war|ear|jar|rar|sar)\\?\"")
UPSTREAM_RE = re.compile(r"\bupstream\s+(?P<n>[A-Za-z][\w.\-]*)\s*\{")
# Alt alan adı olarak çok yaygın, metnin geri kalanına yayılmayacak etiketler
SUBDOMAIN_COMMON = set("""www mail smtp imap pop pop3 ftp sftp vpn portal intranet extranet api app apps
    auth sso login cdn static assets img images media admin panel dev test stage staging prod beta
    demo docs wiki git gitlab jenkins grafana kibana monitor status shop store blog news web ns ns1 ns2
    mx owa webmail remote secure cloud files support help crm erp hr db sql ldap ad dc proxy gateway
    registry repo nexus harbor console""".split())
def _label_spreads(lbl):
    low = lbl.lower()
    return (len(lbl) >= 4 and low not in SUBDOMAIN_COMMON and low not in COMMON_WORDS
            and low not in HOST_PRODUCT and not re.search(r"\d", lbl))

STD_DIRS = set("""~ / root home etc var opt srv tmp usr local bin sbin lib lib64 log logs data app apps
    src code projects project proje projeler work workspace repos repo git docker compose deploy backup
    backups www html conf config configs nginx jboss wildfly standalone configuration deployments
    Desktop Downloads Documents Masaüstü İndirilenler Belgeler build dist target node_modules venv .venv
    scripts test tests docs mnt media run dev proc sys boot cache spool mail share include system32
    Windows Users sites-enabled sites-available conf.d ssl certs secrets volumes""".split())

# ---- syslog / journal: "Oct 01 09:12:01 web01 sshd[1234]:" ----
SYSLOG_RE = re.compile(r"(?m)^(?:[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}|"
                       r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+"
                       r"(?P<h>[A-Za-z0-9][\w.\-]{0,62})\s+(?P<p>[A-Za-z][\w\-./@]*)(?:\[\d+\])?:\s")
LOG_LEVELS = {"INFO", "WARN", "WARNING", "ERROR", "DEBUG", "TRACE", "FATAL", "NOTICE", "CRIT",
              "CRITICAL", "SEVERE", "FINE", "FINER", "FINEST", "ALERT", "EMERG", "ERR"}

# ---- /etc/hosts satırı: "10.10.10.20  db01.sirket.com.tr db01" ----
HOSTS_RE = re.compile(r"(?m)^[ \t]*(?P<ip>(?:\d{1,3}\.){3}\d{1,3}|[0-9A-Fa-f:]*:[0-9A-Fa-f:]+)[ \t]+"
                      r"(?P<names>[A-Za-z0-9][\w.\-]*(?:[ \t]+[A-Za-z0-9][\w.\-]*){0,7})[ \t\r]*(?:#[^\n]*)?$")
HOST_KEEP = {"localhost", "localhost.localdomain", "localdomain", "broadcasthost", "ip6-localhost",
             "ip6-loopback", "ip6-localnet", "ip6-mcastprefix", "ip6-allnodes", "ip6-allrouters",
             "ip6-allhosts", "host.docker.internal", "gateway.docker.internal"}

# ---- ağ arayüzleri ----
IFACE_STD_RE = re.compile(r"(?:lo|eth\d+|ens\d+(?:f\d+)?(?:np\d+)?|enp\d+s\d+(?:f\d+)?(?:np\d+)?|eno\d+|"
                          r"enx[0-9a-f]{12}|em\d+|p\d+p\d+|wlan\d+|wlp\d+s\d+|wlo\d+|docker\d+|veth[0-9a-f]+|"
                          r"virbr\d+(?:-nic)?|tun\d+|tap\d+|wg\d+|bond\d+|team\d+|cni\d+|flannel\.\d+|"
                          r"cali[0-9a-f]+|tunl\d+|vxlan\.calico|vxlan\d*|kube-ipvs\d+|kube-bridge|br\d+|if\d+|"
                          r"ip6tnl\d+|sit\d+|gre\d+|gretap\d+|erspan\d+|ip_vti\d+|ip6_vti\d+|ip6gre\d+|"
                          r"lxcbr\d+|lxdbr\d+|podman\d+|cilium_\w+|nodelocaldns|dummy\d+|ovs-system|br-int|"
                          r"br-ex|ens\d+\.\d+|eth\d+\.\d+)", re.I)
def is_std_iface(n): return bool(IFACE_STD_RE.fullmatch(n or ""))
IFACE_LINE_RE = re.compile(r"(?m)^\d+:\s+(?P<i>[^\s:@]+)(?:@(?P<peer>[^\s:]+))?:\s+<")
IFCONFIG_RE   = re.compile(r"(?m)^(?P<i>[A-Za-z][\w.\-]*?):?\s+(?:flags=|Link encap)")
IFACE_REF_RE  = re.compile(r"\b(?:dev|master|iif|oif|iface|interface|vlan-raw-device|bridge_ports)\s+"
                           r"(?P<i>[A-Za-z][\w.\-]*)")
BRIDGE_RE     = re.compile(r"\bbr-[0-9a-f]{12}\b")

# ---- konteyner / compose projesi ----
DOCKER_PS_HDR = re.compile(r"(?m)^CONTAINER ID\s+IMAGE\s+.*\bNAMES[ \t\r]*$")
DOCKER_IMAGES_HDR = re.compile(r"(?m)^REPOSITORY\s+TAG\s+IMAGE ID\b[^\n]*$")
# Docker Hub resmi imajları — yerel (kullanıcıya özel) imaj sayılmaz
OFFICIAL_IMAGES = set("""postgres mysql mariadb redis valkey nginx httpd node python alpine ubuntu debian
    busybox mongo mongo-express rabbitmq elasticsearch kibana logstash grafana prometheus traefik caddy
    memcached wordpress php golang openjdk eclipse-temurin amazoncorretto ibmjava jenkins sonarqube
    registry adminer haproxy consul vault influxdb telegraf zookeeper kafka cassandra couchdb neo4j
    nextcloud gitea ghost drupal joomla tomcat jetty centos fedora rockylinux almalinux oraclelinux
    amazonlinux docker hello-world swarm solr nats etcd minio keycloak ruby rust perl gcc maven
    gradle composer bash vaultwarden portainer pgadmin4 phpmyadmin percona clickhouse""".split())
CONTAINER_NAME_RE = re.compile(r"(?:--name[ =][\"']?|container_name:[ \t]*[\"']?|\"Name\"\s*:\s*\"/)"
                               r"(?P<n>[A-Za-z0-9][\w.\-]*)")
DOCKER_CMD_RE = re.compile(
    r"\b(?:docker|podman)\s+(?:container\s+)?(?:logs|exec|inspect|restart|stop|start|rm|kill|attach|top|"
    r"stats|port|cp|update|wait|pause|unpause|rename|commit|diff|export)\b"
    r"(?:\s+(?:(?:--(?:tail|since|until|user|env|workdir|env-file|format|time|signal|detach-keys)|-[nuew])"
    r"(?:=|\s+)\S+|-{1,2}[\w\-]+(?:=\S+)?))*\s+(?P<n>[A-Za-z0-9][\w.\-]*)")
COMPOSE_PROJECT_RE = re.compile(
    r"(?:com\.docker\.compose\.project[\"']?\s*[:=]\s*[\"']?|COMPOSE_PROJECT_NAME[ \t]*=[ \t]*[\"']?|"
    r"\bdocker[ \-]compose\b[^\n]*?\s(?:-p|--project-name)[ =][\"']?)(?P<p>[A-Za-z0-9][\w.\-]*)")
COMPOSE_NAME_RE = re.compile(r"^(?P<p>[A-Za-z0-9][\w.\-]*?)[-_](?P<s>[a-z0-9][a-z0-9.]*)[-_](?P<n>\d+)$")
DOCKER_WORDS = {"bash", "sh", "zsh", "ash", "python", "node", "java", "psql", "mysql", "redis-cli",
                "cat", "ls", "env", "printenv", "true", "false"}

# Yayılmayacak (metnin her yerinde aranmayacak) genel kelimeler
COMMON_WORDS = set("""app api web www db data test prod dev stage staging main master default
    backend frontend server client service worker proxy cache mail admin user users home public
    private local remote config docs src lib bin log logs tmp root""".split())

# ---- hostname ----
HOST_BLOCK = set(["md5","md2","md4","sha1","sha2","sha3","sha224","sha256","sha384","sha512","ripemd160",
    "crc32","adler32","base64","base32","utf8","utf16","utf32","utf8mb4","latin1","iso88591","x8664",
    "amd64","arm64","aarch64","armv7l","i386","i686","ppc64le","s390x","win32","win64","http2","http3",
    "h2","h2c","tls10","tls11","tls12","tls13","tlsv1","tlsv12","tlsv13","ssl2","ssl3","sslv3","ipv4",
    "ipv6","ip4","ip6","inet4","inet6","icmp6","icmpv6","tcp4","tcp6","udp4","udp6","raw6","ssh1","ssh2",
    "oauth2","ec2","s3","k8s","k3s","i18n","l10n","a11y","p2p","log4j","log4j2","ext2","ext3","ext4",
    "fat32","ntfs","rfc822","x509","pkcs1","pkcs7","pkcs8","pkcs11","pkcs12","p12","ed25519","ed448",
    "rsa1024","rsa2048","rsa4096","nistp256","nistp384","nistp521","secp256r1","secp384r1","prime256v1",
    "aes128","aes192","aes256","chacha20","poly1305","overlay2","cgroup2","cgroupv2","netns0","el7",
    "el8","el9","fc38","fc39","fc40","win10","win11","dotnet6","dotnet8","node18","node20","node22"])

KW_RE  = re.compile(r"\b(?:hostname|nodename|node|computername|computer|dnsname|host|cn)\b\s*[:=]\s*[\"']?"
                    r"([A-Za-z][A-Za-z0-9\-]{1,62})[\"']?", re.I)
TOK_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*\b")

# "thread-12", "pool-3", "worker-7", "port8080"… hostname değil — log gürültüsü
HOST_NOISE = {"thread","threads","pool","worker","workers","task","tasks","exec","executor",
    "nio","ajp","main","job","batch","session","sess","req","request","conn","connection",
    "tx","timer","scheduler","async","default","eventloop","loop","reactor","line","row","col",
    "page","step","item","port","pid","tid","build","rev","release","version","ver","attempt",
    "retry","try","phase","stage","part","chunk","index","idx","slot","queue","listener",
    "handler","consumer","producer","partition","offset","epoch","gen","generation","pts","tty"}
# ürün adıyla başlayanlar ("java17", "jboss-eap-7", "java-17-openjdk-amd64") hostname değil
HOST_PRODUCT = {"java","jdk","jre","jvm","openjdk","jboss","wildfly","eap","tomcat","spring",
    "hibernate","postgres","postgresql","pg","mysql","mariadb","mssql","oracle","ora","redis",
    "kafka","nginx","apache","httpd","centos","rhel","el","ubuntu","debian","windows","win",
    "python","py","npm","tls","tlsv","ssl","sslv","http","https","utf","iso","cp","sha",
    "md","ipv","rfc","cve","jsr","jep","log","slf","logback","junit","maven","gradle","v",
    "alpine","node","golang","go","php","ruby","dotnet","kernel","linux","fedora","rocky","alma"}

# Gerçek alan adı TLD'leri — "org.jboss.as.controller", "server.log", "standalone.xml",
# "AbstractPool.java" gibi paket/dosya adlarının DNS sanılmasını önler.
TLDS = set("""com net org io co info biz tr uk de eu us gov edu mil int local lan internal
    intranet intra corp home localdomain cloud dev app ai tech systems online site xyz me nl fr
    it es ru ch at be se no dk fi cz gr ro hu az kz ua il ae sa qa in cn jp kr sg hk tw au nz ca
    br mx za arpa""".split())
TWO_LEVEL = set("""com.tr net.tr org.tr gov.tr edu.tr bel.tr k12.tr gen.tr av.tr bbs.tr
    co.uk org.uk ac.uk gov.uk com.au net.au co.jp co.kr com.br com.cn co.za co.in""".split())
# Genel/kamusal alan adları ve container registry'leri — maskelemeye gerek yok
BENIGN_DOMAINS = set("""example.com example.org example.net localhost.localdomain github.com
    gitlab.com stackoverflow.com google.com microsoft.com apple.com redhat.com oracle.com
    jboss.org wildfly.org apache.org python.org pypi.org npmjs.com npmjs.org maven.org spring.io
    openai.com anthropic.com claude.ai chatgpt.com ubuntu.com debian.org centos.org kernel.org
    mozilla.org w3.org ietf.org wikipedia.org docker.com docker.io kubernetes.io k8s.io ghcr.io
    quay.io gcr.io pkg.dev postgresql.org mysql.com mariadb.org cloudflare.com letsencrypt.org
    xmlsoap.org jcp.org sun.com java.com openjdk.org hibernate.org eclipse.org jakarta.ee
    alpinelinux.org fedoraproject.org rockylinux.org almalinux.org golang.org nodejs.org
    githubusercontent.com elastic.co hashicorp.com grafana.com prometheus.io nginx.org nginx.com
    googleapis.com gstatic.com""".split())


def _split_domain(d):
    """'app01.sirket.com.tr' → (['app01'], 'sirket.com.tr') — iki seviyeli uzantıları tanır."""
    labels = d.split(".")
    n = 3 if len(labels) >= 3 and ".".join(labels[-2:]).lower() in TWO_LEVEL else 2
    return labels[:-n], ".".join(labels[-n:])

def _valid_domain(d):
    tld = d.rsplit(".", 1)[-1]
    if tld != tld.lower() or tld not in TLDS: return False      # Java sınıfı / dosya uzantısı
    low = d.lower()
    if any(low == b or low.endswith("." + b) for b in BENIGN_DOMAINS): return False
    return True

def _benign_domain(d):
    low = d.lower()
    return any(low == b or low.endswith("." + b) for b in BENIGN_DOMAINS)

# ---- config anahtarları ----
# Serbest anahtarlar: ayraçsız da olur ("datasource jboss")
CFG_FREE = ["datasource name","datasource","data source","data-source","jndi name","jndi-name",
    "jndi","pool name","pool-name","database name","database-name","schema name","service name",
    "instance name","connection pool","connection-pool"]
# Genel kelimeler: yalnızca açık ayraçla (":", "=", XML ">") — düz cümlede yanlış eşleşmesin
CFG_STRICT = ["database","databasename","db name","db-name","dbname","db","schema","schema-name",
    "catalog","ds name","dsname","pool","servicename","service-name","sid","instance",
    "instance-name","realm","context root","context-root"]
def _cfg_alt(keys):
    return "|".join(r"\s+".join(re.escape(p) for p in k.split()) for k in sorted(keys, key=len, reverse=True))
_CFG_VAL = r"[ \t]*[\"']?([A-Za-z_][\w.\-\/:]*)[\"']?"
CFG_FREE_RE   = re.compile(r"(?<!/)\b(" + _cfg_alt(CFG_FREE) + r")\b[ \t]*(?:[:=>]|:=|=>|->)?" + _CFG_VAL, re.I)
CFG_STRICT_RE = re.compile(r"(?<!/)\b(" + _cfg_alt(CFG_STRICT) + r")\b[ \t]*(?:[:=>]|:=|=>|->)" + _CFG_VAL, re.I)
# .env / ortam değişkeni biçimi: DB_NAME=appdb, POSTGRES_DB=appdb, MYSQL_DATABASE=appdb
CFG_ENV_RE = re.compile(r"(?<![\w.\-/])(?P<key>[A-Za-z0-9_.\-]*?(?:db[_\-]?name|database(?:[_\-]?name)?|"
                        r"postgres_db|mysql_database|schema(?:[_\-]?name)?|jndi[_\-]?name|"
                        r"datasource(?:[_\-]?name)?))[\"']?[ \t]*[=:][ \t]*[\"']?(?P<v>[A-Za-z_][\w.\-\/:]*)", re.I)
CFG_STOP = set(["is","are","was","were","be","been","the","a","an","of","for","to","in","on",
    "and","or","not","no","yes","true","false","null","none","name","value","type","this","that",
    "with","ise","olarak","bir","ve","veya","için","ile","adı","adi","ismi","olan","gibi"])
CFG_STOP |= {k.lower() for k in CFG_FREE + CFG_STRICT}   # "<datasource jndi-name=…>" → "jndi-name" değer değil
CFG_STOP |= {"jndi-name", "pool-name", "user-name", "enabled", "use-java-context", "statistics-enabled"}

def _cfg_prefix(key):
    """Config anahtarına göre etiket: datasource jboss → DS_1, DB_NAME=appdb → DB_1 …"""
    k = re.sub(r"[\s_\-.]", "", key.lower())
    if "jndi" in k: return "JNDI"
    if "datasource" in k or k in ("dsname", "pool", "poolname", "connectionpool"): return "DS"
    if "schema" in k: return "SCHEMA"
    if any(x in k for x in ("database", "dbname", "postgresdb", "mysqldatabase")) or \
       k in ("db", "catalog", "sid", "servicename", "instance", "instancename"): return "DB"
    return "AYAR"

LABELS = {"ipv4":"IPv4","ipv6":"IPv6","domain":"DNS","email":"E-POSTA","mac":"MAC",
          "hostname":"HOST","user":"USER","container":"DOCKER","project":"PROJE","iface":"IFACE",
          "config":"CONFIG","secret":"PAROLA","date":"TARİH","custom":"ÖZEL"}
ALL_TYPES = ("ipv4","ipv6","domain","hostname","mac","iface","email","user","container",
             "config","secret","date","custom")
# Tarihler varsayılan olarak yalnızca TANINIR (IP sanılmaz) ama maskelenmez: zaman çizelgesi
# hata ayıklamak için gerekli. İstenirse "TARİH" seçeneği açılır → TARIH_1.
DEFAULT_OFF = {"date"}
def default_opts(): return {t: t not in DEFAULT_OFF for t in ALL_TYPES}
OPT_OF = {"project": "container"}          # proje adları DOCKER seçeneğine bağlı


def _user_ok(v):
    if not v or len(v) < 2 or v.isdigit() or is_token(v): return False
    low = v.lower()
    if low in USER_SKIP or "/" in v or "$" in v or "{" in v: return False
    if low in SYSTEM_USERS and not MASK_SYSTEM_USERS: return False
    return True

def _host_label_ok(v):
    if not v or len(v) < 2 or is_token(v) or v.isdigit(): return False
    low = v.lower()
    if low in HOST_KEEP or low in HOST_BLOCK or v.upper() in LOG_LEVELS or is_std_iface(v): return False
    if re.fullmatch(r"[0-9a-f]{12}|[0-9a-f]{64}", low): return False          # konteyner ID
    return True

def _looks_like_host(tok):
    if len(tok) < 3 or len(tok) > 63: return False
    if not re.search(r"\d", tok): return False
    low = tok.lower()
    if low.replace("-","") in HOST_BLOCK or low in HOST_KEEP or is_std_iface(tok): return False
    if re.search(r"ipv[46]|ip6|inet6", low): return False                  # GlobalIPv6Address, ip6-localhost
    m = re.match(r"[a-z]+", low)
    first = m.group(0) if m else ""
    if first in HOST_NOISE or first in HOST_PRODUCT: return False          # thread-12, java-17-openjdk
    if not re.search(r"[a-z]", tok) and re.search(r"\d{4,}", tok):
        return False                                                       # WFLYCTL0013, ORA-00942
    if re.fullmatch(r"[0-9a-f\-]{8,}", low): return False                  # hash / UUID parçası
    if "-" not in tok and len(first) < 2: return False
    return True

def _bounded(v):
    return re.compile(r"(?<![A-Za-z0-9._\-\/])" + re.escape(v) + r"(?![A-Za-z0-9_\-\/]|\.[A-Za-z0-9])")

def _spread_re(v):
    """Öğrenilmiş adlar: kenarında harf/rakam olmasın; - _ . / serbest (ithub-web-1, /home/kemal)."""
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(v) + r"(?![A-Za-z0-9])")


class Mapper:
    """Gerçek ↔ etiket defteri. Parola/anahtar/token eşleşmeleri yalnızca bellekte tutulur.
    store=None → diske hiç dokunmaz (testler için)."""
    def __init__(self, store="__default__"):
        self.store = STORE if store == "__default__" else store
        self.lock = threading.RLock()
        self._reset()
        self.custom_terms = []
        self.load()

    def _reset(self):
        self.entries = []          # [{real, fake, type, secret?, prop?}]
        self.real_to_fake = {}     # gerçek → etiket (diske yazılır)
        self.by_real = {}          # gerçek → defter kaydı
        self.secret_map = {}       # gerçek parola → etiket (yalnızca bellek)
        self.tok = {}              # etiket → gerçek
        self.counters = {}         # önek → son numara

    # ---- etiket üretimi ----
    def _token(self, prefix):
        n = self.counters.get(prefix, 0) + 1
        self.counters[prefix] = n
        return "%s_%d" % (prefix, n)

    def _register(self, real, typ, prefix, secret=False, prop=False):
        m = self.secret_map if secret else self.real_to_fake
        if real in m and not (not secret and self._should_upgrade(m[real], prefix)):
            if prop and not secret and real in self.by_real:
                self.by_real[real]["prop"] = True            # sonradan bağlamla doğrulandı → yay
            return m[real]
        t = self._token(prefix)
        m[real] = t; self.tok[t] = real
        e = {"real": real, "fake": t, "type": typ}
        if secret: e["secret"] = True
        if prop: e["prop"] = True
        self.entries.append(e)
        if not secret: self.by_real[real] = e
        return t

    @staticmethod
    def _should_upgrade(old, prefix):
        """Defterdeki etiket eski/genel bir türdeyse ve bağlam daha kesin bir tür bulduysa yeni etiket ver.
        Eski etiket defterde kalır, eski AI cevapları geri çevrilmeye devam eder.
        Örn. eski sürümden HOST_10 (br-3f2a…) → IFACE_1, IP_5 → IP_PRIV_3."""
        if not is_token(old): return True                         # ilk sürümün gerçekçi sahteleri
        op = old.rsplit("_", 1)[0]
        if op == prefix: return False
        if op in ("IP", "IPV6", "KULLANICI"): return True         # sürüm 2 önekleri
        return op == "HOST" and prefix in ("IFACE", "CONTAINER", "PROJE", "USER")

    def _get_fake(self, value, typ, prefix=None, prop=False):
        if typ == "domain":
            subs, base = _split_domain(value)
            return ".".join([self._register(s, "hostname", "HOST", prop=_label_spreads(s)) for s in subs] +
                            [self._register(base, "domain", "DOMAIN")])
        if typ in ("ipv4", "ipv6"):
            return self._register(value, typ, _ip_prefix(value, typ == "ipv6"))
        if typ == "secret":
            return self._register(value, typ, prefix or "PAROLA", secret=True)
        return self._register(value, typ, prefix or TYPE_PREFIX.get(typ, "AYAR"), prop=prop)

    # ---- tespit ----
    def _collect(self, text, opts=None):
        """Hassas değerleri bulur: [(başlangıç, bitiş, değer, tür, önek, yay)]. Mevcut etiketlere dokunmaz."""
        opts = dict(default_opts(), **(opts or {}))
        on = lambda typ: opts.get(OPT_OF.get(typ, typ), False)
        found = []          # (s, e, v, typ, prefix, prio, prop)
        learned = {}        # bu metinde bağlamdan öğrenilen adlar: değer → (tür, önek)

        def add(s, e, v, typ, prefix=None, prio=None, prop=False):
            if not on(typ) or s >= e: return
            found.append((s, e, v, typ, prefix, PRIO[typ] if prio is None else prio, prop))
            if prop: learned.setdefault(v, (typ, prefix))

        def add_host(s, v, prio, prop=True):
            """Bağlamdan gelen sunucu adı: FQDN → alan adı, değilse HOST (yayılır)."""
            if "." in v and _valid_domain(v):
                add(s, s + len(v), v, "domain", prio=prio)
            elif "." in v and _benign_domain(v):
                return
            elif _host_label_ok(v):
                add(s, s + len(v), v, "hostname", prio=prio, prop=prop)

        def add_user(s, v, prio=None):
            if _user_ok(v): add(s, s + len(v), v, "user", prio=prio, prop=True)

        def add_container(s, name, prio=None):
            if not name or is_token(name) or name in DOCKER_WORDS or re.fullmatch(r"[0-9a-f]{12,64}", name):
                return
            m = COMPOSE_NAME_RE.match(name)
            if m and len(m.group("p")) >= 2:                          # ithub-web-1 → PROJE_1-web-1
                add(s, s + len(m.group("p")), m.group("p"), "project", prio=prio, prop=True)
            else:
                add(s, s + len(name), name, "container", prio=prio, prop=True)

        # --- 1) parolalar / anahtarlar ---
        if on("secret"):
            secrets = {}
            def add_secret(s, v, p):
                add(s, s + len(v), v, "secret", p); secrets[v] = p
            for m in SECRET_KV_RE.finditer(text):
                key = m.group("key"); kl = key.lower()
                if kl.endswith(SECRET_KEY_META) or kl.endswith(SECRET_KEY_NOT): continue
                p = _secret_prefix(m.group("core"), m.group("suf") or ("pass" if kl == "pass" else None))
                g = "v1" if m.group("v1") is not None else "v2"
                v = m.group(g)
                if g == "v2": v = v.rstrip(".:")
                if key in ("PWD", "OLDPWD") and v.startswith("/"): continue      # çalışma dizini
                if _secret_ok(v, p): add_secret(m.start(g), v, p)
            for m in SECRET_CLI_RE.finditer(text):
                p = _secret_prefix(m.group("core")); v = m.group("v")
                if _secret_ok(v, p): add_secret(m.start("v"), v, p)
            for m in CURL_USER_RE.finditer(text):
                add_user(m.start("u"), m.group("u"))
                if _secret_ok(m.group("p"), "PAROLA"): add_secret(m.start("p"), m.group("p"), "PAROLA")
            for m in SECRET_BEARER_RE.finditer(text):
                add_secret(m.start("v"), m.group("v"), "TOKEN")
            for m in SECRET_PEM_RE.finditer(text):
                add(m.start("body"), m.end("body"), m.group("body"), "secret", "ANAHTAR")
            for rx in SECRET_PATTERNS:
                for m in rx.finditer(text):
                    add_secret(m.start(), m.group(0), "TOKEN")
            for m in ENTROPY_RE.finditer(text):                      # yedek: rastgele görünen dizgi
                if _looks_random(m.group(0)):
                    add(m.start(), m.end(), m.group(0), "secret", "TOKEN", prio=P_ENTROPY)
            # aynı parola metnin başka bir yerinde etiketsiz geçiyorsa onu da gizle
            for v, p in list(secrets.items()):
                if len(v) >= 6:
                    for m in _bounded(v).finditer(text): add(m.start(), m.end(), v, "secret", p)

        # --- 2) bağlantı dizgisi: kullanıcı, parola, sunucu, veritabanı ayrı ayrı ---
        conn_dbs = {}
        for m in CONN_RE.finditer(text):
            if m.group("user"): add_user(m.start("user"), m.group("user"), prio=P_CONTEXT)
            pw = m.group("pw")
            if pw and _secret_ok(pw, "PAROLA"):
                add(m.start("pw"), m.end("pw"), pw, "secret", "PAROLA", prio=8)
            h = m.group("host")
            if h and not is_token(h) and not PAT["ipv4"].fullmatch(h) and not h.startswith("["):
                if "." in h and _valid_domain(h):
                    add(m.start("host"), m.end("host"), h, "domain", prio=P_CONTEXT)
                elif "." not in h and _looks_like_host(h):
                    add(m.start("host"), m.end("host"), h, "hostname", prio=P_CONTEXT)
            db = m.group("db")
            if db and m.group("scheme").lower() in DB_SCHEMES and not is_token(db):
                add(m.start("db"), m.end("db"), db, "config", "DB", prio=P_CONTEXT)
                conn_dbs[db] = "DB"                      # metnin başka yerlerinde de (psql … appdb)

        # --- 3) shell prompt: kullanıcı@sunucu:dizin$ ---
        def prompt_dir(d, base):
            d = d.rstrip("/\\")
            if any(d == sp or d.startswith(sp + "/") for sp in SYSTEM_PATHS): return
            name = re.split(r"[/\\]", d)[-1] if d else ""
            low = name.lower()
            if name and name not in STD_DIRS and len(name) >= 3 and not name.startswith("~") \
               and not is_token(name) and low not in COMMON_WORDS and low not in HOST_PRODUCT \
               and _user_ok(name) and not (home_user and name == home_user):
                add(base + len(d) - len(name), base + len(d), name, "project", prio=P_CONTEXT, prop=True)
        home_user = None
        for rx in (PROMPT_RE1, PROMPT_RE2):
            for m in rx.finditer(text):
                if not is_token(m.group("u")): add_user(m.start("u"), m.group("u"), prio=P_CONTEXT)
                if not is_token(m.group("h")): add_host(m.start("h"), m.group("h"), P_CONTEXT)
                prompt_dir(m.group("d"), m.start("d"))
        for m in PROMPT_PS.finditer(text):
            prompt_dir(m.group("d"), m.start("d"))
        for m in DIR_CTX_RE.finditer(text):
            hm = HOME_RE.search(m.group("d")); home_user = hm.group("u") if hm else None
            prompt_dir(m.group("d"), m.start("d"))
        home_user = None
        for m in DEPLOY_RE.finditer(text):
            if not is_token(m.group("p")):
                add(m.start("p"), m.end("p"), m.group("p"), "project", prop=True)
        for m in UPSTREAM_RE.finditer(text):
            n = m.group("n")
            if not is_token(n) and n.lower() not in COMMON_WORDS:
                cm = re.match(r"([A-Za-z][A-Za-z0-9]*?)[_\-](?:backend|upstream|app|api|web|servers?|pool)$", n)
                if cm and _label_spreads(cm.group(1)):
                    add(m.start("n"), m.start("n") + len(cm.group(1)), cm.group(1), "project", prop=True)

        # --- 4) kullanıcı adları ---
        for m in HOME_RE.finditer(text):
            add_user(m.start("u"), m.group("u"))
        for m in USER_KV_RE.finditer(text):
            g = "v1" if m.group("v1") is not None else "v2"
            add_user(m.start(g), m.group(g).rstrip(".:"))
        for m in USER_ID_RE.finditer(text):
            for u in USER_ID_ONE.finditer(m.group(0)):
                add_user(m.start() + u.start("u"), u.group("u"))
        for rx in (USER_CLI_RE, USER_U_RE):
            for m in rx.finditer(text): add_user(m.start("v"), m.group("v"))
        for rx in (SSHD_RE, SUDO_RE):
            for m in rx.finditer(text): add_user(m.start("u"), m.group("u"))
        for m in SSH_RE.finditer(text):
            add_user(m.start("u"), m.group("u"), prio=P_CONTEXT)
            add_host(m.start("h"), m.group("h"), P_CONTEXT)

        # --- 5) sunucu adı bağlamları: journal, /etc/hosts ---
        for m in SYSLOG_RE.finditer(text):
            if m.group("h").upper() not in LOG_LEVELS: add_host(m.start("h"), m.group("h"), P_CONTEXT)
        for m in HOSTS_RE.finditer(text):
            if not (PAT["ipv4"].fullmatch(m.group("ip")) or PAT["ipv6"].fullmatch(m.group("ip"))): continue
            off = m.start("names")
            for n in re.finditer(r"\S+", m.group("names")):
                add_host(off + n.start(), n.group(0), P_CONTEXT)

        # --- 6) ağ arayüzleri ---
        def add_iface(s, name):
            if name and not is_std_iface(name) and not is_token(name):
                add(s, s + len(name), name, "iface", prop=True)
        for m in IFACE_LINE_RE.finditer(text): add_iface(m.start("i"), m.group("i"))
        for m in IFCONFIG_RE.finditer(text):   add_iface(m.start("i"), m.group("i"))
        for m in IFACE_REF_RE.finditer(text):
            if re.search(r"[\d\-]", m.group("i")): add_iface(m.start("i"), m.group("i"))
        for m in BRIDGE_RE.finditer(text):     add_iface(m.start(), m.group(0))

        # --- 7) konteynerler / compose projesi ---
        for m in COMPOSE_PROJECT_RE.finditer(text):
            p = m.group("p")
            if not is_token(p) and len(p) >= 2:
                add(m.start("p"), m.end("p"), p, "project", prop=True)
        for rx in (CONTAINER_NAME_RE, DOCKER_CMD_RE):
            for m in rx.finditer(text): add_container(m.start("n"), m.group("n"))
        def image_parts(img):
            """'ghcr.io/x/app:1.2' → (repo='ghcr.io/x/app', public?, yerel?)"""
            repo = re.split(r"[:@]", img, 1)[0] if not img.startswith("[") else img
            first = repo.split("/")[0]
            has_registry = "/" in repo and ("." in first or ":" in first or first == "localhost")
            if has_registry:
                return repo, _benign_domain(first), False
            if "/" in repo:                                           # Docker Hub kurum/imaj
                return repo, True, False
            return repo, repo in OFFICIAL_IMAGES, repo not in OFFICIAL_IMAGES
        def add_local_image(s, repo, cname=None):
            """Yerel imaj adı kullanıcıya özeldir: compose imajı 'proje-servis' ise proje kısmı,
            değilse adın tamamı PROJE olur (dockotp-totp-panel → PROJE_4)."""
            cm = COMPOSE_NAME_RE.match(cname or "")
            if cm and repo in (cm.group("p") + "-" + cm.group("s"), cm.group("p") + "_" + cm.group("s")):
                add(s, s + len(cm.group("p")), cm.group("p"), "project", prop=True)
            elif not is_token(repo) and len(repo) >= 3:
                add(s, s + len(repo), repo, "project", prop=True)
        for h in DOCKER_PS_HDR.finditer(text):
            pos = h.end() + 1
            for line in text[pos:].split("\n"):
                row = re.match(r"([0-9a-f]{12})\s+(?P<img>\S+)", line)
                if not row: break                                     # satır konteyner ID ile başlamalı
                last = re.search(r"(\S+)\s*$", line)
                names = list(re.finditer(r"[^,\s]+", last.group(1))) if last else []
                img = row.group("img"); repo, public, local = image_parts(img)
                first_name = names[0].group(0) if names else None
                if local and not is_token(img):
                    add_local_image(pos + row.start("img"), repo, first_name)
                for nm in names:
                    n = nm.group(0)
                    if public and n == repo.split("/")[-1]: continue     # open-webui ↔ ghcr.io/open-webui/open-webui
                    add_container(pos + last.start(1) + nm.start(), n)
                pos += len(line) + 1
        for h in DOCKER_IMAGES_HDR.finditer(text):                    # docker images
            pos = h.end() + 1
            for line in text[pos:].split("\n"):
                row = re.match(r"(?P<repo>\S+)\s+\S+\s+[0-9a-f]{12}\s", line)
                if not row: break
                repo, public, local = image_parts(row.group("repo"))
                if local and repo != "<none>": add_local_image(pos, repo)
                pos += len(line) + 1

        # --- 8) özel terimler ---
        for term in sorted([t for t in self.custom_terms if t], key=len, reverse=True):
            for m in re.finditer(r"(?<![A-Za-z0-9_])" + re.escape(term) + r"(?![A-Za-z0-9_])", text, re.I):
                add(m.start(), m.end(), m.group(0), "custom")

        # --- 9) tarihler: maskelenmeseler bile IP / hostname sanılmalarını engeller ---
        for m in DATE_RE.finditer(text):
            found.append((m.start(), m.end(), m.group(0), "date", None, PRIO["date"], False))

        # --- 10) genel kalıplar ---
        for typ in ("email", "domain", "ipv6", "ipv4", "mac"):
            if not on(typ): continue
            for m in PAT[typ].finditer(text):
                v = m.group(0)
                if not v: continue
                if typ == "domain" and not _valid_domain(v): continue
                if typ == "email" and _benign_domain(v.split("@", 1)[1]): continue   # git@github.com
                if typ in ("ipv4", "ipv6") and _benign_ip(v): continue
                if typ in ("ipv4", "ipv6"):
                    pm = re.match(r"/\d{1,3}", text[m.end():m.end() + 4])
                    if pm and (v + pm.group(0)) in WELL_KNOWN_NETS: continue
                if typ == "mac" and _benign_mac(v): continue
                add(m.start(), m.end(), v, typ)
        protected = [(m.start(), m.end()) for m in TOKEN_RE.finditer(text)]
        if on("hostname"):
            seen = set()
            for m in KW_RE.finditer(text):
                name = m.group(1); s = m.start() + m.group(0).rfind(name)
                if (s, s + len(name)) not in seen and _host_label_ok(name):
                    seen.add((s, s + len(name)))
                    add(s, s + len(name), name, "hostname", prop=not re.search(r"\d", name))
            ends = {pe for _, pe in protected}
            for m in TOK_RE.finditer(text):
                t = m.group(0)
                if (m.start(), m.end()) in seen: continue
                if re.match(r"\.\d", text[m.end():m.end() + 2]): continue        # sürüm: xxx-7.4.12
                if re.match(r"\"\s*:", text[m.end():m.end() + 3]): continue      # JSON anahtarı
                if re.fullmatch(r"[0-9a-fA-F]{1,4}", t) and text[m.end():m.end() + 1] == ":": continue  # ff02::1
                if m.start() - 1 in ends and text[m.start() - 1] in "-_": continue  # PROJE_1-web-1
                if _looks_like_host(t): add(m.start(), m.end(), t, "hostname")
        if on("config"):
            values = dict(conn_dbs)
            for rx in (CFG_FREE_RE, CFG_STRICT_RE):
                for m in rx.finditer(text):
                    val = re.sub(r"[:.]+$", "", m.group(2) or "")
                    if len(val) >= 2 and val.lower() not in CFG_STOP and not is_token(val):
                        values.setdefault(val, _cfg_prefix(m.group(1)))
            for m in CFG_ENV_RE.finditer(text):
                val = re.sub(r"[:.]+$", "", m.group("v"))
                if len(val) >= 2 and val.lower() not in CFG_STOP and not is_token(val):
                    values.setdefault(val, _cfg_prefix(m.group("key")))
            for v, p in values.items():
                for m in _bounded(v).finditer(text):
                    add(m.start(), m.end(), v, "config", p)

        # --- 11) öğrenilmiş adları metnin her yerinde yay (bu mesaj + defterdeki önceki mesajlar) ---
        spread = dict(learned)
        for f in found:
            if f[3] == "domain":
                for lbl in _split_domain(f[2])[0]:
                    if _label_spreads(lbl): spread.setdefault(lbl, ("hostname", None))
        for e in self.entries:
            if e.get("prop") and not e.get("secret"):
                spread.setdefault(e["real"], (e["type"], None))
        for v, (typ, p) in spread.items():
            if len(v) < 4 or v.lower() in COMMON_WORDS or v.lower() in SYSTEM_USERS: continue
            if not on(typ) or v not in text: continue
            for m in _spread_re(v).finditer(text):
                add(m.start(), m.end(), v, typ, p, prio=P_SPREAD)

        # mevcut etiketlerin (IP_PRIV_1, HOST_2…) üstüne düşen hiçbir şey maskelenmez
        found = [f for f in found if not any(f[0] < pe and ps < f[1] for ps, pe in protected)]

        found.sort(key=lambda x: (x[0], -x[5], -(x[1] - x[0])))
        chosen = []; last_end = -1
        for f in found:
            if f[0] >= last_end:
                chosen.append(f); last_end = f[1]
        if not opts.get("date"):
            chosen = [c for c in chosen if c[3] != "date"]    # tanındı, korundu, ama maskelenmez
        return [(s, e, v, t, p, pr) for s, e, v, t, p, _, pr in chosen]

    # ---- genel API ----
    def anonymize(self, text, opts=None):
        with self.lock:
            matches = self._collect(text, opts)
            out = []; i = 0
            for s, e, v, t, p, pr in matches:
                out.append(text[i:s]); out.append(self._get_fake(v, t, p, pr)); i = e
            out.append(text[i:])
            if matches: self.save()
            return "".join(out), len(matches)

    def analyze(self, text, opts=None):
        """(bilinen_etiket_sayısı, yeni_hassas_değer_sayısı) — metin AI cevabı mı, yeni log mu?"""
        with self.lock:
            known = sum(1 for m in TOKEN_RE.finditer(text) if m.group(0) in self.tok)
            return known, len(self._collect(text, opts))

    def classify(self, text, opts=None):
        """'restore' yalnızca metinde bilinen etiketler baskınsa (AI cevabı); aksi halde 'anon'."""
        known, new = self.analyze(text, opts)
        kind = "restore" if known > 0 and known >= new else "anon"
        return kind, known, new

    def legacy_count(self):
        """Eski sürümün gerçekçi sahte değerleri (etiket olmayanlar)."""
        return sum(1 for e in self.entries if not is_token(e["fake"]))

    def _guard(self, typ):
        if typ == "ipv4": return (r"(?<![0-9.])", r"(?![0-9.])")
        if typ in ("ipv6","mac"): return (r"(?<![0-9A-Fa-f:.\-])", r"(?![0-9A-Fa-f:.\-])")
        return (r"(?<![A-Za-z0-9._\-\/])", r"(?![A-Za-z0-9._\-\/])")

    def restore(self, text):
        """Ters eşleme: metindeki bilinen etiketleri gerçek değerlere çevirir."""
        with self.lock:
            count = [0]
            def sub(m):
                real = self.tok.get(m.group(0))
                if real is None: return m.group(0)
                count[0] += 1; return real
            text = TOKEN_RE.sub(sub, text)
            # eski sürümden kalan gerçekçi sahteler (geriye dönük uyumluluk)
            for p in sorted((e for e in self.entries if not is_token(e["fake"])), key=lambda x: -len(x["fake"])):
                lb, la = self._guard(p["type"])
                text, n = re.subn(lb + re.escape(p["fake"]) + la, lambda _m, r=p["real"]: r, text)
                count[0] += n
            return text, count[0]

    def import_entries(self, items):
        """Dışa aktarılmış defteri ekler. Çakışan etiketler atlanır. Dönüş: eklenen sayısı."""
        added = 0
        with self.lock:
            for e in items:
                real, fake = e.get("real"), e.get("fake")
                if not real or not fake or e.get("secret") or real in self.real_to_fake or fake in self.tok:
                    continue
                ne = {"real": real, "fake": fake, "type": e.get("type", "custom")}
                if e.get("prop"): ne["prop"] = True
                self.real_to_fake[real] = fake; self.tok[fake] = real
                self.entries.append(ne); self.by_real[real] = ne
                if is_token(fake):
                    p, n = fake.rsplit("_", 1)
                    self.counters[p] = max(self.counters.get(p, 0), int(n))
                added += 1
            self.save()
        return added

    def export_entries(self):
        return [e for e in self.entries if not e.get("secret")]

    def set_custom(self, terms):
        with self.lock:
            self.custom_terms = terms; self.save()

    def save(self):
        if not self.store: return
        try:
            with open(self.store, "w", encoding="utf-8") as f:
                json.dump({"version": 3, "entries": self.export_entries(), "counters": self.counters,
                           "custom_terms": self.custom_terms}, f, ensure_ascii=False, indent=1)
        except Exception as ex:
            print("Kaydetme hatası:", ex)

    def load(self):
        if not self.store or not os.path.exists(self.store): return
        try:
            with open(self.store, encoding="utf-8") as f: d = json.load(f)
            self.custom_terms = d.get("custom_terms", [])
            self.counters = {k: int(v) for k, v in d.get("counters", {}).items()}
            for e in d.get("entries", []):
                if e.get("secret") or not e.get("real") or not e.get("fake"): continue
                ne = {"real": e["real"], "fake": e["fake"], "type": e.get("type", "custom")}
                if e.get("prop"): ne["prop"] = True
                self.entries.append(ne)
                if e["real"] not in self.real_to_fake:
                    self.real_to_fake[e["real"]] = e["fake"]; self.by_real[e["real"]] = ne
                if is_token(e["fake"]):
                    self.tok[e["fake"]] = e["real"]
                    p, n = e["fake"].rsplit("_", 1)
                    self.counters[p] = max(self.counters.get(p, 0), int(n))
        except Exception as ex:
            print("Yükleme hatası:", ex)

    def clear(self):
        with self.lock:
            self._reset(); self.save()


# =====================================================================
#  UYGULAMA (kutu akışı + isteğe bağlı pano/kısayol)
# =====================================================================

def _norm(s):
    """Pano karşılaştırması için: Windows \\r\\n, sondaki boşluk/NUL farkları yok sayılır."""
    return (s or "").replace("\r\n", "\n").replace("\r", "\n").rstrip("\x00").strip()


def _clipboard_counter():
    """Her Ctrl+C'de artan işletim sistemi sayacı — içerik AYNI olsa bile yeni kopyayı yakalar.
    Windows: GetClipboardSequenceNumber · macOS: NSPasteboard.changeCount · diğerleri: None"""
    if sys.platform == "win32":
        try:
            import ctypes
            fn = ctypes.windll.user32.GetClipboardSequenceNumber
            fn.restype = ctypes.c_uint32
            fn()
            return lambda: int(fn())
        except Exception:
            return None
    if sys.platform == "darwin":
        try:
            from AppKit import NSPasteboard
            pb = NSPasteboard.generalPasteboard()
            return lambda: int(pb.changeCount())
        except Exception:
            return None
    return _x11_counter()


def _x11_counter():
    """Linux/X11: XFixes ile pano sahibi değişimlerini sayar — her Ctrl+C bir olaydır,
    içerik aynı olsa bile. python-xlib, pynput ile birlikte zaten kurulu gelir."""
    if not os.environ.get("DISPLAY"):
        return None
    try:
        import Xlib.display
        from Xlib.ext import xfixes
        disp = Xlib.display.Display()
        if not disp.has_extension("XFIXES"):
            return None
        disp.xfixes_query_version()
        clip = disp.intern_atom("CLIPBOARD")
        disp.xfixes_select_selection_input(disp.screen().root, clip,
                                           xfixes.XFixesSetSelectionOwnerNotifyMask)
        disp.flush()
    except Exception:
        return None
    state = {"n": 0}
    def listen():
        while True:
            try:
                ev = disp.next_event()
                if (ev.type, getattr(ev, "sub_code", None)) == disp.extension_event.SetSelectionOwnerNotify:
                    state["n"] += 1
            except Exception:
                return
    threading.Thread(target=listen, daemon=True).start()
    return lambda: state["n"]

ECHO_GRACE = 1.0   # sn — bizim yazdığımız metin bu süre içinde tekrar belirirse (RDP vb.) yankı sayılır


class Agent:
    def __init__(self, counter="auto"):
        self.mapper = Mapper()
        self.auto = False
        self.mode = "smart"               # "smart": log→maskele, AI cevabı→geri çevir | "mask": hep maskele
        self.counter = _clipboard_counter() if counter == "auto" else counter
        self.last_seq = None              # en son işlenen pano sayacı
        self.seen_norm = None             # panoda en son gördüğümüz (normalize)
        self.written_norm = None          # panoya en son BİZİM yazdığımız (normalize)
        self.written_at = 0.0
        self.running = True
        self.gui = None
        self.get_opts = lambda: None      # GUI geçerli kategori seçimini verir
        self.notify = lambda title, msg: None   # GUI tepsi bildirimini bağlar

    def _seq(self):
        if not self.counter: return None
        try: return self.counter()
        except Exception: return None

    def sync_now(self):
        """Panonun şu anki halini 'görüldü' say (açılışta ve kendi yazdıklarımızdan sonra)."""
        self.last_seq = self._seq()
        try: self.seen_norm = _norm(pyperclip.paste()) if pyperclip else None
        except Exception: pass

    def mark_written(self, text):
        """Panoya uygulamanın kendisi yazdı (yazma işleminden SONRA çağır) — yeni kopya sayılmasın."""
        self.written_norm = _norm(text); self.seen_norm = self.written_norm
        self.written_at = time.time()
        self.last_seq = self._seq()

    def _write(self, text):
        pyperclip.copy(text); self.mark_written(text)

    def clip_anonymize(self):
        if not pyperclip: return self._flash("pyperclip yok.")
        txt = pyperclip.paste()
        if not txt.strip(): return self._flash("Pano boş.")
        masked, n = self.mapper.anonymize(txt, self.get_opts())
        if masked != txt:
            self._write(masked)
            self._flash("Panoda anonimleştirildi: %d öğe" % n); self._refresh()
        else:
            self._flash("Panoda maskelenecek bir şey yok.")

    def clip_restore(self):
        if not pyperclip: return self._flash("pyperclip yok.")
        txt = pyperclip.paste()
        if not txt.strip(): return self._flash("Pano boş.")
        restored, n = self.mapper.restore(txt)
        if restored != txt:
            self._write(restored)
            self._flash("Panoda geri çevrildi: %d değer" % n)
        else:
            self._flash("Panoda defterdeki etiketlerden biri yok.")

    def toggle_auto(self):
        self.auto = not self.auto
        self._flash("Oto-izle: " + ("AÇIK" if self.auto else "KAPALI")); self._refresh()

    def handle_copy(self, cur):
        """Yeni bir kopyayı işler. Dönüş: (kind, çıktı, adet, açıklama)."""
        opts = self.get_opts()
        if self.mode == "smart":
            kind, fakes, news = self.mapper.classify(cur, opts)
        else:
            kind, fakes, news = "anon", 0, 0
        if kind == "restore":
            out, n = self.mapper.restore(cur)
            why = "AI cevabı algılandı (%d etiket)" % fakes
        else:
            out, n = self.mapper.anonymize(cur, opts)
            why = "log algılandı" if self.mode == "smart" else "sadece-maskele modu"
        return kind, out, n, why

    def _poll(self):
        """Yeni bir kopyalama olayı varsa panodaki metni döndürür, yoksa None."""
        seq = self._seq()
        if seq is not None and sys.platform.startswith("linux"):
            # Linux: X11 sayacı + içerik kontrolü birlikte (Wayland'da sayaç olay kaçırabilir)
            seq_changed = seq != self.last_seq
            self.last_seq = seq
            try: cur = pyperclip.paste()
            except Exception: return None
            ncur = _norm(cur)
            if not seq_changed and ncur == self.seen_norm: return None
            self.seen_norm = ncur
            if ncur == self.written_norm:
                # kendi yazdığımız: yalnızca kullanıcı sonradan AYNI metni tekrar kopyaladıysa işle
                if not seq_changed or time.time() - self.written_at < ECHO_GRACE: return None
            return cur
        if seq is not None:
            # Sayaç modu: içerik aynı olsa da her Ctrl+C yeni olaydır.
            if seq == self.last_seq: return None
            self.last_seq = seq
            try: cur = pyperclip.paste()
            except Exception: return None
            ncur = _norm(cur)
            # Kendi yazdığımızın gecikmeli yankısı (RDP pano eşitlemesi vb.) → atla
            if ncur == self.written_norm and time.time() - self.written_at < ECHO_GRACE:
                return None
            self.seen_norm = ncur
            return cur
        # Sayaç yok (Linux): içerik değişimine bak — aynı metni tekrar kopyalamak algılanamaz
        try: cur = pyperclip.paste()
        except Exception: return None
        ncur = _norm(cur)
        if ncur == self.seen_norm: return None
        self.seen_norm = ncur
        if ncur == self.written_norm: return None
        return cur

    def watch_loop(self):
        while self.running:
            if pyperclip:
                cur = self._poll()
                if cur is not None and self.auto and _norm(cur):
                    try:
                        kind, out, n, why = self.handle_copy(cur)
                    except Exception as ex:
                        self._flash("Hata: %s" % ex); time.sleep(0.3); continue
                    if out != cur:
                        self._write(out)
                        self.notify("Anonim Ajan",
                                    ("↩ Geri çevrildi: %d değer" % n) if kind == "restore"
                                    else ("🛡 Maskelendi: %d öğe" % n))
                    if self.gui: self.gui.capture(kind, cur, out, n, why)
                    self._refresh()
            time.sleep(0.25)

    def _flash(self, msg):
        print("•", msg)
        if self.gui: self.gui.flash(msg)
    def _refresh(self):
        if self.gui: self.gui.refresh()
    def stop(self): self.running = False


# =====================================================================
#  SİMGE — kalkan + sansür çubukları (exe, pencere, görev çubuğu, tepsi)
# =====================================================================
try:
    from PIL import Image as PILImage, ImageDraw as PILDraw, ImageFilter as PILFilter, ImageChops as PILChops
except Exception:
    PILImage = None

def _bezier(p0, p1, p2, p3, n=48):
    pts = []
    for i in range(n + 1):
        t = i / n; u = 1 - t
        pts.append((u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0],
                    u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1]))
    return pts

def _shield(cx, top, w, h):
    L, R, T = cx - w/2, cx + w/2, top
    r = w * 0.13
    pts = []
    pts += _bezier((L, T + r), (L, T), (L, T), (L + r, T), 12)
    pts += _bezier((R - r, T), (R, T), (R, T), (R, T + r), 12)
    pts += _bezier((R, T + h*0.46), (R, T + h*0.80), (cx + w*0.20, T + h*0.93), (cx, T + h))
    pts += _bezier((cx, T + h), (cx - w*0.20, T + h*0.93), (L, T + h*0.80), (L, T + h*0.46))
    return pts

_ICON_CACHE = {}
def app_icon(size=256):
    """Uygulama simgesi (RGBA). 1024'lük tuval üzerinde 2x süper örneklemeyle çizilir."""
    if size in _ICON_CACHE: return _ICON_CACHE[size]
    S = 2048 if size > 64 else 1024
    k = S / 1024
    v = PILImage.linear_gradient("L").resize((S, S))
    grad = PILChops.add(v, v.rotate(90), scale=2.0)                      # sol üst → sağ alt
    tile = PILImage.composite(PILImage.new("RGBA", (S, S), (24, 74, 168, 255)),
                              PILImage.new("RGBA", (S, S), (43, 212, 168, 255)), grad)
    mask = PILImage.new("L", (S, S), 0)
    PILDraw.Draw(mask).rounded_rectangle([int(40*k), int(40*k), int(984*k), int(984*k)], radius=int(220*k), fill=255)
    img = PILImage.new("RGBA", (S, S), (0, 0, 0, 0)); img.paste(tile, (0, 0), mask)
    shadow = PILImage.new("L", (S, S), 0)
    PILDraw.Draw(shadow).polygon([(x*k, (y+26)*k) for x, y in _shield(512, 210, 560, 640)], fill=110)
    shadow = PILChops.multiply(shadow.filter(PILFilter.GaussianBlur(28*k)), mask)
    img = PILImage.composite(PILImage.new("RGBA", (S, S), (6, 20, 40, 255)), img, shadow)
    d = PILDraw.Draw(img)
    d.polygon([(x*k, y*k) for x, y in _shield(512, 210, 560, 640)], fill=(244, 252, 250, 255))
    for x0, y0, x1, col in ((338, 360, 686, (14, 42, 59, 255)),
                            (338, 470, 600, (43, 212, 168, 255)),
                            (338, 580, 650, (14, 42, 59, 255))):
        d.rounded_rectangle([x0*k, y0*k, x1*k, (y0+64)*k], radius=int(32*k), fill=col)
    out = img.resize((size, size), PILImage.LANCZOS)
    _ICON_CACHE[size] = out
    return out

def export_icon(path):
    """Simgeyi dosyaya yazar: .ico (16–256 her boyut ayrı çizilir) ya da .png (512)."""
    if PILImage is None:
        raise SystemExit("Simge için Pillow gerekli: pip install Pillow")
    if path.lower().endswith(".ico"):
        sizes = (16, 24, 32, 48, 64, 128, 256)
        frames = [app_icon(s) for s in sizes]
        frames[-1].save(path, format="ICO", sizes=[(s, s) for s in sizes], append_images=frames[:-1])
    else:
        app_icon(512).save(path)
    return path


# =====================================================================
#  ARAYÜZ
# =====================================================================

def run_gui(agent):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, font as tkfont
    try:
        import customtkinter as ctk
    except ImportError:
        try:
            r = tk.Tk(); r.withdraw()
            messagebox.showerror("Anonim Ajan", "Arayüz paketi eksik.\n\npip install customtkinter")
        except Exception:
            pass
        raise SystemExit("customtkinter eksik: pip install customtkinter")

    if sys.platform == "win32":
        try:   # script olarak çalışırken görev çubuğunda Python simgesi yerine bizimki görünsün
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AnonimAjan.App")
        except Exception:
            pass

    ctk.set_appearance_mode("dark")

    # ---------- renk sistemi ----------
    BG      = "#0B0E14"   # pencere
    SURF    = "#121722"   # kart
    SURF2   = "#182030"   # yükseltilmiş / üzerine gelince
    INK     = "#0D121A"   # metin kutusu
    BORDER  = "#232C3B"
    BORDER2 = "#33405A"
    TEXT    = "#E8EDF5"
    MUTED   = "#8C97AB"
    FAINT   = "#5D687C"
    TEAL    = "#2BD4A8";  TEAL_H = "#55E3C0";  TEAL_INK = "#04261E";  TEAL_BG = "#10302A";  TEAL_LINE = "#1F5F50"
    CORAL   = "#FF8A7A";  CORAL_BG = "#3A1F1D";  CORAL_LINE = "#5A2E2A"

    root = ctk.CTk(fg_color=BG)
    root.title("Anonim Ajan")
    try:
        sc = ctk.ScalingTracker.get_window_scaling(root)
        max_h = int(root.winfo_screenheight() / sc) - 90
    except Exception:
        sc, max_h = 1.0, 820
    root.geometry("1000x%d" % min(800, max_h)); root.minsize(840, min(640, max_h))

    fams = set(tkfont.families(root))
    def pick(*names):
        return next((n for n in names if n in fams), None)
    UI   = pick("Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text", "Helvetica Neue",
                "Ubuntu", "Cantarell", "Noto Sans", "DejaVu Sans") or "TkDefaultFont"
    UI_D = pick("Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI", "Inter", "SF Pro Display",
                "Ubuntu", "Cantarell", "Noto Sans", "DejaVu Sans") or UI
    MONO = pick("Cascadia Mono", "Cascadia Code", "JetBrains Mono", "SF Mono", "Consolas",
                "Ubuntu Mono", "DejaVu Sans Mono") or "TkFixedFont"
    def F(size, weight="normal", family=None):
        return ctk.CTkFont(family=family or UI, size=size, weight=weight)

    # ---------- pencere simgesi ----------
    ico_path = None
    if PILImage is not None:
        try:
            if sys.platform == "win32":
                import tempfile
                ico_path = export_icon(os.path.join(tempfile.gettempdir(), "anonim_ajan.ico"))
                root.iconbitmap(ico_path)
            else:
                from PIL import ImageTk
                root._icon_ref = ImageTk.PhotoImage(app_icon(256))
                root.iconphoto(True, root._icon_ref)
        except Exception:
            pass

    def put_clipboard(t):
        """Uygulama içi 'Kopyala': önce yaz, sonra işaretle — izleyici bunu kullanıcı kopyası sanmasın."""
        if pyperclip:
            agent._write(t)
        else:
            root.clipboard_clear(); root.clipboard_append(t); root.update(); agent.mark_written(t)

    # ---------- yapı taşları ----------
    def card(master):
        return ctk.CTkFrame(master, fg_color=SURF, corner_radius=14, border_width=1, border_color=BORDER)

    def clear(master):
        return ctk.CTkFrame(master, fg_color="transparent")

    BTN = {
        "primary":   dict(fg_color=TEAL, hover_color=TEAL_H, text_color=TEAL_INK, border_width=0),
        "secondary": dict(fg_color=SURF2, hover_color="#212B3D", text_color=TEXT, border_width=1, border_color=BORDER),
        "ghost":     dict(fg_color="transparent", hover_color=SURF2, text_color=MUTED, border_width=0),
        "outline":   dict(fg_color="transparent", hover_color=TEAL_BG, text_color=TEAL, border_width=1, border_color=TEAL_LINE),
        "danger":    dict(fg_color="transparent", hover_color=CORAL_BG, text_color=CORAL, border_width=1, border_color=CORAL_LINE),
    }
    def btn(master, text, cmd, kind="secondary", width=110, height=34, size=12):
        return ctk.CTkButton(master, text=text, command=cmd, width=width, height=height, corner_radius=9,
                             font=F(size if kind != "primary" else size + 1, "bold"), **BTN[kind])

    def textbox(master):
        t = ctk.CTkTextbox(master, height=90, fg_color=INK, border_width=1, border_color=BORDER, corner_radius=10,
                           text_color=TEXT, font=ctk.CTkFont(family=MONO, size=12), wrap="word",
                           border_spacing=10, scrollbar_button_color=BORDER, scrollbar_button_hover_color=BORDER2)
        t.bind("<FocusIn>",  lambda e: t.configure(border_color=TEAL_LINE), add=True)
        t.bind("<FocusOut>", lambda e: t.configure(border_color=BORDER), add=True)
        return t

    def set_text(tb, s):
        tb.delete("1.0", "end"); tb.insert("1.0", s)

    def highlight(tb, text, pairs, tag):
        """pairs: [(değer, tür)] — metinde geçen her değeri renkli etiketle işaretle."""
        for v, typ in pairs:
            if not v or v not in text: continue
            if typ in ("ipv4", "ipv6", "mac"):
                lb, la = agent.mapper._guard(typ)
            else:
                lb, la = r"(?<![A-Za-z0-9_\-])", r"(?![A-Za-z0-9_\-])"
            for m in re.finditer(lb + re.escape(v) + la, text):
                tb.tag_add(tag, "1.0+%dc" % m.start(), "1.0+%dc" % m.end())

    def show_fakes(tb, text):
        set_text(tb, text)
        for m in TOKEN_RE.finditer(text):
            tb.tag_add("fake", "1.0+%dc" % m.start(), "1.0+%dc" % m.end())

    def show_reals(tb, text):
        set_text(tb, text)
        highlight(tb, text, [(e["real"], e["type"]) for e in agent.mapper.entries], "real")

    # ---------- kısayollar penceresi ----------
    def show_hotkeys(*_):
        win = ctk.CTkToplevel(root, fg_color=BG)
        win.title("Kısayollar"); win.resizable(False, False); win.transient(root)
        if ico_path:
            win.after(250, lambda: win.iconbitmap(ico_path))
        body = clear(win); body.pack(fill="both", expand=True, padx=26, pady=24)
        ctk.CTkLabel(body, text="Klavye kısayolları", font=F(17, "bold", UI_D), text_color=TEXT,
                     anchor="w").pack(anchor="w", pady=(0, 14))
        rows = [(("Ctrl", "Alt", "A"), "Panodaki metni anonimleştir"),
                (("Ctrl", "Alt", "R"), "Panodaki metni geri çevir"),
                (("Ctrl", "Alt", "T"), "Oto-izlemeyi aç / kapat"),
                (("Ctrl", "Enter"),    "Kutudaki metni işle"),
                (("Ctrl", "Q"),        "Uygulamadan çık")]
        grid = clear(body); grid.pack(fill="x")
        for row, (keys, desc) in enumerate(rows):
            kf = clear(grid); kf.grid(row=row, column=0, sticky="w", pady=4)
            for i, kname in enumerate(keys):
                if i: ctk.CTkLabel(kf, text="+", text_color=FAINT, font=F(11), width=14).pack(side="left")
                ctk.CTkLabel(kf, text=" %s " % kname, font=F(11, "bold"), text_color=TEXT, fg_color=SURF2,
                             corner_radius=6, height=26).pack(side="left")
            ctk.CTkLabel(grid, text=desc, font=F(13), text_color=MUTED, anchor="w").grid(
                row=row, column=1, sticky="w", padx=(18, 0))
        note = ("Oto-izle açıkken kısayola gerek yok: log kopyala → maskelenir, "
                "AI cevabını kopyala → gerçek değerlere döner.")
        if not keyboard:
            note = "Global kısayollar kapalı: pynput paketi yok (pip install pynput). " + note
        ctk.CTkLabel(body, text=note, font=F(12), text_color=(CORAL if not keyboard else FAINT),
                     wraplength=400, justify="left", anchor="w").pack(anchor="w", pady=(16, 18))
        btn(body, "Tamam", win.destroy, "primary", width=120, height=36).pack(anchor="e")
        win.update_idletasks()
        x = root.winfo_rootx() + (root.winfo_width() - win.winfo_reqwidth()) // 2
        y = root.winfo_rooty() + (root.winfo_height() - win.winfo_reqheight()) // 3
        win.geometry("+%d+%d" % (max(x, 0), max(y, 0)))
        win.lift(); win.focus_force()

    # ---------- üst bölüm ----------
    header = clear(root); header.pack(fill="x", padx=26, pady=(22, 14))
    if PILImage is not None:
        try:
            logo = ctk.CTkImage(light_image=app_icon(128), dark_image=app_icon(128), size=(42, 42))
            ctk.CTkLabel(header, text="", image=logo).pack(side="left")
        except Exception as ex:          # logo çizilemezse uygulama logosuz devam etsin
            print("Logo gösterilemedi:", ex)
    tb_ = clear(header); tb_.pack(side="left", padx=(12, 0))
    ctk.CTkLabel(tb_, text="Anonim Ajan", font=F(21, "bold", UI_D), text_color=TEXT, anchor="w").pack(anchor="w")
    ctk.CTkLabel(tb_, text="Log ve config verilerini AI'a göndermeden önce maskeler",
                 font=F(12), text_color=MUTED, anchor="w").pack(anchor="w")
    btn(header, "Kısayollar", show_hotkeys, "ghost", width=96, height=32).pack(side="right", padx=(10, 0))

    MODES = {"Akıllı": "smart", "Sadece maskele": "mask"}
    def on_mode(value):
        agent.mode = MODES.get(value, "smart"); gui.refresh()
        gui.flash("Yön: Akıllı — log maskelenir, AI cevabı geri çevrilir" if agent.mode == "smart"
                  else "Yön: Sadece maskele — her kopya maskelenir")
    mode_seg = ctk.CTkSegmentedButton(header, values=list(MODES), command=on_mode, height=32,
                                      font=F(12, "bold"), fg_color=SURF, selected_color="#26324A",
                                      selected_hover_color="#2C3A55", unselected_color=SURF,
                                      unselected_hover_color=SURF2, text_color=TEXT, corner_radius=9)
    mode_seg.set("Akıllı" if agent.mode == "smart" else "Sadece maskele")
    mode_seg.pack(side="right")
    ctk.CTkLabel(header, text="Yön", font=F(12), text_color=FAINT).pack(side="right", padx=(0, 10))
    def toggle_mode():
        mode_seg.set("Sadece maskele" if agent.mode == "smart" else "Akıllı")
        on_mode(mode_seg.get())

    # ---------- durum kartı ----------
    hero = card(root); hero.pack(fill="x", padx=26)
    top = clear(hero); top.pack(fill="x", padx=20, pady=(16, 0))
    dot = ctk.CTkLabel(top, text="●", font=F(20), text_color=TEAL, width=22); dot.pack(side="left", anchor="n")
    tbox = clear(top); tbox.pack(side="left", padx=(8, 0), fill="x", expand=True)
    hero_title = ctk.CTkLabel(tbox, text="", font=F(16, "bold", UI_D), text_color=TEXT, anchor="w")
    hero_title.pack(anchor="w")
    hero_sub = ctk.CTkLabel(tbox, text="", font=F(12), text_color=MUTED, anchor="w", justify="left")
    hero_sub.pack(anchor="w", fill="x")

    auto_var = tk.BooleanVar(value=False)
    def set_auto(value, quiet=False):
        agent.auto = bool(value)
        def _():
            if auto_var.get() != agent.auto: auto_var.set(agent.auto)
            gui.refresh()
            if not quiet: gui.flash("Oto-izle " + ("açık" if agent.auto else "kapalı"))
        root.after(0, _)
    agent.set_auto = set_auto
    auto_sw = ctk.CTkSwitch(top, text="Oto-izle", variable=auto_var, onvalue=True, offvalue=False,
                            command=lambda: set_auto(auto_var.get()), switch_width=54, switch_height=28,
                            progress_color=TEAL, fg_color=BORDER2, button_color="#F2F6FB",
                            button_hover_color="#FFFFFF", font=F(13, "bold"), text_color=TEXT)
    auto_sw.pack(side="right")

    ctk.CTkFrame(hero, height=1, fg_color=BORDER).pack(fill="x", padx=20, pady=(14, 0))
    hb = clear(hero); hb.pack(fill="x", padx=20, pady=(10, 14))
    caps_box = clear(hb); caps_box.pack(side="right")
    last_lbl = ctk.CTkLabel(hb, text="Hazır", font=F(12), text_color=MUTED, anchor="w")
    last_lbl.pack(side="left", fill="x", expand=True)

    def set_caps(items):
        for w in caps_box.winfo_children(): w.destroy()
        for name, ok in items:
            ctk.CTkLabel(caps_box, text=("  ✓  %s  " if ok else "  ✕  %s  ") % name, height=24, corner_radius=12,
                         font=F(11, "bold"), fg_color=(TEAL_BG if ok else SURF2),
                         text_color=(TEAL if ok else FAINT)).pack(side="left", padx=(6, 0))

    # ---------- sekmeler ----------
    tabbar = clear(root); tabbar.pack(fill="x", padx=26, pady=(18, 12))
    PAGES = ["Anonimleştir", "Geri Çevir", "Defter"]
    tabs = ctk.CTkSegmentedButton(tabbar, values=PAGES, height=38, font=F(13, "bold"),
                                  fg_color=SURF, selected_color="#26324A", selected_hover_color="#2C3A55",
                                  unselected_color=SURF, unselected_hover_color=SURF2, text_color=TEXT,
                                  corner_radius=10, command=lambda v: show_page(v))
    tabs.pack(side="left")
    ledger_badge = ctk.CTkLabel(tabbar, text="", font=F(12), text_color=FAINT)
    ledger_badge.pack(side="left", padx=(12, 0))

    content = clear(root); content.pack(fill="both", expand=True, padx=26, pady=(0, 22))
    content.grid_rowconfigure(0, weight=1); content.grid_columnconfigure(0, weight=1)
    pages = {}
    for name in PAGES:
        f = clear(content); f.grid(row=0, column=0, sticky="nsew"); pages[name] = f
    def show_page(name):
        pages[name].tkraise()
        if tabs.get() != name: tabs.set(name)

    def io_card(master, title, hint):
        c = card(master)
        h = clear(c); h.pack(fill="x", padx=16, pady=(12, 8))
        ctk.CTkLabel(h, text=title, font=F(12, "bold"), text_color=TEXT, anchor="w").pack(side="left")
        ctk.CTkLabel(h, text="  ·  " + hint, font=F(12), text_color=FAINT, anchor="w").pack(side="left")
        t = textbox(c); t.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        return c, h, t

    # ===== Anonimleştir =====
    pa = pages["Anonimleştir"]
    pa.grid_columnconfigure(0, weight=1)
    pa.grid_rowconfigure(1, weight=1, uniform="io"); pa.grid_rowconfigure(3, weight=1, uniform="io")
    chiprow = clear(pa); chiprow.grid(row=0, column=0, sticky="ew", pady=(0, 10))
    CHIP_GROUPS = [("Ağ", ("ipv4", "ipv6", "domain", "hostname", "mac", "iface")),
                   ("Kimlik ve gizli", ("user", "email", "container", "config", "secret", "date", "custom"))]
    optvars = {}
    def make_chip(chips, t):
        v = tk.BooleanVar(value=t not in DEFAULT_OFF); optvars[t] = v
        b = ctk.CTkButton(chips, text=LABELS[t], width=10, height=30, corner_radius=15, font=F(11, "bold"),
                          border_width=1)
        def paint():
            on = v.get()
            b.configure(fg_color=(TEAL_BG if on else "transparent"), hover_color=(TEAL_LINE if on else SURF2),
                        border_color=(TEAL_LINE if on else BORDER), text_color=(TEAL if on else FAINT))
        b.configure(command=lambda: (v.set(not v.get()), paint()))
        paint(); return b
    for gi, (gname, types_) in enumerate(CHIP_GROUPS):
        row = clear(chiprow); row.pack(fill="x", pady=(0 if gi == 0 else 6, 0))
        ctk.CTkLabel(row, text=gname, font=F(11), text_color=FAINT, width=104, anchor="w").pack(side="left")
        for t in types_:
            make_chip(row, t).pack(side="left", padx=(0, 6))
    def get_opts(): return {t: optvars[t].get() for t in ALL_TYPES}
    agent.get_opts = get_opts

    in_card, in_head, src = io_card(pa, "Giriş", "log, config, hata çıktısı")
    in_card.grid(row=1, column=0, sticky="nsew")
    out_badge = ctk.CTkLabel(in_head, text="", font=F(11, "bold"), height=22, corner_radius=11)

    act1 = clear(pa); act1.grid(row=2, column=0, sticky="ew", pady=12)
    def do_anon():
        agent.mapper.set_custom([s.strip() for s in custom_entry.get().split(",") if s.strip()])
        txt = src.get("1.0", "end-1c")
        if not txt.strip(): return gui.flash("Önce giriş kutusuna bir metin yapıştır.")
        masked, n = agent.mapper.anonymize(txt, get_opts())
        show_fakes(masked_out, masked); gui.refresh(); set_badge(n)
        gui.flash("%d öğe maskelendi — Kopyala ile al." % n if n else "Maskelenecek bir değer bulunamadı.",
                  "ok" if n else "info")
    def copy_masked():
        t = masked_out.get("1.0", "end-1c")
        if not t.strip(): return gui.flash("Kopyalanacak çıktı yok.")
        put_clipboard(t); gui.flash("Maskeli metin panoda — AI'a yapıştırabilirsin.", "ok")
    def clear_in():
        src.delete("1.0", "end"); masked_out.delete("1.0", "end"); set_badge(None); gui.flash("Temizlendi.")
    def set_badge(n):
        if n is None:
            out_badge.pack_forget(); return
        out_badge.configure(text="  %d öğe maskelendi  " % n, fg_color=TEAL_BG, text_color=TEAL)
        out_badge.pack(side="right")
    btn(act1, "Anonimleştir", do_anon, "primary", width=170, height=42).pack(side="left")
    ctk.CTkLabel(act1, text="Ctrl+Enter", font=F(11), text_color=FAINT).pack(side="left", padx=12)
    btn(act1, "Temizle", clear_in, "ghost", width=90, height=34).pack(side="right")
    custom_entry = ctk.CTkEntry(act1, height=34, corner_radius=9, border_width=1, border_color=BORDER,
                                fg_color=INK, text_color=TEXT, font=F(12), width=150,
                                placeholder_text="Özel terimler (firma adı, proje kodu…), virgülle",
                                placeholder_text_color=FAINT)
    custom_entry.pack(side="left", fill="x", expand=True, padx=(8, 12))
    if agent.mapper.custom_terms:
        custom_entry.insert(0, ", ".join(agent.mapper.custom_terms))

    out_card, out_head, masked_out = io_card(pa, "AI'a gidecek metin", "maskeli")
    out_card.grid(row=3, column=0, sticky="nsew")
    btn(out_head, "Kopyala", copy_masked, "outline", width=92, height=30).pack(side="right")
    masked_out.tag_config("fake", background=TEAL_BG, foreground=TEAL)
    src.bind("<Control-Return>", lambda e: (do_anon(), "break")[1], add=True)

    # ===== Geri Çevir =====
    pr = pages["Geri Çevir"]
    pr.grid_columnconfigure(0, weight=1)
    pr.grid_rowconfigure(0, weight=1, uniform="io"); pr.grid_rowconfigure(2, weight=1, uniform="io")
    rin_card, _, reply = io_card(pr, "AI cevabı", "IP_1, HOST_1 gibi etiketler içeren metin")
    rin_card.grid(row=0, column=0, sticky="nsew")
    act2 = clear(pr); act2.grid(row=1, column=0, sticky="ew", pady=12)
    def do_restore():
        txt = reply.get("1.0", "end-1c")
        if not txt.strip(): return gui.flash("Önce AI'ın cevabını yapıştır.")
        restored, n = agent.mapper.restore(txt)
        show_reals(restored_out, restored)
        gui.flash("%d değer geri çevrildi." % n if n else "Bu metinde defterdeki etiketlerden biri yok.",
                  "real" if n else "info")
    def copy_restored():
        t = restored_out.get("1.0", "end-1c")
        if not t.strip(): return gui.flash("Kopyalanacak sonuç yok.")
        put_clipboard(t); gui.flash("Gerçek değerli metin panoda.", "real")
    def clear_rest():
        reply.delete("1.0", "end"); restored_out.delete("1.0", "end"); gui.flash("Temizlendi.")
    btn(act2, "Geri çevir", do_restore, "primary", width=170, height=42).pack(side="left")
    ctk.CTkLabel(act2, text="Ctrl+Enter", font=F(11), text_color=FAINT).pack(side="left", padx=12)
    btn(act2, "Temizle", clear_rest, "ghost", width=90, height=34).pack(side="right")
    rout_card, rout_head, restored_out = io_card(pr, "Gerçek değerler", "editörüne / terminaline")
    rout_card.grid(row=2, column=0, sticky="nsew")
    btn(rout_head, "Kopyala", copy_restored, "danger", width=92, height=30).pack(side="right")
    ctk.CTkLabel(rout_head, text="  AI'a gönderme  ", font=F(11, "bold"), height=22, corner_radius=11,
                 fg_color=CORAL_BG, text_color=CORAL).pack(side="right", padx=(0, 10))
    restored_out.tag_config("real", background=CORAL_BG, foreground=CORAL)
    reply.bind("<Control-Return>", lambda e: (do_restore(), "break")[1], add=True)

    # ===== Defter =====
    pd = pages["Defter"]
    bar = clear(pd); bar.pack(fill="x", pady=(0, 12))
    search = ctk.CTkEntry(bar, height=34, width=320, corner_radius=9, border_width=1,
                          border_color=BORDER, fg_color=INK, text_color=TEXT, font=F(12),
                          placeholder_text="Ara: IP, alan adı, etiket (HOST_3)…", placeholder_text_color=FAINT)
    search.pack(side="left")
    ledcount = ctk.CTkLabel(bar, text="", font=F(12), text_color=FAINT); ledcount.pack(side="left", padx=12)

    def do_export():
        p = filedialog.asksaveasfilename(parent=root, defaultextension=".json", initialfile="anonim-defteri.json")
        if p:
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"version": 2, "entries": agent.mapper.export_entries()}, f, ensure_ascii=False, indent=1)
            gui.flash("Defter dışa aktarıldı (parolalar hariç). Gerçek değerler içerir — paylaşma.", "real")
    def do_import():
        p = filedialog.askopenfilename(parent=root, filetypes=[("JSON", "*.json")])
        if p:
            with open(p, encoding="utf-8") as f: d = json.load(f)
            n = agent.mapper.import_entries(d.get("entries", []))
            gui.refresh(); gui.flash("Defter içe aktarıldı: %d yeni eşleşme." % n, "ok")
    def do_clear():
        if not agent.mapper.entries: return gui.flash("Defter zaten boş.")
        if messagebox.askyesno("Defteri sıfırla",
                               "Tüm eşleşmeler silinsin mi?\n\nDaha önce AI'a gönderdiğin metinlerin cevapları "
                               "artık geri çevrilemez.", parent=root):
            agent.mapper.clear(); gui.refresh(); gui.flash("Defter sıfırlandı.")
    btn(bar, "Sıfırla", do_clear, "danger", width=90).pack(side="right")
    btn(bar, "İçe aktar", do_import, "secondary", width=100).pack(side="right", padx=(0, 8))
    btn(bar, "Dışa aktar", do_export, "secondary", width=100).pack(side="right", padx=(0, 8))

    led_card = card(pd); led_card.pack(fill="both", expand=True)
    style = ttk.Style(root)
    try: style.theme_use("clam")
    except Exception: pass
    style.configure("Ledger.Treeview", background=SURF, fieldbackground=SURF, foreground=TEXT,
                    rowheight=int(34 * sc), borderwidth=0, relief="flat", font=(UI, 11))
    style.configure("Ledger.Treeview.Heading", background=SURF, foreground=FAINT, borderwidth=0,
                    relief="flat", font=(UI, 10, "bold"), padding=(10, 8))
    style.map("Ledger.Treeview", background=[("selected", "#1C2A3D")], foreground=[("selected", TEXT)])
    style.map("Ledger.Treeview.Heading", background=[("active", SURF)], foreground=[("active", MUTED)])
    style.layout("Ledger.Treeview", [("Ledger.Treeview.treearea", {"sticky": "nswe"})])
    tree_wrap = clear(led_card); tree_wrap.pack(fill="both", expand=True, padx=(12, 6), pady=10)
    tree = ttk.Treeview(tree_wrap, columns=("type", "real", "fake"), show="headings", style="Ledger.Treeview")
    for col, title, w in (("type", "TÜR", 90), ("real", "GERÇEK", 360), ("fake", "ETİKET", 360)):
        tree.heading(col, text=title, anchor="w"); tree.column(col, width=w, anchor="w", stretch=(col != "type"))
    tree.tag_configure("odd", background="#141A26")
    vsb = ctk.CTkScrollbar(tree_wrap, command=tree.yview, button_color=BORDER, button_hover_color=BORDER2)
    tree.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y"); tree.pack(side="left", fill="both", expand=True)
    empty_lbl = ctk.CTkLabel(led_card, text="Henüz eşleşme yok.\nBir log kopyaladığında ya da anonimleştirdiğinde burada görünür.",
                             font=F(13), text_color=FAINT, justify="center")
    search.bind("<KeyRelease>", lambda e: gui.refresh())

    # ---------- arayüz köprüsü (izleyici thread'inden güvenle çağrılır) ----------
    TONES = {"ok": TEAL, "real": CORAL, "info": MUTED, "warn": CORAL}
    class Gui:
        def refresh(self):
            def _():
                q = search.get().strip().lower()
                tree.delete(*tree.get_children())
                def shown(e):
                    if e.get("secret"):
                        return "••••••••  (%d karakter · yalnızca bellekte)" % len(e["real"])
                    return e["real"]
                rows = [e for e in agent.mapper.entries
                        if not q or q in shown(e).lower() or q in e["fake"].lower() or q in LABELS.get(e["type"], "").lower()]
                for i, e in enumerate(reversed(rows)):          # en yeni üstte
                    tree.insert("", "end", values=(LABELS.get(e["type"], e["type"]), shown(e), e["fake"]),
                                tags=("odd",) if i % 2 else ())
                total = len(agent.mapper.entries)
                ledcount.configure(text=("%d / %d kayıt" % (len(rows), total)) if q else ("%d kayıt" % total))
                ledger_badge.configure(text=("Defterde %d eşleşme" % total) if total else "")
                if total: empty_lbl.place_forget()
                else: empty_lbl.place(relx=0.5, rely=0.5, anchor="center")
                if auto_var.get() != agent.auto: auto_var.set(agent.auto)
                if agent.auto:
                    dot.configure(text_color=TEAL); hero_title.configure(text="Koruma aktif")
                    hero_sub.configure(text=("Kopyaladığın loglar anında maskelenir, AI cevapları gerçek değerlere döner."
                                             if agent.mode == "smart" else
                                             "Kopyaladığın her metin maskelenir. Geri çevirmeyi elle yaparsın."))
                else:
                    dot.configure(text_color=FAINT); hero_title.configure(text="Oto-izle kapalı")
                    hero_sub.configure(text="Pano izlenmiyor. Kutulara yapıştırarak elle çalışabilir ya da anahtarı açabilirsin.")
            root.after(0, _)
        def flash(self, msg, tone="info"):
            stamp = time.strftime("%H:%M")
            root.after(0, lambda: last_lbl.configure(text="%s   %s" % (stamp, msg), text_color=TONES.get(tone, MUTED)))
        def capture(self, kind, original, result, n, why=""):
            def _():
                if kind == "restore":
                    show_page("Geri Çevir"); set_text(reply, original); show_reals(restored_out, result)
                    self.flash(("↩  AI cevabı: %d değer geri çevrildi · gerçek hali panoda" % n) if n
                               else "AI cevabı yakalandı, geri çevrilecek değer yoktu", "real" if n else "info")
                else:
                    show_page("Anonimleştir"); set_text(src, original); show_fakes(masked_out, result)
                    set_badge(n)
                    self.flash(("●  %d öğe maskelendi · Ctrl+V ile yapıştır" % n) if n
                               else "Pano yakalandı, maskelenecek yeni değer yoktu", "ok" if n else "info")
            root.after(0, _)
    gui = Gui(); agent.gui = gui
    show_page("Anonimleştir"); gui.refresh()

    # ---------- sistem tepsisi + bildirim ----------
    icon = None
    if pystray and PILImage is not None:
        def tray_toggle(i=None, item=None): set_auto(not agent.auto)
        def tray_show(i=None, item=None):
            root.after(0, lambda: (root.deiconify(), root.lift(), root.focus_force()))
        def tray_anon(i=None, item=None): agent.clip_anonymize()
        def tray_restore(i=None, item=None): agent.clip_restore()
        def tray_clear(i=None, item=None): root.after(0, do_clear)
        def tray_keys(i=None, item=None): root.after(0, show_hotkeys)
        def tray_quit(i=None, item=None):
            try: icon.stop()
            except Exception: pass
            agent.stop(); root.after(0, root.destroy)
        menu = pystray.Menu(
            pystray.MenuItem("Göster", tray_show, default=True),
            pystray.MenuItem(lambda i: ("Oto-izle: açık" if agent.auto else "Oto-izle: kapalı"), tray_toggle),
            pystray.MenuItem(lambda i: ("Yön: Akıllı" if agent.mode == "smart" else "Yön: Sadece maskele"),
                             lambda i=None, item=None: root.after(0, toggle_mode)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Panoyu anonimleştir  (Ctrl+Alt+A)", tray_anon),
            pystray.MenuItem("Panoyu geri çevir  (Ctrl+Alt+R)", tray_restore),
            pystray.MenuItem("Defteri sıfırla…", tray_clear),
            pystray.MenuItem("Kısayollar…", tray_keys),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Çıkış", tray_quit),
        )
        try:
            icon = pystray.Icon("anonim_ajan", app_icon(64), "Anonim Ajan", menu)
            threading.Thread(target=icon.run, daemon=True).start()
        except Exception as ex:
            icon = None; print("Tepsi ikonu başlatılamadı:", ex)

    def notify(title, msg):
        if icon is not None:
            try: icon.notify(msg, title); return
            except Exception: pass
        if sys.platform.startswith("linux"):
            try:
                import subprocess; subprocess.Popen(["notify-send", "-i", "security-high", title, msg]); return
            except Exception: pass
    agent.notify = notify

    def on_close():
        if sys.platform == "win32" and icon is not None:
            root.withdraw(); notify("Anonim Ajan", "Arka planda çalışıyor — tepsi simgesinden açabilirsin.")
        elif sys.platform != "win32":
            # Linux/macOS: her masaüstünde tepsi alanı yok (ör. düz GNOME) — gizlemek yerine küçült.
            root.iconify(); notify("Anonim Ajan", "Küçültüldü, izleme sürüyor. Çıkmak için Ctrl+Q.")
        else:
            agent.stop(); root.destroy()
    root.bind_all("<Control-q>", lambda e: (agent.stop(), root.destroy()))
    root.protocol("WM_DELETE_WINDOW", on_close)

    if keyboard:
        try:
            hk = keyboard.GlobalHotKeys({
                "<ctrl>+<alt>+a": agent.clip_anonymize,
                "<ctrl>+<alt>+r": agent.clip_restore,
                "<ctrl>+<alt>+t": lambda: set_auto(not agent.auto),
            })
            hk.daemon = True; hk.start()
        except Exception as ex:
            gui.flash("Kısayollar başlatılamadı: %s" % ex, "warn")

    # pano erişimi kontrolü → varsa oto-izleyi aç
    clip_ok = False
    if pyperclip:
        try:
            pyperclip.paste(); agent.sync_now(); clip_ok = True   # açılıştaki panoya dokunma
        except Exception as ex:
            gui.flash("Pano okunamıyor (%s). Linux'ta: sudo apt install xclip" % ex, "warn")
    else:
        gui.flash("pyperclip yok — pip install pyperclip pynput ile kur.", "warn")
    set_auto(clip_ok, quiet=True)
    set_caps([("Pano", clip_ok), ("Kısayol", bool(keyboard)), ("Tepsi", icon is not None),
              ("Tekrar-kopya", bool(agent.counter))])
    if not keyboard:
        gui.flash("Kısayollar kapalı (pynput yok) — anahtar yine çalışır", "warn")
    elif clip_ok:
        gui.flash("Hazır — bir log kopyala, maskeli hali panoya gelsin.", "ok")
    legacy = agent.mapper.legacy_count()
    if legacy:
        gui.flash("Defterde eski biçimde %d kayıt var — yeni etiketler için Defter'den bir kez Sıfırla" % legacy, "warn")

    threading.Thread(target=agent.watch_loop, daemon=True).start()
    root.mainloop(); agent.stop()


def main():
    args = sys.argv[1:]
    if args[:1] == ["--export-icon"]:
        path = args[1] if len(args) > 1 else "anonim_ajan.ico"
        print("Simge yazıldı:", export_icon(path)); return
    if pyperclip is None:
        print("Uyarı: pyperclip yok — pano/kısayol çalışmaz, ama kutular yine çalışır.\n"
              "  pip install pyperclip pynput")
    agent = Agent()
    try:
        run_gui(agent)
    except SystemExit:
        raise
    except Exception as ex:
        # Konsolsuz exe'de hata görünmez ve süreç arka planda asılı kalabilir:
        # hatayı dosyaya yaz, ekranda göster, süreci tamamen kapat.
        import traceback
        detail = traceback.format_exc()
        log = os.path.join(os.path.expanduser("~"), "anonim_ajan_hata.log")
        try:
            with open(log, "w", encoding="utf-8") as f: f.write(detail)
        except Exception:
            log = None
        print(detail)
        try:
            import tkinter as tk
            from tkinter import messagebox
            r = tk.Tk(); r.withdraw()
            messagebox.showerror("Anonim Ajan açılamadı",
                                 "%s\n\n%s" % (ex, ("Ayrıntılar: " + log) if log else ""))
        except Exception:
            pass
        os._exit(1)


if __name__ == "__main__":
    main()
