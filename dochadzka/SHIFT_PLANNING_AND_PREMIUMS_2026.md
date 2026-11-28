# BID Dochádzka v15 – plánovač zmien, prestávky, saldo a príplatky

Implementácia na testovacej vetve `feature/sk-dochadzka`.
Právny základ: Zákonník práce 311/2001 Z. z. § 85–91, § 121–123,
§ 223, 226, 227 a 228a; MPSVR/NIP sumy minimálnych príplatkov na rok 2026.

## Prednastavené zmeny

| Režim | Čas prítomnosti | Prestávka | Plánovaný čistý čas |
| --- | --- | --- | --- |
| TPP | 08:00–16:30 | 30 min | 8 h |
| Dispečer denná | 06:00–18:00 | 60 min | 11 h |
| Dispečer nočná | 18:00–06:00 | 60 min | 11 h |
| Dispečer polzmena | 06:00–12:00 | 0 min | 6 h |
| Dispečer voľno | – | – | 0 h |
| Dohoda (ukážka) | 08:00–12:00 | 0 min | 4 h |

Zákon §91 vyžaduje minimálne 30 min prestávky pri zmene **dlhšej ako
6 hodín**. Hodinová prestávka dispečera je samostatné nastavenie
BID, nie všeobecné zákonné minimum.
Bežná prestávka nie je pracovným časom; výnimky pri
neprerušiteľnej práci a bezpečnostných prestávkach
sa musia posúdiť individuálne.

Výpočtové jadro `pdf_reports.build_rows` odpočíta **jednu**
automatickú prestávku z uzatvoreného súvislého pípnutia,
pokiaľ nie je evidovaný explicitný začiatok a koniec
prestávky. Pri obede zaznamenanom terminálom nedôjde
k druhému odpočtu. Pri cezpolnočných zmenách môže
syntetická prestávka pre kontrolný výkaz pripadnúť
približne na stred zmeny, pretože skutočný čas obeda
nebol zaznamenaný. Pre príplatky je lepšie mať skutočne
odpípaný čas obeda. Nezamieňaj orientačný odpočet za
dôkaz, že zamestnávateľ prestávku naozaj poskytol.

## Rozpis zmien

- **Zmeny a plán** obsahujú prednastavené profily,
  ručnú zmenu dňa, generátor cyklu D–N–V–V aj polzmeny.
- Ranná/nočná dispečera má 660 min čistého času
  po odpočítaní 60-minútovej prestávky.
- Cyklus nepredstavuje zákonné schválenie odpočinkov:
  pri plánovaní treba osobitne kontrolovať denné
  a týždenné odpočinky, nadčas a nerovnomerný čas.
- Plánovaný fond je čistý čas zo zmien;
  saldo závisí od spracovaných pípnutí, schválených
  neprítomností a mzdových klasifikácií.
- Mesačná uzávierka blokuje ďalšie bežné zmeny rozpisu.

## Rola plánovač zmien

Administrátor/HR môže založiť účet s rolou `scheduler`
v `Používateľské účty`.
Plánovač smie použiť `GET/POST /api/shifts`,
`POST /api/shifts/generate-cycle`,
`GET /api/shift-presets` a
`GET /api/scheduler/employees`.
Nesmie načítavať detailné HR profily ani mzdové a právne
agendy. Zatiaľ je rola na **celú spoločnosť**,
nie na konkrétny útvar. Také obmedzenie je potrebné
pridať pred delegovaním viacerým vedúcim.

## Dohody a pracovný fond

Nie je právne správne nastaviť každému dohodárovi
automaticky 40 hodín za týždeň. V profile zamestnanca
sú samostatné druhy:
- bežná dohoda o pracovnej činnosti: 10 h/týždenne
- brigádnická práca študentov: spravidla priemer 20 h/týždenne
- sezónna dohoda o pracovnej činnosti: najviac priemer
  40 h/týždenne za definované obdobie a ročný limit 520 h
- dohoda o vykonaní práce: ročný limit 350 h.

Typ dohody a limit musí HR porovnať s pracovnou zmluvou.
Pole týždenného fondu je konfigurovateľné; program upozorňuje
na niektoré neplatné kombinácie, ale nesleduje ešte súhrnné
ročné limity dohôd. Pokiaľ BID myslí *40 hodín mesačne*,
treba zvoliť tomu zodpovedajúce individuálne plánovanie.

## Zákonné príplatky 2026

Nové kontrolné rozhranie v sekcii `Zmeny a plán`
(`GET /api/premiums/{employee_id}`) vypočíta odpracované
minúty v kategóriách a zákonné štandardné **minimá**:

- noc: 2,1036 €/hod., pri rizikovej práci 2,6295 €/hod.
- sobota: 2,6295 €/hod.
- nedeľa: 5,2590 €/hod.
- sviatok: spravidla 100 % priemerného zárobku;
  zamestnávateľ musí zohľadniť náhradné voľno a výnimky.

Na výpočet sviatku musí HR doplniť priemerný hodinový
zárobok. Pri pravidelnej práci a zákonných výnimkách
môžu byť niektoré príplatky odlišné. Pri posúdení
soboty/nedele v nepretržitej prevádzke sa môže
uplatniť zákonné posunutie začiatku dňa podľa prvej
rannej zmeny – jednoduché kalendárne triedenie
vyžaduje kontrolu. Nadčasy, pracovná pohotovosť,
KZ, dohody a mzdové zložky sú mimo tohto
automatického zákonného minima. Systém preto
neúčtuje a neprenáša tieto čiastky do finálnych miezd
bez schválenia personalistikou.

Zdroje:
- https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/2001/311/20260901
- https://www.ip.gov.sk/pracovnopravne-vztahy/mzda/minimalna-mzda-minimalne-mzdove-naroky-roku-2026.html
- https://www.employment.gov.sk/sk/praca-zamestnanost/vztah-zamestnanca-zamestnavatela/odmenovanie/

## Zostávajúce úlohy pred produkciou

Trvalá PostgreSQL, otestovaná obnova zálohy,
súlad hromadného/individuálneho PDF/mzdového exportu,
mzdové pravidlá BID KZ, výnimky v nočných/víkendových
zmenách, ročné limity dohôd, detailné oddelené práva
plánovača podľa útvarov, integrovanejšie planovanie
odpočinkov a úplný bezpečnostný audit.
