#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anonim Ajan — maskeleme regresyon testleri.

    python tests/test_masking.py            # testleri çalıştır
    python tests/test_masking.py --update   # beklenen çıktıları yeniden üret (önce farkı incele!)
    pytest tests/                           # pytest ile de çalışır

Her örnek (tests/fixtures/*) için:
  1. Maskeli çıktı tests/expected/<ad> ile birebir aynı olmalı.
  2. LEAKS listesindeki gerçek değerlerin HİÇBİRİ çıktıda geçmemeli.
  3. KEEP listesindeki değerler (standart arayüzler, ::1, registry'ler…) olduğu gibi kalmalı.
  4. Geri çevirince orijinal metin birebir geri gelmeli.
  5. Maskeli metni tekrar maskelemek hiçbir şeyi değiştirmemeli.

Arayüz paketleri (customtkinter, pynput…) gerekmez; yalnızca çekirdek motor yüklenir.
"""
import difflib, importlib.util, os, re, shutil, subprocess, sys, types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIX, EXP = os.path.join(HERE, "fixtures"), os.path.join(HERE, "expected")


def load_engine():
    for mod in ("pyperclip", "pynput"):          # arayüz bağımlılıkları olmadan yükle
        if mod not in sys.modules:
            try:
                __import__(mod)
            except Exception:
                sys.modules[mod] = types.ModuleType(mod)
    spec = importlib.util.spec_from_file_location("anonim_agent", os.path.join(ROOT, "anonim_agent.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


# Çıktıda ASLA görünmemesi gereken gerçek değerler
LEAKS = {
    "ip_a.txt": ["kemal", "web01", "ithub", "10.10.10.20", "10.10.10.255", "10.10.10.1", "185.12.34.56",
                 "00:50:56:a1:b2:c3", "fe80::250:56ff:fea1:b2c3", "172.17.0.1", "br-3f2a1b4c5d6e",
                 "mgmt-net0", "192.168.50.4", "6e:2f:1a:2b:3c:4d"],
    "docker_ps.txt": ["kemal", "web01", "ithub", "nostalgic_hopper", "registry.sirket.com.tr"],
    "dotenv.txt": ["ithub", "db01", "sirket.com.tr", "appdb", "appuser", "Gizli.Parola!42", "R3dis-Pa55",
                   "10.10.10.30", "raporcu", "M0ngo.Sifre", "raporlar", "9fK2mQ7xL4pZ8vB1nC6tR3yW5sD0hJ",
                   "pQ7vX2mL9kR4tB8nW1cZ6yH3sJ5dF0gA", "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI", "ghp_", "bildirim@", "Mail.Sifre9",
                   "kemal"],
    "etc_hosts.txt": ["web01", "db01", "veritabani", "redisprod", "yonetim", "sirket.com.tr",
                      "10.10.10.20", "10.10.10.30", "192.168.50.4", "185.12.34.56", "partner-firma"],
    "env.txt": ["web01", "kemal", "ithub", "185.12.34.56", "10.10.10.20", "hvs."],
    "docker_inspect.json": ["ithub", "kemal", "sirket.com.tr", "appuser", "Gizli.Parola!42",
                            "172.20.0.5", "172.20.0.1", "02:42:ac:14:00:05"],
    "nginx.conf": ["ithub", "10.10.10.21", "app02", "sirket.com.tr", "185.12.34.0", "eyJhbGci"],
    "journalctl.txt": ["web01", "kemal", "185.12.34.56", "ithub", "45.13.22.9", "deneme123",
                       "br-3f2a1b4c5d6e", "x9KzQ2mP7vL4nR8tY6wB1cD5fG0hJ3sA2qW"],
    "prompt_conn.txt": ["kemal", "web01", "ithub", "raporcu", "db01", "appuser", "yonetim", "sirket.com.tr",
                        "entegrasyon", "Ent3gre.Sifre", "appdb", "Url.Parola1", "b3BlbnNzaC1rZXkt"],
    "jboss.txt": ["db01", "sirket.com.tr", "appdb", "appuser", "Gizli.Parola!42", "raporDS", "ithub"],
    "docker_ps_local.txt": ["kemal", "srvdocker", "ithub", "vm-inventory", "it-system-management-hub",
                            "dockotp", "totp-panel", "totp", "10.0.0.15", "k3Jd9xPq2LmZ7vBn4RtY8wQe1AsDf6Gh",
                            "Yonetici.2026!"],
}

# Çıktıda AYNEN kalması gereken değerler (bağlam için gerekli, hassas değil)
KEEP = {
    "ip_a.txt": [" lo:", "ens192", "enp11s0", "docker0", "veth1a2b3c4@if23", "inet6", "link/ether",
                 "link/loopback", "qdisc", "brd", "scope host", "00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff",
                 "127.0.0.1/8", "::1/128", "valid_lft forever", "fq_codel", "/24", "/16", "/64"],
    "docker_ps.txt": ["CONTAINER ID", "postgres:15-alpine", "redis:7", "ghcr.io/acme/worker", "0.0.0.0:8080",
                      ":::8080", "-web-1", "-db-1", "_cache_1", "_default", "3f2a1b4c5d6e",
                      "DRIVER    SCOPE", "bridge    local"],
    "dotenv.txt": ["DB_PORT=5432", "PASSWORD_MIN_LENGTH=12", "SESSION_TTL=3600", "/run/secrets/db_password",
                   "${OLD_DB_PASS}", "LOG_LEVEL=info", "/token"],
    "etc_hosts.txt": ["127.0.0.1       localhost", "127.0.1.1", "ip6-localhost", "ip6-loopback", "ff02::1",
                      "ip6-allnodes", "ip6-allrouters", "::1"],
    "env.txt": ["/bin/bash", "en_US.UTF-8", "java-17-openjdk-amd64", "HISTSIZE=1000", "/usr/local/sbin"],
    "docker_inspect.json": ["\"Hostname\": \"3f2a1b4c5d6e\"", "IPv6Gateway", "GlobalIPv6Address", "IPPrefixLen",
                            "com.docker.compose.service", "/usr/local/sbin"],
    "nginx.conf": ["listen 443 ssl http2", "/24", "10.0.0.0/8", "fullchain.pem", "deny all"],
    "journalctl.txt": ["sshd[1234]", "ssh2", "USER=root", "invalid user oracle", "veth1a2b3c4", "pts/0",
                       "for user root" if False else "uid=0"],
    "prompt_conn.txt": ["root@", "127.0.0.1", "sudo", "docker", "git@github.com:acme/", "PRIVATE KEY"],
    "docker_ps_local.txt": ["ghcr.io/open-webui/open-webui:main", "open-webui\n", "postgres:16-alpine",
                            "postgres                       16-alpine", "-app-1", "-db-1", "[::]:18443",
                            "ADMIN_USERNAME=\"admin\"", "Administrator", "/data/"],
    "jboss.txt": ["org.jboss.jca.core.connectionmanager.pool", "IJ000604", "WFLYSRV0010", ".war\"",
                  "jboss-eap-7.4.12", "server.log.2026-09-30", "standalone.xml", "2026-10-01 09:12:01,114",
                  "task-12", "Thread Pool -- 74"],
}


def mask(engine, name, text):
    return engine.Mapper(store=None).anonymize(text)


def check_fixture(engine, name, update=False):
    src = open(os.path.join(FIX, name), encoding="utf-8").read()
    m = engine.Mapper(store=None)
    out, _ = m.anonymize(src)
    problems = []
    exp_path = os.path.join(EXP, name)
    if update:
        open(exp_path, "w", encoding="utf-8").write(out)
    elif not os.path.exists(exp_path):
        problems.append("beklenen çıktı yok — önce --update çalıştır")
    else:
        exp = open(exp_path, encoding="utf-8").read()
        if out != exp:
            diff = "".join(difflib.unified_diff(exp.splitlines(True), out.splitlines(True),
                                                "beklenen", "şimdiki", n=0))
            problems.append("çıktı beklenenden farklı:\n" + diff)
    for v in LEAKS.get(name, []):
        # kelime gibi değerlerde sınıra bak: "ithub" ararken "github.com" sızıntı sayılmasın
        pat = (r"(?<![A-Za-z0-9])" + re.escape(v) + r"(?![A-Za-z0-9])") if re.fullmatch(r"\w+", v) else re.escape(v)
        if re.search(pat, out): problems.append("SIZINTI: %r maskelenmedi" % v)
    for v in KEEP.get(name, []):
        if v not in out: problems.append("FAZLA MASKELEME: %r korunmalıydı" % v)
    back, _ = m.restore(out)
    if back != src: problems.append("geri çevirme orijinali vermedi")
    again, n = m.anonymize(out)
    if again != out: problems.append("maskeli metni tekrar maskelemek %d şeyi değiştirdi" % n)
    return problems


def check_consistency(engine):
    """Mesajlar arası tutarlılık: aynı ad farklı mesajlarda / bağlamlarda aynı etiketi almalı."""
    m = engine.Mapper(store=None)
    problems = []
    a, _ = m.anonymize("kemal@web01:~/projects/ithub$ docker ps")
    b, _ = m.anonymize("Oct 01 09:13:44 web01 sudo[2201]:    kemal : COMMAND=/usr/bin/docker restart ithub-web-1")
    c, _ = m.anonymize("server_name ithub.sirket.com.tr;\nupstream ithub_backend { server 10.10.10.21:8080; }")
    d, _ = m.anonymize("ithub projesinde kemal kullanicisi web01 uzerinde hata aliyor")   # bağlamsız düz cümle
    tok = lambda real: m.real_to_fake.get(real)
    for real in ("kemal", "web01", "ithub"):
        t = tok(real)
        if not t:
            problems.append("%r hiç etiketlenmedi" % real); continue
        for label, txt in (("prompt", a), ("journal", b), ("nginx", c), ("düz cümle", d)):
            if real in txt: problems.append("%s mesajında %r açıkta kaldı" % (label, real))
    if tok("ithub") and ("%s.DOMAIN_" % tok("ithub")) not in c:
        problems.append("ithub alan adı etiketi projeyle aynı değil: %s" % c)
    if tok("ithub") and ("%s-web-1" % tok("ithub")) not in b:
        problems.append("compose konteyneri proje etiketini kullanmıyor: %s" % b)
    return problems


def check_crlf(engine):
    """Windows panosu \\r\\n verir: her örnek CRLF ile de birebir aynı sonucu vermeli."""
    problems = []
    for name in fixtures():
        src = open(os.path.join(FIX, name), encoding="utf-8").read()
        lf, _ = engine.Mapper(store=None).anonymize(src)
        m = engine.Mapper(store=None)
        crlf, _ = m.anonymize(src.replace("\n", "\r\n"))
        if crlf.replace("\r\n", "\n") != lf:
            diff = "".join(difflib.unified_diff(lf.splitlines(True), crlf.replace("\r\n", "\n").splitlines(True),
                                                "LF", "CRLF", n=0))
            problems.append("%s: CRLF ile farklı sonuç\n%s" % (name, diff))
        if m.restore(crlf)[0] != src.replace("\n", "\r\n"):
            problems.append("%s: CRLF geri çevirme orijinali vermedi" % name)
    return problems


def check_legacy_upgrade(engine):
    """Eski sürümün defteri: bağlam daha kesin tür bulunca yeni etiket, eski etiket yine geri çevrilir."""
    import json, tempfile
    path = os.path.join(tempfile.mkdtemp(), "defter.json")
    json.dump({"version": 2, "entries": [
        {"real": "10.0.0.15", "fake": "IP_5", "type": "ipv4"},
        {"real": "br-4c1e2f3a5b6d", "fake": "HOST_10", "type": "hostname"},
        {"real": "appuser", "fake": "KULLANICI_1", "type": "config"},
        {"real": "web01", "fake": "HOST_3", "type": "hostname"}],
        "counters": {"IP": 5, "HOST": 10, "KULLANICI": 1}}, open(path, "w"))
    m = engine.Mapper(store=path)
    out, _ = m.anonymize("4: br-4c1e2f3a5b6d: <UP> mtu 1500\n    inet 10.0.0.15/24 scope global br-4c1e2f3a5b6d\n"
                         "DB_USER=appuser\nkemal@web01:~$ ls")
    problems = []
    for want in ("IFACE_1", "IP_PRIV_1/24", "DB_USER=USER_1", "@HOST_3:"):
        if want not in out: problems.append("yükseltme bekleniyordu: %r yok → %s" % (want, out))
    back = m.restore("IP_5 HOST_10 KULLANICI_1 IFACE_1 IP_PRIV_1")[0]
    if back != "10.0.0.15 br-4c1e2f3a5b6d appuser br-4c1e2f3a5b6d 10.0.0.15":
        problems.append("eski + yeni etiketler geri çevrilmedi: %s" % back)
    return problems


def secret_samples():
    """Sağlayıcı anahtar biçimleri. Parçalar çalışma anında birleştirilir: depoda gerçek görünümlü
    bir anahtar durmasın, GitHub'ın gizli anahtar taraması push'u engellemesin."""
    j = "".join
    return {"Stripe": j(["sk_", "live_", "a1B2c3D4" * 3]), "GitHub": j(["gh", "p_", "A1b2C3d4E5" * 4]),
            "GitLab": j(["gl", "pat-", "x7Y8z9W0" * 3]), "Slack": j(["xo", "xb-", "1234567890-", "aBcDeFgHiJ"]),
            "Google": j(["AI", "za", "Sy" + "Q1w2E3r4T5" * 3 + "abc"]), "Vault": j(["hv", "s.", "Q1w2E3r4T5" * 3]),
            "AWS": j(["AK", "IA", "Q1W2E3R4T5Y6U7I8"])}


def check_secret_formats(engine):
    """Anahtar adı olmadan, yalnızca biçiminden tanınmalı ve geri çevrilmeli."""
    problems = []
    for name, val in secret_samples().items():
        m = engine.Mapper(store=None)
        txt = "istek reddedildi: " + val + " gecersiz"
        out, _ = m.anonymize(txt)
        if val in out: problems.append("%s anahtarı biçiminden tanınmadı: %s" % (name, out))
        if m.restore(out)[0] != txt: problems.append("%s anahtarı geri çevrilmedi" % name)
    return problems


def check_classify(engine):
    m = engine.Mapper(store=None)
    masked, _ = m.anonymize("kemal@web01:~$ ping 10.10.10.20")
    ai = "IP_PRIV_1 adresine HOST_1 üzerinden ulaşılamıyor; USER_1 ile tekrar dene."
    problems = []
    if m.classify(ai)[0] != "restore": problems.append("AI cevabı geri çevrilecek diye sınıflanmadı")
    if m.classify("yeni log: 172.16.9.9 app07 hata")[0] != "anon": problems.append("yeni log maskelenecek diye sınıflanmadı")
    back = m.restore(ai)[0]
    if "10.10.10.20" not in back or "web01" not in back or "kemal" not in back:
        problems.append("ters eşleme eksik: %s" % back)
    if m.restore("IP_PRIV_99 bilinmiyor")[0] != "IP_PRIV_99 bilinmiyor":
        problems.append("bilinmeyen etiket değiştirildi")
    return problems


def check_web():
    """Web sürümü (anonimlestirici.html) aynı beklenen çıktıları vermeli — Node varsa çalışır."""
    node = shutil.which("node")
    if not node: return None
    r = subprocess.run([node, os.path.join(HERE, "test_web_engine.js")], capture_output=True, text=True, encoding="utf-8")
    return [] if r.returncode == 0 else [l for l in r.stdout.splitlines() if l.strip() and not l.startswith("✓")]


def fixtures():
    return sorted(f for f in os.listdir(FIX) if not f.startswith("."))


# ---- pytest girişleri ----
def test_fixtures():
    eng = load_engine(); bad = {n: p for n in fixtures() for p in [check_fixture(eng, n)] if p}
    assert not bad, "\n".join("%s:\n  %s" % (n, "\n  ".join(p)) for n, p in bad.items())

def test_consistency():
    p = check_consistency(load_engine()); assert not p, "\n".join(p)

def test_crlf():
    p = check_crlf(load_engine()); assert not p, "\n".join(p)

def test_legacy_upgrade():
    p = check_legacy_upgrade(load_engine()); assert not p, "\n".join(p)

def test_secret_formats():
    p = check_secret_formats(load_engine()); assert not p, "\n".join(p)

def test_classify_and_restore():
    p = check_classify(load_engine()); assert not p, "\n".join(p)


def test_web_parity():
    p = check_web()
    if p is None:
        import pytest; pytest.skip("node yok — web testi atlandı")
    assert not p, "\n".join(p)


def main():
    update = "--update" in sys.argv
    eng = load_engine()
    os.makedirs(EXP, exist_ok=True)
    failed = 0
    for name in fixtures():
        p = check_fixture(eng, name, update)
        print(("✓ " if not p else "✗ ") + name)
        for x in p: print("    " + x.replace("\n", "\n    "))
        failed += bool(p)
    for label, fn in (("mesajlar arası tutarlılık", check_consistency), ("Windows satır sonları (CRLF)", check_crlf),
                      ("eski defterden yükseltme", check_legacy_upgrade),
                      ("anahtar biçimleri (Stripe, GitHub, AWS…)", check_secret_formats), ("sınıflama + ters eşleme", check_classify)):
        p = fn(eng)
        print(("✓ " if not p else "✗ ") + label)
        for x in p: print("    " + x)
        failed += bool(p)
    if not update:
        p = check_web()
        if p is None: print("- web sürümü (node bulunamadı, atlandı)")
        else:
            print(("✓ " if not p else "✗ ") + "web sürümü aynı sonucu veriyor (anonimlestirici.html)")
            for x in p: print("    " + x)
            failed += bool(p)
    print("\n%s: %d başarısız" % ("GÜNCELLENDİ" if update else "SONUÇ", failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
