# Render: trvalé úložisko dochádzky

## Podstatné pravidlo

**GitHub nie je databáza.** Zdrojový kód, testy a migračné skripty patria do
GitHubu; mená, dochádzka, RFID ID a heslá zamestnancov patria do súkromnej
PostgreSQL databázy. Neexportuj tieto údaje do repozitára.

Existujúci web: https://dashboard.render.com/web/srv-dc4t4us9v7es738a03v0
Existujúca databáza (frankfurt): `sk-dochadzka-db`
PostgreSQL ID: `dpg-dc4t4lp7lnhs739p29bg-a`

Aktuálna databáza má **plán Free a expiruje 27. decembra 2026**.
Render Free Postgres neposkytuje dlhodobú záruku uloženia. Pred používaním so
skutočnými osobnými údajmi treba zvoliť trvalý platený PostgreSQL plán
s automatickými zálohami. Neautorizované zvýšenie nákladov sa nevykonalo.

## Pripojenie PostgreSQL k existujúcej aplikácii

1. Na Renderi otvor existujúcu PostgreSQL `sk-dochadzka-db`.
2. Klikni **Connect** a skopíruj **Internal Database URL**.
   **Nikdy neposielaj túto URL cez chat, GitHub ani e-mail**; obsahuje heslo.
3. Otvor existujúcu službu `sk-dochadzka-portal` → **Environment**.
4. Existujúci `DATABASE_URL` zmeň zo `sqlite:////tmp/attendance.db`
   na skopírovanú **Internal Database URL**. Ulož.
5. Render reštartuje službu a SQLAlchemy vytvorí nové schémy v PostgreSQL.
6. Over `GET https://sk-dochadzka-portal.onrender.com/health`.
   Očakávané: `database=postgresql` a `persistent=true`.
7. Pre dlhodobé uchovanie ešte na DB aktivuj platený plán s uchovávaním záloh.
   Pred aktiváciou zisti cenu a schváľ ju.

**Dôležité k už existujúcim údajom:** zmena DATABASE_URL sama neprenesie
údaje z pôvodnej SQLite databázy. Pred prechodom stiahni šifrovanú zálohu
**Uzávierka a export → Šifrovaná záloha dát** a ulož si heslo na bezpečnom
mieste. V novej DB môžeš obnoviť zálohu cez `restore_backup.py` v
dôveryhodnom prostredí s prístupom k DB a následne overiť počet zamestnancov
a vzorku mesačných výkazov. Bez overeného exportu/obnovy nemanipuluj
s existujúcimi produkčnými dátami.

## Šifrovaná záloha a obnova

- API `POST /api/admin/backup` vyžaduje rolu admin a JSON
  `{"passphrase":"silné heslo aspoň 16 znakov"}`. Vracia `.bidbak`,
  šifrované AES-256-GCM, kľúč PBKDF2-SHA256/600k.
- Po každej významnej zmene a pred prepnutím DB ulož zálohu na dôveryhodné
  šifrované úložisko mimo GitHubu, a osobitne ulož obnovovacie heslo.
- Obnova: `DATABASE_URL="postgresql://..." python restore_backup.py záloha.bidbak`.
  Funguje **len na čerstvej databáze**, ktorá neobsahuje personálne záznamy.
  Požaduje výslovné potvrdenie a heslo bez zobrazenia v termináli.
- Toto je **manuálna**, nie automatická záloha. Pre produkciu treba automatické
  dennodenné zálohy, retenčnú politiku, periodický restore test, monitoring
  a incidentný proces. Správna odpoveď na stratu údajov nie je GitHub commit.

## Šablóna Render Blueprint

Pre neskoršie deklaratívne nasadenie je v tomto priečinku súbor
`render-persistent.yaml`, ktorý používa mechanizmus
`fromDatabase.property: connectionString`. **Nie je automaticky
aplikovaný na existujúcu službu** a pred prvou synchronizáciou
sa musia skontrolovať všetky existujúce environment premenné vrátane tajných
kľúčov. Preferovaná okamžitá oprava pre existujúcu službu je ručné nastavenie
`DATABASE_URL` podľa krokov vyššie.

## Rozvoj

Pred ostrou prevádzkou treba tiež MFA, politiky rolí pre celé podstromy
organizácie, validáciu pracovných fondov a príplatkov s mzdárkou,
plnohodnotnú uzávierku všetkých editácií vrátane RFID,
zabezpečené terminálové kľúče na zariadenie a penetračný test.
