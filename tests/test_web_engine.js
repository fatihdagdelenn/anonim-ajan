#!/usr/bin/env node
/*
 * Anonim Ajan — web sürümü (anonimlestirici.html) için parite testleri.
 *
 *     node tests/test_web_engine.js                 # HTML içindeki motoru test et
 *     node tests/test_web_engine.js path/engine.js  # başka bir dosyadaki motoru test et
 *
 * HTML'deki /* ENGINE START *\/ … /* ENGINE END *\/ bloğu çıkarılır ve masaüstü
 * sürümün beklenen çıktılarıyla (tests/expected/*) birebir karşılaştırılır. Böylece
 * iki sürüm aynı girdiye aynı maskeyi verir; biri değişip diğeri unutulursa test kırılır.
 * Yalnızca Node 18+ gerekir, paket kurulumu yok.
 */
"use strict";
const fs = require("fs"), path = require("path");

const HERE = __dirname, ROOT = path.dirname(HERE);
const FIX = path.join(HERE, "fixtures"), EXP = path.join(HERE, "expected");

function loadEngine(file) {
  file = file || path.join(ROOT, "anonimlestirici.html");
  const src = fs.readFileSync(file, "utf8");
  const a = src.indexOf("/* ENGINE START"), b = src.indexOf("/* ENGINE END */");
  if (a < 0 || b < 0) throw new Error(file + ": ENGINE START/END işaretleri bulunamadı");
  return new Function(src.slice(a, b) + "\nreturn AnonimEngine;")();
}

// Python testindeki listelerle aynı (tests/test_masking.py)
const LEAKS = {
  "ip_a.txt": ["kemal", "web01", "ithub", "10.10.10.20", "10.10.10.255", "10.10.10.1", "185.12.34.56",
               "00:50:56:a1:b2:c3", "fe80::250:56ff:fea1:b2c3", "172.17.0.1", "br-3f2a1b4c5d6e",
               "mgmt-net0", "192.168.50.4", "6e:2f:1a:2b:3c:4d"],
  "docker_ps.txt": ["kemal", "web01", "ithub", "nostalgic_hopper", "registry.sirket.com.tr"],
  "dotenv.txt": ["ithub", "db01", "sirket.com.tr", "appdb", "appuser", "Gizli.Parola!42", "R3dis-Pa55",
                 "10.10.10.30", "raporcu", "M0ngo.Sifre", "raporlar", "9fK2mQ7xL4pZ8vB1nC6tR3yW5sD0hJ",
                 "pQ7vX2mL9kR4tB8nW1cZ6yH3sJ5dF0gA", "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI", "ghp_", "bildirim@", "Mail.Sifre9", "kemal"],
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
};
const KEEP = {
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
  "journalctl.txt": ["sshd[1234]", "ssh2", "USER=root", "invalid user oracle", "veth1a2b3c4", "pts/0", "uid=0"],
  "prompt_conn.txt": ["root@", "127.0.0.1", "sudo", "docker", "git@github.com:acme/", "PRIVATE KEY"],
  "docker_ps_local.txt": ["ghcr.io/open-webui/open-webui:main", "open-webui\n", "postgres:16-alpine",
                          "postgres                       16-alpine", "-app-1", "-db-1", "[::]:18443",
                          "ADMIN_USERNAME=\"admin\"", "Administrator", "/data/"],
  "jboss.txt": ["org.jboss.jca.core.connectionmanager.pool", "IJ000604", "WFLYSRV0010", ".war\"",
                "jboss-eap-7.4.12", "server.log.2026-09-30", "standalone.xml", "2026-10-01 09:12:01,114",
                "task-12", "Thread Pool -- 74"],
};

const reEsc = s => s.replace(/[.*+?^${}()|[\]\\\/]/g, "\\$&");
const fixtures = () => fs.readdirSync(FIX).filter(f => !f.startsWith(".")).sort();

function lineDiff(a, b) {
  const x = a.split("\n"), y = b.split("\n"), out = [];
  for (let i = 0; i < Math.max(x.length, y.length); i++)
    if (x[i] !== y[i]) { out.push("-" + (x[i] ?? "∅")); out.push("+" + (y[i] ?? "∅")); }
  return out.slice(0, 40).join("\n");
}

function checkFixture(E, name) {
  const src = fs.readFileSync(path.join(FIX, name), "utf8");
  const m = new E.Mapper(null);
  const [out] = m.anonymize(src);
  const problems = [];
  const exp = fs.readFileSync(path.join(EXP, name), "utf8");
  if (out !== exp) problems.push("masaüstü sürümünden farklı çıktı:\n" + lineDiff(exp, out));
  for (const v of LEAKS[name] || []) {
    const pat = /^\w+$/.test(v) ? new RegExp("(?<![A-Za-z0-9])" + reEsc(v) + "(?![A-Za-z0-9])") : new RegExp(reEsc(v));
    if (pat.test(out)) problems.push("SIZINTI: " + JSON.stringify(v) + " maskelenmedi");
  }
  for (const v of KEEP[name] || []) if (!out.includes(v)) problems.push("FAZLA MASKELEME: " + JSON.stringify(v));
  if (m.restore(out)[0] !== src) problems.push("geri çevirme orijinali vermedi");
  const [again, n] = m.anonymize(out);
  if (again !== out) problems.push("maskeli metni tekrar maskelemek " + n + " şeyi değiştirdi");
  return problems;
}

function checkConsistency(E) {
  const m = new E.Mapper(null), problems = [];
  const [a] = m.anonymize("kemal@web01:~/projects/ithub$ docker ps");
  const [b] = m.anonymize("Oct 01 09:13:44 web01 sudo[2201]:    kemal : COMMAND=/usr/bin/docker restart ithub-web-1");
  const [c] = m.anonymize("server_name ithub.sirket.com.tr;\nupstream ithub_backend { server 10.10.10.21:8080; }");
  const [d] = m.anonymize("ithub projesinde kemal kullanicisi web01 uzerinde hata aliyor");
  const tok = r => m.realToFake.get(r);
  for (const real of ["kemal", "web01", "ithub"]) {
    if (!tok(real)) { problems.push(real + " hiç etiketlenmedi"); continue; }
    for (const [label, txt] of [["prompt", a], ["journal", b], ["nginx", c], ["düz cümle", d]])
      if (txt.includes(real)) problems.push(label + " mesajında " + real + " açıkta kaldı");
  }
  if (tok("ithub") && !c.includes(tok("ithub") + ".DOMAIN_")) problems.push("alan adı etiketi projeyle aynı değil: " + c);
  if (tok("ithub") && !b.includes(tok("ithub") + "-web-1")) problems.push("compose konteyneri proje etiketini kullanmıyor: " + b);
  return problems;
}

function checkCrlf(E) {
  const problems = [];
  for (const name of fixtures()) {
    const src = fs.readFileSync(path.join(FIX, name), "utf8");
    const [lf] = new E.Mapper(null).anonymize(src);
    const m = new E.Mapper(null);
    const [crlf] = m.anonymize(src.replace(/\n/g, "\r\n"));
    if (crlf.replace(/\r\n/g, "\n") !== lf) problems.push(name + ": CRLF ile farklı sonuç\n" + lineDiff(lf, crlf.replace(/\r\n/g, "\n")));
    if (m.restore(crlf)[0] !== src.replace(/\n/g, "\r\n")) problems.push(name + ": CRLF geri çevirme orijinali vermedi");
  }
  return problems;
}

function checkLegacyUpgrade(E) {
  let saved = { version: 2, entries: [
    { real: "10.0.0.15", fake: "IP_5", type: "ipv4" },
    { real: "br-4c1e2f3a5b6d", fake: "HOST_10", type: "hostname" },
    { real: "appuser", fake: "KULLANICI_1", type: "config" },
    { real: "web01", fake: "HOST_3", type: "hostname" }],
    counters: { IP: 5, HOST: 10, KULLANICI: 1 } };
  const store = { load: () => JSON.parse(JSON.stringify(saved)), save: o => { saved = o; } };
  const m = new E.Mapper(store);
  const [out] = m.anonymize("4: br-4c1e2f3a5b6d: <UP> mtu 1500\n    inet 10.0.0.15/24 scope global br-4c1e2f3a5b6d\n" +
                            "DB_USER=appuser\nkemal@web01:~$ ls");
  const problems = [];
  for (const want of ["IFACE_1", "IP_PRIV_1/24", "DB_USER=USER_1", "@HOST_3:"])
    if (!out.includes(want)) problems.push("yükseltme bekleniyordu: " + want + " yok → " + out);
  const back = m.restore("IP_5 HOST_10 KULLANICI_1 IFACE_1 IP_PRIV_1")[0];
  if (back !== "10.0.0.15 br-4c1e2f3a5b6d appuser br-4c1e2f3a5b6d 10.0.0.15")
    problems.push("eski + yeni etiketler geri çevrilmedi: " + back);
  // kalıcı kayıtta parola olmamalı
  const m2 = new E.Mapper(store); m2.anonymize("DB_PASSWORD=Gizli.Parola!42");
  if (JSON.stringify(saved).includes("Gizli.Parola!42")) problems.push("parola depoya yazıldı");
  if (JSON.stringify(m2.exportEntries()).includes("Gizli.Parola!42")) problems.push("parola dışa aktarıldı");
  return problems;
}

// Parçalar çalışma anında birleştirilir: depoda gerçek görünümlü anahtar durmasın (GitHub push koruması)
function secretSamples() {
  const j = a => a.join("");
  return { Stripe: j(["sk_", "live_", "a1B2c3D4".repeat(3)]), GitHub: j(["gh", "p_", "A1b2C3d4E5".repeat(4)]),
           GitLab: j(["gl", "pat-", "x7Y8z9W0".repeat(3)]), Slack: j(["xo", "xb-", "1234567890-", "aBcDeFgHiJ"]),
           Google: j(["AI", "za", "Sy" + "Q1w2E3r4T5".repeat(3) + "abc"]), Vault: j(["hv", "s.", "Q1w2E3r4T5".repeat(3)]),
           AWS: j(["AK", "IA", "Q1W2E3R4T5Y6U7I8"]) };
}
function checkSecretFormats(E) {
  const problems = [];
  for (const [name, val] of Object.entries(secretSamples())) {
    const m = new E.Mapper(null), txt = "istek reddedildi: " + val + " gecersiz";
    const [out] = m.anonymize(txt);
    if (out.includes(val)) problems.push(name + " anahtarı biçiminden tanınmadı: " + out);
    if (m.restore(out)[0] !== txt) problems.push(name + " anahtarı geri çevrilmedi");
  }
  return problems;
}

function checkClassify(E) {
  const m = new E.Mapper(null), problems = [];
  m.anonymize("kemal@web01:~$ ping 10.10.10.20");
  const ai = "IP_PRIV_1 adresine HOST_1 üzerinden ulaşılamıyor; USER_1 ile tekrar dene.";
  if (m.classify(ai)[0] !== "restore") problems.push("AI cevabı geri çevrilecek diye sınıflanmadı");
  if (m.classify("yeni log: 172.16.9.9 app07 hata")[0] !== "anon") problems.push("yeni log maskelenecek diye sınıflanmadı");
  const back = m.restore(ai)[0];
  if (!back.includes("10.10.10.20") || !back.includes("web01") || !back.includes("kemal")) problems.push("ters eşleme eksik: " + back);
  if (m.restore("IP_PRIV_99 bilinmiyor")[0] !== "IP_PRIV_99 bilinmiyor") problems.push("bilinmeyen etiket değiştirildi");
  return problems;
}

function main() {
  const E = loadEngine(process.argv[2]);
  let failed = 0;
  const report = (label, p) => {
    console.log((p.length ? "✗ " : "✓ ") + label);
    for (const x of p) console.log("    " + x.replace(/\n/g, "\n    "));
    failed += p.length ? 1 : 0;
  };
  for (const name of fixtures()) report(name, checkFixture(E, name));
  report("mesajlar arası tutarlılık", checkConsistency(E));
  report("Windows satır sonları (CRLF)", checkCrlf(E));
  report("eski defterden yükseltme", checkLegacyUpgrade(E));
  report("anahtar biçimleri (Stripe, GitHub, AWS…)", checkSecretFormats(E));
  report("sınıflama + ters eşleme", checkClassify(E));
  console.log("\nWEB SONUÇ: " + failed + " başarısız");
  process.exit(failed ? 1 : 0);
}

if (require.main === module) main();
module.exports = { loadEngine };
