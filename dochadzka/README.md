# SK Dochádzka — slovenský dochádzkový systém

**Stav: vývojové MVP / API prototyp. Nie je pripravené na ostrú prevádzku ani na spracúvanie reálnych osobných údajov.** Projekt vznikol ako samostatný adresár `dochadzka/` v repozitári APP na vetve `feature/sk-dochadzka`. Inspirácia rozsahom funkcionality profesionálnych riešení (napr. Aktion), bez prevzatia ich kódu ani dizajnu.

## Rýchle spustenie (lokálne)
```bash
cd dochadzka
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
export ADMIN_API_KEY='nahodny-dlhy-admin-kluc'
export TERMINAL_API_KEY='iny-nahodny-terminal-kluc'
uvicorn main:app --reload
```
API dokumentácia: http://127.0.0.1:8000/docs . Hlavička na admin endpointoch: `X-Admin-Key`; na termináli: `X-Terminal-Key`. Neukladajte kľúče do GitHubu, nezapínajte `--reload` v produkcii. V SQLite sa databáza vytvorí pri prvom spustení.

## Už implementované
- Zamestnanci, úväzok, referenčný počet pracovných dní, dátum nástupu, RFID UID karty.
- Raspberry Pi/USB RFID čítačka fungujúca ako HID klávesnica; cez HTTP API odosiela UID.
- Príchod, odchod, prestávka, ochrana pred dvojitým pípnutím do 10 sekúnd, nezatvorené udalosti ako upozornenia.
- Žiadosť o neprítomnosť, schválenie, audit udalostí.
- Základný prehľad odpracovaných minút; informatívne ročné čerpanie dovolenky, lekára a sprevádzania.
- Kalendár názvov slovenských sviatkov z knižnice holidays. **Pozor:** knižnica sama o sebe nesmie určovať zákonný pracovný fond: 1. september a 17. november sú pracovnými dňami a v roku 2026 aj 8. máj a 15. september. Výpočet pracovných dní v aktuálnom MVP nie je preto právne spoľahlivý; pred nasadením ho nahradí vlastný verzovaný kalendár výnimiek.
- Neprítomnosti: dovolenka, lekár, sprevádzanie, neplatený lekár, neplatené sprevádzanie, PN, OČR, materská, otcovská, rodičovská, neplatené/platené voľno, služobná cesta, školenie, svadba, pohreb, darovanie krvi a iné.

## Raspberry Pi
Pripojte USB RFID/NFC čítačku s HID/keyboard emuláciou (posiela UID a Enter). Skontrolujte formát UID, oddelenie kľúčov, fyzické zabezpečenie a HTTPS alebo VPN. Na Pi nainštalujte Python 3, skopírujte `raspberry_pi/terminal.py` a spustite:
```bash
export ATTENDANCE_URL='https://dochadzka.example.sk'
export TERMINAL_API_KEY='samostatny-terminal-kluc'
export DEVICE_ID='vstup-hlavny'
python raspberry_pi/terminal.py
```
Tento prototyp nemá offline queue, deduplikáciu udalostí po odpojení ani kryptograficky silné karty; jednoduché UID možno skopírovať. Pri produkcii použiť bezpečné RFID/NFC médium a dôveryhodný terminál.

## Vzor API
1. POST `/api/employees`: `{"name":"Test","card_uid":"AABBCC","start_date":"2026-01-01","weekly_minutes":2400,"work_days":5,"annual_leave_weeks":5}`
2. POST `/api/terminal/punch`: `{"card_uid":"AABBCC","device_id":"recepcia","kind":"toggle"}`
3. POST `/api/absences`: `{"employee_id":1,"kind":"doctor","start":"2026-11-27","end":"2026-11-27","minutes":120}`
4. POST `/api/absences/1/approve`
5. GET `/api/timesheet/1?start=2026-11-01&end=2026-11-30`
6. GET `/api/balances/1/2026`

## Rozsah cieľového systému (roadmap)
### Pracovný čas
- Individuálne a hromadné rozpisy, pevná/pružná/zmenová prevádzka, 37,5/38,75/40 h, čiastočné úväzky, delené zmeny, nočné a cezpolnočné smeny, home office, pohotovosť, služobné cesty.
- Fond pracovného času vypočítaný zo zmien a zákonných dní pracovného pokoja, kladné/záporné saldo, prenášanie salda, nadčas a jeho schválenie, náhradné voľno, zaokrúhľovanie a tolerancie, zákonné prestávky a minimálne odpočinky; upozornenia na porušenie pravidiel.
- Nezmazateľná pôvodná stopa pípnutí, korekcie s dôvodom, verzovaním a schvaľovaním, zamykanie mesačnej uzávierky.
### Práva a HR
- Zamestnanec / vedúci / personalista / mzdár / admin / audítor; SSO/OIDC a MFA, oddelené tenanty; podpis a schvaľovanie viacúrovňových žiadostí, zastupovanie, delegovanie.
- Ročné nároky, prenos dovolenky, dodatková dovolenka, krátenie a pomerná časť, zmeny veku, starostlivosť o dieťa, zmena rozvrhu, nástup/výstup počas roka.
- Lekár a sprevádzanie podľa §141 (nevyhnutne potrebný čas, samostatné platené a neplatené čerpanie, zákonný rozsah 7 dní), osobitný nárok pri dieťati do 15 rokov osamelého zamestnanca účinný od 2026, iné osobné prekážky a kolektívne výhody.
- Bezpečné prílohy/potvrdenia s minimalizáciou zdravotných údajov, retention a prístupové politiky.
### Rozhranie a integrácie
- Responzívny dashboard, mesačný kalendár, tímová prítomnosť, samoobsluha, grafy, vyhľadávanie, notifikácie email/push.
- Raspberry Pi RFID/NFC, QR/virtuálna karta, viac terminálov, offline queue, presná synchronizácia času, idempotentné odoslanie, správa zariadení.
- CSV/XLSX/PDF export do miezd, účtovných systémov, REST/webhook, plánované prehľady, zálohovanie a disaster recovery.
### Pred ostrým nasadením — povinné
- Rozšíriť autentifikáciu (aktuálne iba zdieľané kľúče), hash/rotácia kľúčov, per-device scope, RBAC, TLS, anti-replay, rate limits, testy, migrácie databázy, Postgres, logging a monitoring.
- Implementovať plán zmien a z neho odvíjať saldo, prácu počas sviatkov, prestávky a nadčasy; toto **zatiaľ nie je implementované**.
- Pravidlá dovolenkových nárokov a prekážok v práci treba dokončiť a právne otestovať: dnešné výpočty sú **iba orientačné** a nevystavujú automaticky správny ročný nárok pri skrátených alebo nerovnomerných rozvrhoch.
- GDPR DPIA podľa potreby, interné pravidlá a informačné povinnosti, výmaz/archivácia, prístupové práva, audit korekcií.
- Vzorkové a hraničné testy: 2026 sviatky, zmena času, prestupný rok, cezpolnočná zmena, PN, zmeny úväzku, nástup počas roka, špeciálne nároky.

## Právne zdroje, ktoré treba verzovať
- Zákonník práce 311/2001 Z. z. § 99, § 103 a nasl., § 141: https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/2001/311/
- Zákon 241/1993 Z. z. o štátnych sviatkoch: https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/1993/241/
- NIP zmeny v sprevádzaní od 2026: https://www.ip.gov.sk/pracovnopravne-vztahy/pracovny-cas-doba-odpocinku/novinky-prekazkach-praci-od-1-januara-2026.html
- NIP 8. máj a 15. september 2026: https://www.ip.gov.sk/pracovnopravne-vztahy/pracovny-cas-doba-odpocinku/sviatky-8-maj-15-september-2026-z-pohladu-pracovneho-prava.html

Žiadna časť tohto prototypu sa nesmie považovať za právne alebo mzdové posúdenie konkrétneho zamestnanca.
