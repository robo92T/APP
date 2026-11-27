# BID Dochádzka – dochádzkový systém pre Bratislavskú integrovanú dopravu, a.s.

Funkčný prototyp: server (Python/FastAPI + SQLite), webová a mobilná aplikácia (PWA – Android, iPhone, Windows),
terminál na stenu (tablet + USB čítačka čipov), schvaľovanie žiadostí, rozpis zmien pre dispečing 24/7 a export pre mzdy.

## 1. Rýchle spustenie na vlastnom počítači (5 minút)

```bash
# 1. nainštalujte Python 3.11+  (python.org)
python -m venv .venv
.venv\Scripts\activate          # Windows   (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt

# 2. vytvorte databázu s ukážkovými dátami
python -m backend.seed --demo

# 3. spustite server
uvicorn backend.app:app --port 8000
```

| Čo | Adresa | Prihlásenie |
|---|---|---|
| Aplikácia | http://localhost:8000 | `admin` / `Admin2026!` |
| Zamestnanec | | `jsimkova` / `Demo2026!` |
| Vedúci | | `mpolak`, `tvarga`, `rmolnar` (dispečing) / `Demo2026!` |
| Personalistka (mzdy) | | `lbalaz` / `Demo2026!` |
| Terminál | http://localhost:8000/kiosk | kľúč terminálu: `demo-kiosk-key` |
| Dokumentácia API | http://localhost:8000/api/docs | |

Vyskúšanie terminálu bez čítačky: na stránke `/kiosk` napíšte na klávesnici UID čipu a Enter,
napr. `04A11004B2C3D4` (J. Šimková). Demo čipy majú tvar `04A1` + osobné číslo + `B2C3D4`.

## 2. Testy

```bash
python -m pytest -q        # 26 testov: výpočty (noc, sviatky 2026/2027, prestávky, odpočinok) + API (roly, schvaľovanie, terminál, export, uzávierka)
```

## 3. Štruktúra projektu

```
backend/
  app.py      – REST API (prihlásenie, dochádzka, žiadosti, rozpis, správa, terminál, export)
  calc.py     – výpočet dochádzky (intervaly, nočná práca, sviatky, saldo, upozornenia podľa ZP)
  exports.py  – exporty CSV / XLSX / XML / JSON podľa profilov
  db.py       – databázová schéma (SQLite)
  seed.py     – číselníky, sviatky, exportné profily, demo firma
frontend/
  index.html, app.js, style.css – aplikácia pre zamestnancov, vedúcich, mzdy a správu (PWA)
  kiosk.html, kiosk.js, kiosk.css – terminál na stenu
  manifest.webmanifest, sw.js – inštalácia do mobilu / počítača
deploy/       – Docker, nginx (TLS), systemd, zálohovanie
tests/        – automatické testy
```

## 4. Nasadenie na interný server

1. IT pridelí server/VM (Linux, 2 vCPU, 4 GB RAM, 40 GB disk) v internej sieti a DNS meno, napr. `dochadzka.bid.sk`.
2. `cd deploy && docker compose up -d --build` (alebo systemd služba `bid-dochadzka.service`).
3. Certifikát vložte do `deploy/certs/` (fullchain.pem, privkey.pem).
4. Pri prvom štarte bez demo dát sa vypíše jednorazové heslo účtu `admin` (`docker compose logs app`).
5. Dostupnosť z internetu: publikovať **len** cez existujúcu reverznú proxy/WAF organizácie, s HTTPS;
   terminálové API (`/api/kiosk/`) povoliť len z internej siete.
6. Zálohy: kontajner `backup` robí dennú zálohu databázy do `deploy/backups/` (35 dní) – zahrňte ju do firemného zálohovania.

## 5. Nastavenie terminálu (tablet na stene)

1. Tablet Android + uzamykateľný držiak + USB čítačka 13,56 MHz (emulácia klávesnice) cez USB-C hub s napájaním (PD).
2. Admin vytvorí terminál v *Správa → Terminály* – zobrazí sa kľúč.
3. Na tablete otvorte `https://dochadzka.bid.sk/kiosk`, zadajte kľúč.
4. Zapnite kioskový režim (Fully Kiosk Browser alebo Android „pripnutie aplikácie“), vypnite uspávanie obrazovky.
5. Pri výpadku siete terminál ukladá záznamy lokálne (max. 72 h) a po obnovení ich odošle.

## 6. Prvé kroky v ostrej prevádzke

1. *Správa → Organizačná štruktúra*: vytvorte strom útvarov a vedúcich.
2. *Pracovné režimy*: pevný / pružný / zmenový (dispečing).
3. *Zamestnanci a účty*: osobné čísla (zhodné s mzdovým systémom), úväzky, čipy (priložiť k USB čítačke pri počítači), roly.
4. *Exportné profily*: podľa importnej šablóny mzdového systému (stĺpce, kódovanie, oddeľovač).
5. *Rozpis zmien*: vygenerujte cyklus pre dispečing.

## 7. Nasadenie na Render

**Dôležité:** Tento zdrojový projekt používa SQLite. Bezplatný Render web service nemá trvalý disk a pri reštarte alebo novom nasadení sa všetky zapisované údaje môžu stratiť. Pre dochádzku reálnych zamestnancov použite **platený web service s persistent diskom** (`render.yaml`) alebo aplikáciu pred nasadením prerobte na odolnú databázu s externým úložiskom. `render-preview.yaml` je výhradne na skúšanie.

1. Vytvorte GitHub repozitár `bid-dochadzka` a nahrajte zdrojový kód bez `.env`, databázy a hesiel.
2. V Render Dashboard vyberte **New → Blueprint**, pripojte repozitár a súbor `render.yaml`.
3. Pred schválením skontrolujte cenu webovej služby a persistent disku (náklad nie je nulový).
4. Po úspešnom štarte vyhľadajte v súkromných Render logoch riadok `*** Vytvorený admin, heslo: ... ***`. Pri prvom prihlásení je potrebné heslo zmeniť a aktivovať 2FA.
5. **Nespúšťajte `python -m backend.seed --demo` v ostrej prevádzke.** Demo prihlasovacie údaje v tomto README platia výhradne pre lokálnu demo databázu.
6. Pred spracovaním osobných údajov zabezpečte zálohovanie persistent disku mimo Render, kontrolu prístupov, správne nastavenie časov a bezpečnostné otestovanie terminálov a mobilných klientov.

Render používa `deploy/Dockerfile`, region `frankfurt`, zdravotnú kontrolu `/api/health` a databázu `/app/data/dochadzka.db`. Službu spúšťajte ako jednu inštanciu – SQLite nie je pripravené na horizontálne škálovanie.
