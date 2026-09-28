#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anonim Ajan — log/config anonimleştirici (masaüstü).

İKİ KULLANIM:
  1) Kutu akışı (HTML gibi, her zaman çalışır): logu üst kutuya yapıştır,
     kategorileri seç, "Anonimleştir"e bas, maskeli çıktıyı "Panoya kopyala".
     AI'ın cevabını alt kutuya yapıştır, "Geri çevir" ile gerçek değerlere dön.
  2) Pano yakalama (bonus): "Oto-izle"yi aç ya da kısayolları kullan; kopyaladığın
     metin havada yakalanıp maskelenir. (İzin gerektirir — aşağıdaki nota bak.)

Kısayollar (isteğe bağlı, pynput varsa):
  Ctrl+Alt+A  panodaki metni anonimleştir
  Ctrl+Alt+R  panodaki metni geri çevir
  Ctrl+Alt+T  oto-izlemeyi aç/kapa

Kurulum:   pip install pyperclip pynput
Çalıştır:  python anonim_agent.py

macOS: Sistem Ayarları > Gizlilik ve Güvenlik > Erişilebilirlik + Girdi İzleme'de
       Terminal/Python'a izin ver (yalnızca pano yakalama/kısayol için gerekir;
       kutu akışı iznsiz çalışır). Linux: pano için 'xclip' veya 'xsel' kurulu olmalı.
"""

import json, os, re, sys, threading, time, random

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

FAKE_TLDS  = ["net","org","io","com","dev","cloud","systems","co","tech","net.tr"]
FAKE_NAMES = ["dagdelen","meridyen","cinar","poyraz","tulpar","boruk","yildizlar",
    "korelasyon","efrasiya","tuncbilek","kayra","orionteknik","levantis","zumrut",
    "karadeniz","batuhan","serdivan","argos","yelkovan","nirvana","paravel"]
FAKE_LABELS= ["srv","node","gw","host","edge","core","app","db","web","vm","proxy",
    "relay","cache","auth","mail","ns","dc","lb","api","svc"]
CFG_WORDS  = ["ds","db","schema","pool","svc","app","cat","cfg"]

PAT = {
    "ipv4":  re.compile(r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\d.])"),
    "ipv6":  re.compile(r"(?<![0-9A-Fa-f:])(?:(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}|(?:[0-9A-Fa-f]{1,4}:){1,7}:|(?:[0-9A-Fa-f]{1,4}:){1,6}:[0-9A-Fa-f]{1,4}|(?:[0-9A-Fa-f]{1,4}:){1,5}(?::[0-9A-Fa-f]{1,4}){1,2}|(?:[0-9A-Fa-f]{1,4}:){1,4}(?::[0-9A-Fa-f]{1,4}){1,3}|(?:[0-9A-Fa-f]{1,4}:){1,3}(?::[0-9A-Fa-f]{1,4}){1,4}|(?:[0-9A-Fa-f]{1,4}:){1,2}(?::[0-9A-Fa-f]{1,4}){1,5}|[0-9A-Fa-f]{1,4}:(?::[0-9A-Fa-f]{1,4}){1,6}|:(?:(?::[0-9A-Fa-f]{1,4}){1,7}|:))(?![0-9A-Fa-f:])"),
    "email": re.compile(r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]+@(?:[A-Za-z0-9\-]+\.)+[A-Za-z]{2,}(?![A-Za-z0-9\-])"),
    "domain":re.compile(r"(?<![A-Za-z0-9.@\-])(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}(?![A-Za-z0-9\-])"),
    "mac":   re.compile(r"(?<![0-9A-Fa-f:\-])(?:[0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:\-])"),
}
PRIO = {"custom":6,"email":5,"domain":4,"ipv6":3,"ipv4":2,"mac":1,"hostname":0.5,"config":0}

HOST_BLOCK = set(["md5","md2","sha1","sha2","sha3","sha224","sha256","sha384","sha512",
    "crc32","adler32","base64","base32","utf8","utf16","utf32","latin1","iso88591","x8664",
    "amd64","arm64","win32","win64","http2","http3","tls10","tls11","tls12","tls13","ssl2",
    "ssl3","ipv4","ipv6","oauth2","ec2","s3","k8s","i18n","l10n","a11y","p2p","log4j","ext4",
    "fat32","ntfs","rfc822"])

KW_RE  = re.compile(r"\b(?:hostname|nodename|node|computername|computer|dnsname|host|cn)\b\s*[:=]\s*[\"']?([A-Za-z][A-Za-z0-9\-]{1,62})[\"']?", re.I)
TOK_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*\b")

HOST_BLOCK |= {"log4j2","tlsv1","tlsv12","tlsv13","sslv3","utf8mb4","h2","md4","ripemd160"}

# "thread-12", "pool-3", "worker-7", "port8080"… hostname değil — log gürültüsü
HOST_NOISE = {"thread","threads","pool","worker","workers","task","tasks","exec","executor",
    "nio","ajp","main","job","batch","session","sess","req","request","conn","connection",
    "tx","timer","scheduler","async","default","eventloop","loop","reactor","line","row","col",
    "page","step","item","port","pid","tid","build","rev","release","version","ver","attempt",
    "retry","try","phase","stage","part","chunk","index","idx","slot","queue","listener",
    "handler","consumer","producer","partition","offset","epoch","gen","generation"}
# ürün + sürüm ("java17", "jdk11", "postgres14", "rhel8") hostname değil
HOST_PRODUCT = {"java","jdk","jre","jvm","openjdk","jboss","wildfly","eap","tomcat","spring",
    "hibernate","postgres","postgresql","pg","mysql","mariadb","mssql","oracle","ora","redis",
    "kafka","nginx","apache","httpd","centos","rhel","el","ubuntu","debian","windows","win",
    "python","py","npm","tls","tlsv","ssl","sslv","http","https","utf","iso","cp","sha",
    "md","ipv","rfc","cve","jsr","jep","log","slf","logback","junit","maven","gradle","v"}

# Gerçek alan adı TLD'leri — "org.jboss.as.controller", "server.log", "standalone.xml",
# "AbstractPool.java" gibi paket/dosya adlarının DNS sanılmasını önler.
TLDS = set("""com net org io co info biz tr uk de eu us gov edu mil int local lan internal
    intranet intra corp home localdomain cloud dev app ai tech systems online site xyz me nl fr
    it es ru ch at be se no dk fi cz gr ro hu az kz ua il ae sa qa in cn jp kr sg hk tw au nz ca
    br mx za arpa""".split())
TWO_LEVEL = set("""com.tr net.tr org.tr gov.tr edu.tr bel.tr k12.tr gen.tr av.tr bbs.tr
    co.uk org.uk ac.uk gov.uk com.au net.au co.jp co.kr com.br com.cn co.za co.in""".split())
# Genel/kamusal alan adları — maskelemeye gerek yok (AI'ın cevabında da sık geçer)
BENIGN_DOMAINS = set("""example.com example.org example.net localhost.localdomain github.com
    gitlab.com stackoverflow.com google.com microsoft.com apple.com redhat.com oracle.com
    jboss.org wildfly.org apache.org python.org pypi.org npmjs.com maven.org spring.io openai.com
    anthropic.com claude.ai chatgpt.com ubuntu.com debian.org centos.org kernel.org mozilla.org
    w3.org ietf.org wikipedia.org docker.com docker.io kubernetes.io postgresql.org mysql.com
    mariadb.org cloudflare.com letsencrypt.org xmlsoap.org jcp.org sun.com java.com
    openjdk.org hibernate.org eclipse.org jakarta.ee""".split())
BENIGN_IPS = {"127.0.0.1","0.0.0.0","255.255.255.255","8.8.8.8","8.8.4.4","1.1.1.1","1.0.0.1"}


def _split_domain(d):
    """('x','fatih') , 'fatih.com.tr'  → alt etiketler ve kök (iki seviyeli uzantıları tanır)"""
    labels = d.split(".")
    n = 3 if len(labels) >= 3 and ".".join(labels[-2:]).lower() in TWO_LEVEL else 2
    return labels[:-n], ".".join(labels[-n:])

def _valid_domain(d):
    tld = d.rsplit(".", 1)[-1]
    if tld != tld.lower() or tld not in TLDS: return False      # Java sınıfı / dosya uzantısı
    low = d.lower()
    if any(low == b or low.endswith("." + b) for b in BENIGN_DOMAINS): return False
    return True

def _benign_ip(ip):
    return ip in BENIGN_IPS or ip.startswith("255.") or ip.startswith("0.")

# ---- config anahtarları ----
# Serbest anahtarlar: ayraçsız da olur ("datasource jboss")
CFG_FREE = ["datasource name","datasource","data source","data-source","jndi name","jndi-name",
    "jndi","pool name","pool-name","database name","database-name","schema name","service name",
    "instance name","connection pool","connection-pool"]
# Genel kelimeler: yalnızca açık ayraçla (":", "=", XML ">") — düz cümlede yanlış eşleşmesin
CFG_STRICT = ["database","databasename","db name","db-name","dbname","db","schema","schema-name",
    "catalog","ds name","dsname","pool","servicename","service-name","sid","instance",
    "instance-name","username","user name","user-name","user-id","userid","uid","realm",
    "context root","context-root"]
def _cfg_alt(keys):
    return "|".join(r"\s+".join(re.escape(p) for p in k.split()) for k in sorted(keys, key=len, reverse=True))
_CFG_VAL = r"\s*[\"']?([A-Za-z_][\w.\-\/:]*)[\"']?"
CFG_FREE_RE   = re.compile(r"\b(?:" + _cfg_alt(CFG_FREE) + r")\b\s*(?:[:=>]|:=|=>|->)?" + _CFG_VAL, re.I)
CFG_STRICT_RE = re.compile(r"\b(?:" + _cfg_alt(CFG_STRICT) + r")\b\s*(?:[:=>]|:=|=>|->)" + _CFG_VAL, re.I)
CFG_STOP = set(["is","are","was","were","be","been","the","a","an","of","for","to","in","on",
    "and","or","not","no","yes","true","false","null","none","name","value","type","this","that",
    "with","ise","olarak","bir","ve","veya","için","ile","adı","adi","ismi","olan","gibi"])
CFG_STOP |= {k.lower() for k in CFG_FREE + CFG_STRICT}   # "<datasource jndi-name=…>" → "jndi-name" değer değil

LABELS = {"ipv4":"IPv4","ipv6":"IPv6","domain":"DNS","email":"E-POSTA","mac":"MAC",
          "hostname":"HOST","config":"CONFIG","custom":"ÖZEL"}
ALL_TYPES = ("ipv4","ipv6","domain","email","mac","hostname","config","custom")

# Sahte sonekleri — "srv41k", "db_k41": gerçek isimlerle (app1, db2, web01) çakışmaz
_SUFFIX_CH = "abcdefghjkmnpqrstuvwxyz"
# Eski sürümün kısa sahteleri (app2, db8, pool45): otomatik yön kararında güvenilmez
_LEGACY_RE = re.compile(r"[a-z]+\d{1,2}")
def _is_legacy(fake): return bool(_LEGACY_RE.fullmatch(fake))


def _looks_like_host(tok):
    if len(tok) < 3 or len(tok) > 63: return False
    if not re.search(r"\d", tok): return False
    low = tok.lower()
    if low.replace("-","") in HOST_BLOCK: return False
    m = re.match(r"[a-z]+", low)
    first = m.group(0) if m else ""
    if first in HOST_NOISE: return False                                   # thread-12, pool-3
    if first in HOST_PRODUCT and re.fullmatch(r"[a-z]+[-_]?v?\d+(?:[.\-_]\d+)*[a-z]?", low):
        return False                                                       # java17, rhel8
    if not re.search(r"[a-z]", tok) and re.search(r"\d{4,}", tok):
        return False                                                       # WFLYCTL0013, ORA-00942
    if re.fullmatch(r"[0-9a-f\-]{8,}", low): return False                  # hash / UUID parçası
    if "-" not in tok and len(first) < 2: return False
    return True


class Mapper:
    def __init__(self):
        self.entries = []
        self.real_to_fake = {}
        self.used_fakes = set()
        self.base_map = {}
        self.label_map = {}
        self.used_bases = set()
        self.used_labels = set()
        self.custom_terms = []
        self.lock = threading.RLock()
        self.load()

    def _unique(self, gen, seen):
        for _ in range(400):
            v = gen()
            if v not in seen and v not in self.used_fakes:
                return v
        base = gen(); n = 2; v = base
        while v in seen or v in self.used_fakes:
            v = base + str(n); n += 1
        return v

    def _fake_ipv4(self, _):
        heads = [
            lambda: "10.%d.%d.%d"  % (random.randint(0,254), random.randint(0,254), random.randint(1,254)),
            lambda: "192.168.%d.%d"% (random.randint(0,254), random.randint(1,254)),
            lambda: "172.%d.%d.%d" % (random.randint(16,31), random.randint(0,254), random.randint(1,254)),
        ]
        return self._unique(lambda: random.choice(heads)(), self.used_fakes)
    def _hex(self, n): return "".join(random.choice("0123456789abcdef") for _ in range(n))
    def _fake_ipv6(self, _):
        return self._unique(lambda: ":".join(self._hex(4) for _ in range(8)), self.used_fakes)
    def _fake_mac(self, _):
        return self._unique(lambda: ":".join(self._hex(2) for _ in range(6)).upper(), self.used_fakes)
    def _sfx(self):
        return "%02d%s" % (random.randint(10,99), random.choice(_SUFFIX_CH))
    def _fake_config(self, _):
        return self._unique(lambda: "%s_%s%02d" % (random.choice(CFG_WORDS), random.choice(_SUFFIX_CH),
                                                   random.randint(10,99)), self.used_fakes)
    def _fake_base(self, real_base):
        if real_base in self.base_map: return self.base_map[real_base]
        v = self._unique(lambda: "%s.%s" % (random.choice(FAKE_NAMES), random.choice(FAKE_TLDS)), self.used_bases)
        self.base_map[real_base] = v; self.used_bases.add(v); return v
    def _fake_label(self, real_label):
        if real_label in self.label_map: return self.label_map[real_label]
        v = self._unique(lambda: random.choice(FAKE_LABELS) + self._sfx(), self.used_labels)
        self.label_map[real_label] = v; self.used_labels.add(v); return v
    def _fake_domain(self, d):
        subs, base = _split_domain(d)
        if not subs and "." not in base: return d
        return ".".join([self._fake_label(s) for s in subs] + [self._fake_base(base)])
    def _fake_email(self, e):
        at = e.index("@"); dom = e[at+1:]
        local = self._unique(lambda: random.choice(FAKE_LABELS) + self._sfx(), self.used_fakes)
        return "%s@%s" % (local, self._register(dom, "domain", self._fake_domain))

    def _register(self, real, typ, gen):
        if real in self.real_to_fake: return self.real_to_fake[real]
        fake = gen(real)
        self.real_to_fake[real] = fake; self.used_fakes.add(fake)
        self.entries.append({"real": real, "fake": fake, "type": typ})
        return fake

    def _get_fake(self, value, typ):
        return {
            "ipv4":     lambda: self._register(value, typ, self._fake_ipv4),
            "ipv6":     lambda: self._register(value, typ, self._fake_ipv6),
            "mac":      lambda: self._register(value, typ, self._fake_mac),
            "hostname": lambda: self._register(value, typ, self._fake_label),
            "config":   lambda: self._register(value, typ, self._fake_config),
            "email":    lambda: self._register(value, typ, self._fake_email),
            "domain":   lambda: self._register(value, typ, self._fake_domain),
            "custom":   lambda: self._register(value, typ, lambda _: self._unique(lambda: "OZEL_%d" % random.randint(1000,9999), self.used_fakes)),
        }[typ]()

    def _collect(self, text, opts=None, skip=frozenset()):
        """Hassas değerleri bulur. `skip`: zaten sahte olan değerler — dokunulmaz."""
        if opts is None:
            opts = {k: True for k in ALL_TYPES}
        found = []
        if opts.get("custom"):
            for term in sorted([t for t in self.custom_terms if t], key=len, reverse=True):
                for m in re.finditer(re.escape(term), text, re.I):
                    found.append((m.start(), m.end(), m.group(0), "custom"))
        for typ in ("email","domain","ipv6","ipv4","mac"):
            if opts.get(typ):
                for m in PAT[typ].finditer(text):
                    v = m.group(0)
                    if not v: continue
                    if typ == "domain" and not _valid_domain(v): continue
                    if typ == "ipv4" and _benign_ip(v): continue
                    found.append((m.start(), m.end(), v, typ))
        if opts.get("hostname"):
            seen = set()
            def push(s, e, v):
                if (s, e) not in seen:
                    seen.add((s, e)); found.append((s, e, v, "hostname"))
            for m in KW_RE.finditer(text):
                name = m.group(1); s = m.start() + m.group(0).rfind(name)
                push(s, s + len(name), name)
            for m in TOK_RE.finditer(text):
                if _looks_like_host(m.group(0)): push(m.start(), m.end(), m.group(0))
        if opts.get("config"):
            values = set()
            for rx in (CFG_FREE_RE, CFG_STRICT_RE):
                for m in rx.finditer(text):
                    val = re.sub(r"[:.]+$", "", m.group(1) or "")
                    if len(val) >= 2 and val.lower() not in CFG_STOP:
                        values.add(val)
            for v in values:
                for m in re.finditer(r"(?<![A-Za-z0-9._\-\/])" + re.escape(v) + r"(?![A-Za-z0-9._\-\/])", text):
                    found.append((m.start(), m.end(), v, "config"))
        found.sort(key=lambda x: (x[0], -PRIO[x[3]], -(x[1]-x[0])))
        chosen = []; last_end = -1
        for s, e, v, t in found:
            if s >= last_end:
                chosen.append((s, e, v, t)); last_end = e
        if skip:
            chosen = [c for c in chosen if c[2] not in skip]
        return chosen

    def strong_fakes(self):
        """Güvenilir sahteler (yeni format). Eski kısa sahteler gerçek isimlerle çakışabilir."""
        return {e["fake"] for e in self.entries if not _is_legacy(e["fake"])}

    def anonymize(self, text, opts=None):
        """Yeni hassas değerleri maskeler; metindeki mevcut sahtelere dokunmaz (çift maskeleme yok)."""
        with self.lock:
            matches = self._collect(text, opts, skip=self.strong_fakes())
            out = []; i = 0
            for s, e, v, t in matches:
                out.append(text[i:s]); out.append(self._get_fake(v, t)); i = e
            out.append(text[i:])
            if matches: self.save()
            return "".join(out), len(matches)

    def analyze(self, text, opts=None):
        """(sahte_sayısı, yeni_hassas_sayısı) — metin AI cevabı mı yoksa yeni log mu?"""
        with self.lock:
            strong = self.strong_fakes()
            fake_hits = 0
            for e in self.entries:
                f = e["fake"]
                if f not in strong or f not in text: continue
                lb, la = self._guard(e["type"])
                fake_hits += len(re.findall(lb + re.escape(f) + la, text))
            new_hits = len(self._collect(text, opts, skip=strong))
            return fake_hits, new_hits

    def classify(self, text, opts=None):
        """'restore' yalnızca metinde sahteler baskınsa (AI cevabı); aksi halde 'anon' (güvenli taraf)."""
        fake_hits, new_hits = self.analyze(text, opts)
        kind = "restore" if fake_hits > 0 and fake_hits >= new_hits else "anon"
        return kind, fake_hits, new_hits

    def legacy_count(self):
        return sum(1 for e in self.entries if _is_legacy(e["fake"]))

    def _guard(self, typ):
        if typ == "ipv4": return (r"(?<![0-9.])", r"(?![0-9.])")
        if typ in ("ipv6","mac"): return (r"(?<![0-9A-Fa-f:.\-])", r"(?![0-9A-Fa-f:.\-])")
        return (r"(?<![A-Za-z0-9._\-\/])", r"(?![A-Za-z0-9._\-\/])")

    def restore(self, text):
        with self.lock:
            count = 0
            for p in sorted(self.entries, key=lambda x: -len(x["fake"])):
                lb, la = self._guard(p["type"])
                pat = re.compile(lb + re.escape(p["fake"]) + la)
                new, n = pat.subn(p["real"], text)
                if n: count += n; text = new
            return text, count

    def set_custom(self, terms):
        with self.lock:
            self.custom_terms = terms; self.save()

    def save(self):
        try:
            with open(STORE, "w", encoding="utf-8") as f:
                json.dump({"entries": self.entries, "base_map": self.base_map,
                           "label_map": self.label_map, "custom_terms": self.custom_terms}, f,
                          ensure_ascii=False, indent=1)
        except Exception as ex:
            print("Kaydetme hatası:", ex)

    def load(self):
        if not os.path.exists(STORE): return
        try:
            with open(STORE, encoding="utf-8") as f: d = json.load(f)
            self.entries = d.get("entries", [])
            self.base_map = d.get("base_map", {}); self.label_map = d.get("label_map", {})
            self.custom_terms = d.get("custom_terms", [])
            for e in self.entries:
                self.real_to_fake[e["real"]] = e["fake"]; self.used_fakes.add(e["fake"])
            self.used_bases = set(self.base_map.values()); self.used_labels = set(self.label_map.values())
        except Exception as ex:
            print("Yükleme hatası:", ex)

    def clear(self):
        with self.lock:
            self.entries = []; self.real_to_fake = {}; self.used_fakes = set()
            self.base_map = {}; self.label_map = {}; self.used_bases = set(); self.used_labels = set()
            self.save()


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
            self._flash("Panoda sahte değer yok.")

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
            why = "AI cevabı algılandı (%d sahte değer)" % fakes
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


def run_gui(agent):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    BG="#0d1117"; PANEL="#161b22"; INK="#0b0f14"; TEXT="#c9d4e0"; DIM="#7d8b9c"
    SAFE="#43c46a"; ACT="#4fb3d9"; REAL="#f2596a"; LINE="#2a3542"
    MONO=("Consolas", 10); SANS=("Segoe UI", 9)

    root = tk.Tk()
    root.title("Anonim Ajan")
    root.geometry("820x680"); root.minsize(640, 560); root.configure(bg=BG)

    style = ttk.Style()
    try: style.theme_use("clam")
    except Exception: pass
    style.configure("Treeview", background=PANEL, foreground=TEXT, fieldbackground=PANEL, rowheight=22, borderwidth=0)
    style.configure("Treeview.Heading", background="#1b232d", foreground=DIM, borderwidth=0)
    style.map("Treeview", background=[("selected","#26527a")])

    def put_clipboard(t):
        """Uygulama içi 'Kopyala': önce yaz, sonra işaretle — izleyici bunu kullanıcı kopyası sanmasın."""
        if pyperclip:
            agent._write(t)
        else:
            root.clipboard_clear(); root.clipboard_append(t); root.update(); agent.mark_written(t)

    def textbox(parent, h):
        t = tk.Text(parent, height=h, bg=INK, fg=TEXT, insertbackground=TEXT, relief="flat",
                    font=MONO, wrap="word", padx=10, pady=8, bd=1, highlightthickness=1,
                    highlightbackground=LINE, highlightcolor=ACT)
        return t
    def label(parent, txt, fg=DIM, size=9, bold=False):
        return tk.Label(parent, text=txt, bg=BG, fg=fg, font=("Segoe UI", size, "bold" if bold else "normal"))
    def _hover(w, normal, hover):
        w.bind("<Enter>", lambda e: w.config(bg=hover))
        w.bind("<Leave>", lambda e: w.config(bg=normal))
    BTN = {
        "primary": (ACT,      "#63d6ff", "#08222d", ("Segoe UI",10,"bold"), 18, 9),
        "normal":  ("#1b2530","#243444", TEXT,      ("Segoe UI",9,"bold"),  14, 8),
        "ghost":   (BG,       "#1b2530", DIM,       ("Segoe UI",9),         12, 7),
        "danger":  ("#2a171b","#4a2530", REAL,      ("Segoe UI",9,"bold"),  13, 8),
        "small":   ("#161f29","#243444", DIM,       ("Segoe UI",8),         10, 5),
    }
    def button(parent, txt, cmd, kind="normal"):
        bg,hov,fg,font,px,py = BTN.get(kind, BTN["normal"])
        b = tk.Button(parent, text=txt, command=cmd, relief="flat", cursor="hand2",
                      bg=bg, fg=fg, activebackground=hov, activeforeground=fg, bd=0,
                      font=font, padx=px, pady=py)
        _hover(b, bg, hov); return b

    # ---------- üst bar: logo + başlık + OTO-İZLE düğmesi (hep görünür) ----------
    head = tk.Frame(root, bg=BG); head.pack(fill="x", padx=14, pady=(12,2))
    logo = tk.Canvas(head, width=34, height=34, bg=BG, highlightthickness=0)
    logo.create_polygon(17,3,29,8,29,17,17,31,5,17,5,8, outline=ACT, width=2, fill="#132030")
    logo.create_line(5,8,17,3,29,8, fill="#63d6ff", width=1)
    logo.create_oval(12,12,22,22, outline="#63d6ff", width=2)
    logo.create_line(24,27,10,27, fill=SAFE, width=2)
    logo.pack(side="left", padx=(0,10))
    titlebox = tk.Frame(head, bg=BG); titlebox.pack(side="left")
    label(titlebox, "Anonim Ajan", TEXT, 14, True).pack(anchor="w")
    label(titlebox, "log · config anonimleştirici", DIM, 8).pack(anchor="w")
    auto_lbl = label(head, "", DIM, 9, True); auto_lbl.pack(side="right")

    togglebar = tk.Frame(root, bg=BG); togglebar.pack(fill="x", padx=14, pady=(2,6))
    auto_btn = tk.Button(togglebar, text="○ OTO-İZLE KAPALI  (açmak için tıkla)",
                         command=lambda: set_auto(not agent.auto), relief="flat", cursor="hand2",
                         bg=PANEL, fg=TEXT, activebackground="#26527a", bd=0,
                         font=("Segoe UI", 10, "bold"), padx=16, pady=8)
    auto_btn.pack(side="left")
    MODE_TXT = {"smart": "Yön: Akıllı", "mask": "Yön: Sadece maskele"}
    def toggle_mode():
        agent.mode = "mask" if agent.mode == "smart" else "smart"
        mode_btn.config(text=MODE_TXT[agent.mode]); gui.refresh()
        gui.flash("Oto yön: " + ("Akıllı — log maskelenir, AI cevabı geri çevrilir" if agent.mode == "smart"
                                 else "Sadece maskele — her kopya maskelenir"))
    mode_btn = button(togglebar, MODE_TXT[agent.mode], toggle_mode, "small")
    mode_btn.pack(side="left", padx=(8,0), fill="y")
    cap_lbl = label(togglebar, "", DIM, 8); cap_lbl.pack(side="right")

    # alt durum çubuğu — sekmelerden ÖNCE ve en alta yerleşir, pencere küçülse de hep görünür
    statusbar = tk.Frame(root, bg=BG); statusbar.pack(side="bottom", fill="x", padx=14, pady=(2,10))
    flash_lbl = label(statusbar, "hazır", ACT, 9); flash_lbl.config(anchor="w", justify="left")
    flash_lbl.pack(side="left", fill="x", expand=True)

    # oto-izle durum kaynağı (tek giriş noktası; her thread'den güvenli)
    auto_cb_var = tk.BooleanVar(value=False)
    def set_auto(value):
        agent.auto = bool(value)
        def _():
            if auto_cb_var.get() != agent.auto: auto_cb_var.set(agent.auto)
            gui.refresh(); gui.flash("Oto-izle: " + ("AÇIK" if agent.auto else "KAPALI"))
        root.after(0, _)
    agent.set_auto = set_auto

    # ---------- sekmeler ----------
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(6,4,6,0))
    style.configure("TNotebook.Tab", background=PANEL, foreground=DIM,
                    padding=(20,9), font=("Segoe UI",10,"bold"), borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", INK)], foreground=[("selected", ACT)])
    nb = ttk.Notebook(root); nb.pack(fill="both", expand=True, padx=12, pady=(0,4))
    tab_anon = tk.Frame(nb, bg=BG); nb.add(tab_anon, text="  Anonimleştir  ")
    tab_rest = tk.Frame(nb, bg=BG); nb.add(tab_rest, text="  Geri Çevir  ")
    tab_book = tk.Frame(nb, bg=BG); nb.add(tab_book, text="  Defter  ")

    # ===== SEKME 1: Anonimleştir =====
    label(tab_anon, "Kategoriler — fazla maskeleyeni kapat (yeşil = açık)", DIM, 8).pack(anchor="w", padx=12, pady=(10,0))
    togf = tk.Frame(tab_anon, bg=BG); togf.pack(fill="x", padx=10, pady=(3,6))
    optvars = {}
    def make_chip(parent, t):
        v = tk.BooleanVar(value=True); optvars[t] = v
        chip = tk.Label(parent, text=LABELS[t], font=("Consolas",9,"bold"), cursor="hand2", padx=11, pady=5, bd=0)
        def paint(): chip.config(bg=(ACT if v.get() else "#1b2530"), fg=("#08222d" if v.get() else DIM))
        def toggle(e=None): v.set(not v.get()); paint()
        chip.bind("<Button-1>", toggle)
        chip.bind("<Enter>", lambda e: chip.config(bg=("#63d6ff" if v.get() else "#243444")))
        chip.bind("<Leave>", lambda e: paint())
        paint(); return chip
    for t in ALL_TYPES:
        make_chip(togf, t).pack(side="left", padx=3, pady=2)
    def get_opts(): return {t: optvars[t].get() for t in ALL_TYPES}
    agent.get_opts = get_opts

    cf = tk.Frame(tab_anon, bg=BG); cf.pack(fill="x", padx=12, pady=(0,8))
    label(cf, "Özel terimler:", DIM, 9).pack(side="left")
    custom_entry = tk.Entry(cf, bg=INK, fg=TEXT, insertbackground=TEXT, relief="flat", font=MONO,
                            highlightthickness=1, highlightbackground=LINE, highlightcolor=ACT)
    custom_entry.pack(side="left", fill="x", expand=True, padx=(8,0), ipady=3)
    custom_entry.insert(0, ", ".join(agent.mapper.custom_terms))

    # GİDEN
    label(tab_anon, "Log / config yapıştır", TEXT, 10, True).pack(anchor="w", padx=12, pady=(2,2))
    src = textbox(tab_anon, 8); src.pack(fill="both", expand=True, padx=12)
    r1 = tk.Frame(tab_anon, bg=BG); r1.pack(fill="x", padx=12, pady=7)
    out_lbl = label(r1, "", SAFE, 9, True)

    def do_anon():
        agent.mapper.set_custom([s.strip() for s in custom_entry.get().split(",") if s.strip()])
        txt = src.get("1.0","end-1c")
        if not txt.strip(): return gui.flash("Üst kutuya metin yapıştır.")
        masked, n = agent.mapper.anonymize(txt, get_opts())
        masked_out.config(state="normal"); masked_out.delete("1.0","end"); masked_out.insert("1.0", masked)
        gui.refresh(); out_lbl.config(text="%d öğe maskelendi" % n)
        gui.flash("Anonimleştirildi — 'Kopyala' ile al.")
    def copy_masked():
        t = masked_out.get("1.0","end-1c")
        if not t.strip(): return gui.flash("Kopyalanacak çıktı yok.")
        put_clipboard(t)
        gui.flash("Maskeli çıktı panoya kopyalandı.")
    def clear_giden():
        src.delete("1.0","end"); masked_out.delete("1.0","end"); out_lbl.config(text=""); gui.flash("Giriş temizlendi.")
    button(r1, "Anonimleştir", do_anon, "primary").pack(side="left")
    button(r1, "Kopyala", copy_masked, "normal").pack(side="left", padx=(6,0))
    button(r1, "Temizle", clear_giden, "ghost").pack(side="left", padx=(6,0))
    out_lbl.pack(side="right")

    label(tab_anon, "Maskeli çıktı — bunu AI'a gönder", DIM, 9).pack(anchor="w", padx=12)
    masked_out = textbox(tab_anon, 8); masked_out.pack(fill="both", expand=True, padx=12, pady=(2,12))

    # ===== SEKME 2: Geri Çevir =====
    label(tab_rest, "AI'ın cevabını yapıştır", TEXT, 10, True).pack(anchor="w", padx=12, pady=(12,2))
    reply = textbox(tab_rest, 10); reply.pack(fill="both", expand=True, padx=12)
    r2 = tk.Frame(tab_rest, bg=BG); r2.pack(fill="x", padx=12, pady=7)
    def do_restore():
        txt = reply.get("1.0","end-1c")
        if not txt.strip(): return gui.flash("AI cevabını yapıştır.")
        restored, n = agent.mapper.restore(txt)
        restored_out.config(state="normal"); restored_out.delete("1.0","end"); restored_out.insert("1.0", restored)
        gui.flash("Geri çevrildi: %d değer" % n)
    def copy_restored():
        t = restored_out.get("1.0","end-1c")
        if not t.strip(): return gui.flash("Kopyalanacak sonuç yok.")
        put_clipboard(t); gui.flash("Sonuç panoya kopyalandı.")
    def clear_gelen():
        reply.delete("1.0","end"); restored_out.delete("1.0","end"); gui.flash("Cevap alanı temizlendi.")
    button(r2, "Geri çevir", do_restore, "primary").pack(side="left")
    button(r2, "Kopyala", copy_restored, "normal").pack(side="left", padx=(6,0))
    button(r2, "Temizle", clear_gelen, "ghost").pack(side="left", padx=(6,0))
    label(tab_rest, "Geri çevrilmiş — gerçek değerler", DIM, 9).pack(anchor="w", padx=12)
    restored_out = textbox(tab_rest, 10); restored_out.pack(fill="both", expand=True, padx=12, pady=(2,12))

    # ===== SEKME 3: Defter =====
    dh = tk.Frame(tab_book, bg=BG); dh.pack(fill="x", padx=12, pady=(12,2))
    label(dh, "Eşleştirme defteri  (gerçek ↔ sahte)", TEXT, 10, True).pack(side="left")
    ledcount = label(dh, "", DIM, 9); ledcount.pack(side="right")
    tree = ttk.Treeview(tab_book, columns=("type","real","fake"), show="headings")
    tree.heading("type", text="Tür"); tree.column("type", width=80, anchor="w")
    tree.heading("real", text="Gerçek"); tree.column("real", width=300, anchor="w")
    tree.heading("fake", text="Sahte");  tree.column("fake", width=300, anchor="w")
    tree.pack(fill="both", expand=True, padx=12, pady=(6,8))
    bookbtns = tk.Frame(tab_book, bg=BG); bookbtns.pack(fill="x", padx=12, pady=(0,12))
    def do_export():
        p = filedialog.asksaveasfilename(defaultextension=".json", initialfile="anonim-defteri.json")
        if p:
            with open(p,"w",encoding="utf-8") as f:
                json.dump({"entries":agent.mapper.entries}, f, ensure_ascii=False, indent=1)
            gui.flash("Defter dışa aktarıldı.")
    def do_import():
        p = filedialog.askopenfilename(filetypes=[("JSON","*.json")])
        if p:
            with open(p,encoding="utf-8") as f: d=json.load(f)
            for e in d.get("entries",[]):
                if e.get("real") and e["real"] not in agent.mapper.real_to_fake:
                    agent.mapper.real_to_fake[e["real"]]=e["fake"]; agent.mapper.used_fakes.add(e["fake"])
                    agent.mapper.entries.append({"real":e["real"],"fake":e["fake"],"type":e.get("type","custom")})
            agent.mapper.save(); gui.refresh(); gui.flash("Defter içe aktarıldı.")
    def do_clear():
        agent.mapper.clear(); gui.refresh(); gui.flash("Defter sıfırlandı.")
    button(bookbtns, "Sıfırla", do_clear, "danger").pack(side="right")
    button(bookbtns, "İçe aktar", do_import, "small").pack(side="right", padx=(0,6))
    button(bookbtns, "Dışa aktar", do_export, "small").pack(side="right", padx=(0,6))

    class Gui:
        def refresh(self):
            def _():
                for r in tree.get_children(): tree.delete(r)
                for e in agent.mapper.entries:
                    tree.insert("", "end", values=(LABELS.get(e["type"],e["type"]), e["real"], e["fake"]))
                ledcount.config(text="%d kayıt" % len(agent.mapper.entries))
                auto_lbl.config(text=(("● Kopyala: log→maskele, AI cevabı→geri çevir" if agent.mode == "smart"
                                       else "● Kopyala: her metin maskelenir") if agent.auto else "○ oto-izle kapalı"),
                                fg=(SAFE if agent.auto else DIM))
                auto_btn.config(text=("● OTO-İZLE AÇIK  (kapatmak için tıkla)" if agent.auto else "○ OTO-İZLE KAPALI  (açmak için tıkla)"),
                                bg=(SAFE if agent.auto else PANEL), fg=("#08222d" if agent.auto else TEXT))
            root.after(0, _)
        def flash(self, msg): root.after(0, lambda: flash_lbl.config(text=msg))
        def capture(self, kind, original, result, n, why=""):
            def _():
                try: nb.select(tab_rest if kind == "restore" else tab_anon)
                except Exception: pass
                if kind == "restore":
                    reply.delete("1.0","end"); reply.insert("1.0", original)
                    restored_out.delete("1.0","end"); restored_out.insert("1.0", result)
                    flash_lbl.config(text=("↩ %s → geri çevrildi: %d değer. Gerçek hali panoda." % (why, n))
                                     if n else "AI cevabı yakalandı — geri çevrilecek değer yoktu.")
                else:
                    src.delete("1.0","end"); src.insert("1.0", original)
                    masked_out.delete("1.0","end"); masked_out.insert("1.0", result)
                    out_lbl.config(text="pano: %d öğe" % n)
                    flash_lbl.config(text=("🛡 %s → maskelendi: %d öğe. Ctrl+V ile yapıştır." % (why.capitalize(), n))
                                     if n else "Pano yakalandı — maskelenecek yeni değer yoktu.")
            root.after(0, _)
    gui = Gui(); agent.gui = gui; gui.refresh()

    # ---- kısayol bilgisi ----
    HOTKEY_TEXT = ("Ctrl+Alt+A   Panodaki metni anonimleştir\n"
                   "Ctrl+Alt+R   Panodaki metni geri çevir\n"
                   "Ctrl+Alt+T   Oto-izlemeyi aç/kapa\n\n"
                   "Oto-izle açıkken: log kopyala → otomatik maskelenir; "
                   "AI cevabını kopyala → otomatik geri çevrilir. Kısayola gerek kalmaz.")
    def show_hotkeys(*_):
        messagebox.showinfo("Kısayollar", HOTKEY_TEXT)
    button(head, "Kısayollar", show_hotkeys, "small").pack(side="right", padx=(0,8))

    # ---- sistem tepsisi ikonu + bildirim ----
    icon = None
    if pystray:
        def _mk_icon():
            img = Image.new("RGBA", (64,64), (0,0,0,0)); d = ImageDraw.Draw(img)
            d.polygon([(32,4),(56,14),(56,32),(32,60),(8,32),(8,14)], fill=(19,32,48,255), outline=(79,179,217,255))
            d.line([(8,14),(32,4),(56,14)], fill=(99,214,255,255), width=2)
            d.arc([24,17,40,35], start=180, end=360, fill=(99,214,255,255), width=3)  # kilit kemeri
            d.rounded_rectangle([23,27,41,46], radius=3, fill=(79,179,217,255))       # kilit gövdesi
            d.ellipse([29,33,35,39], fill=(19,32,48,255))                              # anahtar deliği
            d.rectangle([31,37,33,43], fill=(19,32,48,255))
            return img
        def tray_toggle(i=None, item=None):
            set_auto(not agent.auto)
        def tray_show(i=None, item=None):
            root.after(0, lambda: (root.deiconify(), root.lift(), root.focus_force()))
        def tray_anon(i=None, item=None): agent.clip_anonymize()
        def tray_restore(i=None, item=None): agent.clip_restore()
        def tray_clear(i=None, item=None): root.after(0, lambda: (agent.mapper.clear(), gui.refresh()))
        def tray_keys(i=None, item=None): root.after(0, show_hotkeys)
        def tray_quit(i=None, item=None):
            try: icon.stop()
            except Exception: pass
            agent.stop(); root.after(0, root.destroy)
        menu = pystray.Menu(
            pystray.MenuItem("Göster", tray_show, default=True),
            pystray.MenuItem(lambda i: ("Oto-izle: AÇIK" if agent.auto else "Oto-izle: kapalı"), tray_toggle),
            pystray.MenuItem(lambda i: ("Yön: Akıllı" if agent.mode == "smart" else "Yön: Sadece maskele"),
                             lambda i=None, item=None: root.after(0, toggle_mode)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Panoyu anonimleştir  (Ctrl+Alt+A)", tray_anon),
            pystray.MenuItem("Panoyu geri çevir  (Ctrl+Alt+R)", tray_restore),
            pystray.MenuItem("Defteri sıfırla", tray_clear),
            pystray.MenuItem("Kısayollar…", tray_keys),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Çıkış", tray_quit),
        )
        icon = pystray.Icon("anonim_ajan", _mk_icon(), "Anonim Ajan", menu)
        try:
            threading.Thread(target=icon.run, daemon=True).start()
        except Exception as ex:
            icon = None; print("Tepsi ikonu başlatılamadı:", ex)

    def notify(title, msg):
        if icon is not None:
            try: icon.notify(msg, title); return
            except Exception: pass
        if sys.platform.startswith("linux"):
            try:
                import subprocess; subprocess.Popen(["notify-send", title, msg]); return
            except Exception: pass
        gui.flash(msg)
    agent.notify = notify

    def on_close():
        if sys.platform == "win32" and icon is not None:
            root.withdraw(); notify("Anonim Ajan", "Arka planda çalışıyor — tepsi ikonundan aç.")
        elif sys.platform != "win32":
            # Linux/macOS: her masaüstünde tepsi alanı yok (ör. düz GNOME). Gizlemek yerine
            # küçült — pencere görev çubuğunda kalır, izleme sürer. Tamamen çıkış: tepsi → Çıkış veya Ctrl+Q.
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
            gui.flash("Kısayollar başlatılamadı: %s" % ex)

    # pano erişimi self-check → varsa oto-izleyi otomatik aç
    clip_ok = False
    if pyperclip:
        try:
            pyperclip.paste(); agent.sync_now(); clip_ok = True   # açılışta mevcut panoyu maskeleme
        except Exception as ex:
            gui.flash("Pano okunamıyor (%s). Linux'ta: sudo apt install xclip" % ex)
    else:
        gui.flash("pyperclip yok — kur: pip install pyperclip pynput, sonra tekrar çalıştır.")
    set_auto(clip_ok)
    cap_lbl.config(text="Pano %s · Kısayol %s · Tepsi %s · Tekrar-kopya %s" % (
        "✓" if clip_ok else "✗",
        "✓" if keyboard else "✗ (pynput yok)",
        "✓" if icon is not None else "✗",
        "✓" if agent.counter else "✗"))
    if not keyboard:
        gui.flash("Kısayollar kapalı (pynput yok) — yukarıdaki düğmeyle aç/kapat. Kurmak için: pip install pynput")
    elif clip_ok:
        gui.flash("Oto-izle AÇIK — bir log kopyala, maskeli hali panoya hazır olur.")
    legacy = agent.mapper.legacy_count()
    if legacy:
        gui.flash("Defterde eski formatta %d kayıt var — temiz başlangıç için Defter sekmesinden 'Sıfırla' önerilir." % legacy)

    threading.Thread(target=agent.watch_loop, daemon=True).start()
    root.mainloop(); agent.stop()


def main():
    if pyperclip is None:
        print("Uyarı: pyperclip yok — pano/kısayol çalışmaz, ama kutu akışı yine çalışır.\n"
              "  pip install pyperclip pynput")
    agent = Agent()
    try:
        run_gui(agent)
    except Exception as ex:
        print("GUI başlatılamadı:", ex)


if __name__ == "__main__":
    main()
