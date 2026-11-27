# BID Dochádzka – právny monitor, schválené pravidlá a bezpečné zálohy

## Rozdelenie systémov

| Úložisko | Čo sa v ňom uchováva |
|---|---|
| GitHub (`feature/sk-dochadzka`) | Zdrojový kód, testy, popis pravidiel, CI |
| PostgreSQL | Zamestnanci, pípnutia, absencie, účty, schválenia legislatívy, záznamy auditu |
| Súkromný S3 bucket alebo spravované databázové zálohy | Šifrované obnoviteľné zálohy; NIKDY nie do verejného repozitára |
| Render Web Service | Spúšťanie kódu; nie trvalý adresár na ukladanie SQLite |

**Stav 27.11.2026:** kód podporuje PostgreSQL, ale existujúca databáza
`sk-dochadzka-db` je Render Free a expiruje 27.12.2026. Produkcia je
na SQLite a testovací Preview na separátnej SQLite. Na ostrú prevádzku
treba pripojiť platenú perzistentnú PostgreSQL so spravovanými zálohami;
cena a samotné zvýšenie plánu vyžadujú schválenie prevádzkovateľa.

## Zálohy

1. **Manuálna:** administrátor v `Uzávierka a export` klikne
   `Šifrovaná záloha dát`. Stiahne `.bidbak`, AES-256-GCM,
   PBKDF2-SHA256/600k, heslo min. 16 znakov. Prenos zvoleným
   dôveryhodným úložiskom mimo GitHubu.
2. **Automatická – pripravené rozhranie:** `backup_worker.py` sa
   aktivuje iba ak je PostgreSQL perzistentná a sú nastavené:
   `BACKUP_S3_BUCKET`, `AWS_REGION`, oprávnenie AWS IAM pre súkromný
   bucket, `BACKUP_ENCRYPTION_PASSPHRASE` min. 24 znakov a
   `BACKUP_SCHEDULER_ENABLED=true`. Predvolený stav je **vypnuté**.
   Záloha sa prenáša šifrovaná a po uložení sa späť načíta,
   skontroluje SHA-256 a autentifikované dešifrovanie.
3. **Ochrana zraniteľností:** pri spravovaných databázach sa musí
   zabezpečiť provider point-in-time recovery, retention politika,
   IAM least privilege, oddelený účet pre zálohy, audit a každoročný
   kontrolný restore test.
4. **Dôležitá hranica:** pravidelný interný scheduler beží iba keď
   server beží. Render Free sa môže uspať; nezaručuje presné denné
   zálohovanie. Pre produkciu použiť externý dôveryhodný plánovač
   a spravované PostgreSQL zálohy.
5. Obnova z manuálnej `.bidbak` má pripravený konzolový nástroj
   `restore_backup.py` pre prázdnu databázu. Pred každou migráciou
   sa má vykonať skúšobná obnova a prepočet vybraných výkazov.

Nikdy nevkladať `DATABASE_URL`, heslo zálohy, privátny API kľúč,
`.bidbak` ani údaje o zamestnancoch do GitHubu.

## Monitor legislatívy

Monitor sleduje nemenný zoznam piatich oficiálnych zdrojov:

- Zákonník práce 311/2001 Z. z. — Slov-Lex
- Zákon o štátnych sviatkoch 241/1993 Z. z. — Slov-Lex
- NIP: Pracovný čas a doba odpočinku
- NIP: Novinky v prekážkach od 1.1.2026
- NIP: Sviatky 8.5. a 15.9.2026

**Prvá kontrola** uloží referenčnú podobu stránky, nevytvorí falošnú
zmenu. **Ďalšie kontroly** porovnajú SHA-256 normalizovaného textu
a pri rozdiele vytvoria `legal_monitor_notice` s časom, oficiálnym
odkazom, predchádzajúcim a novým odtlačkom a informačným výňatkom.

Automatická kontrola sa pokúša vykonať každých 12 h, kým beží webový
server; administrátor môže spustiť kontrolu ručne. Na Free Renderi
nie je 12-hodinový termín garantovaný. Chyba oficiálneho zdroja sa
zobrazí, nie je interpretovaná ako zmena predpisu.

**Dôležité:** zmena HTML stránky, aktuality alebo článku ešte neznamená
novelu účinného zákona. Monitor neinterpretuje automaticky dátum
účinnosti, právne dôsledky alebo zmenu vzorcov.

### Riadené schvaľovanie

1. HR/administrátor otvorí `Monitor legislatívy`, skontroluje
   oficiálny zdroj a zobrazený rozdiel.
2. Vytvorí návrh len v povolenom rozsahu: `doctor_paid_days`,
   `escort_paid_days`, `escort_extra_days_max`.
3. Ručne zadá novú hodnotu, presný dátum účinnosti a právne zdôvodnenie.
4. Až po kliknutí administrátora **Potvrdiť** vznikne v DB
   `legal_rule_version`. Je uložené kto a kedy to schválil.
5. Výpočty referenčných nárokov použijú novú hodnotu až od
   schváleného dátumu účinnosti.
6. Zmenu možno zamietnuť. Najnovšiu schválenú hodnotu možno
   **vrátiť novou auditovanou verziou**, bez mazania histórie.

Nie je možná automatická editácia Python kódu, automatické nasadenie
z cudzieho textu ani svojvoľná zmena príplatkov alebo sviatkov.

### API a bezpečnosť

- `GET /api/legal-monitor/status`
- `POST /api/legal-monitor/check` (admin)
- `GET /api/legal-monitor/notices`
- `POST /api/legal-monitor/notices/{id}/review`
- `GET /api/legal-monitor/rules`
- `POST /api/legal-monitor/proposals`
- `POST /api/legal-monitor/proposals/{id}/approve` (admin)
- `POST /api/legal-monitor/proposals/{id}/reject` (admin)
- `GET /api/legal-monitor/history`
- `POST /api/legal-monitor/history/{id}/rollback` (admin)

Monitor používa fixné HTTPS hostiteľské domény, kontroluje presmerovania,
časový limit a rozsah odpovede. Cudzí HTML obsah sa parsuje ako text,
nie ako vykonateľný kód; frontend ho escapuje. Odkazy vedú len na
povolené domény.

## Pred produkciou

Zostáva preveriť odpovede oficiálnych webov (ochrana proti robotom),
integráciu s pravidlami kolektívnej zmluvy BID, dôveryhodnosť
monitorovacích termínov, ukladanie do platenej PostgreSQL,
denné zálohy do oddeleného úložiska, restore test, MFA,
penetračný test, GDPR a finálne právne schválenie mzdových pravidiel.
