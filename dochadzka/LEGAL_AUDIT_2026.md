# BID Dochádzka – právny a funkčný audit (27.11.2026)

Tento dokument odlišuje **overené pravidlá**, **technickú implementáciu** a
**nedokončené právne posúdenie**. Nejde o právne stanovisko. Interné kolektívne
dohody a pracovné režimy BID sa overujú samostatne.

## Overené pravidlá (oficiálne slovenské zdroje)

1. **Evidencia pracovného času – § 99 ZP**: zamestnávateľ musí evidovať
   presný začiatok a koniec pracovných úsekov, nadčas, nočnú prácu
   a aktívnu i neaktívnu časť pracovnej pohotovosti.
   NIP: https://www.ip.gov.sk/vysielanie-zamestnancov/pracovny-cas-odpocinok/evidencia-pracovneho-casu/
   **Stav:** príchody/odchody áno; evidencia pracovnej pohotovosti a schvaľovaného
   nadčasu ešte NIE je kompletná.
2. **Prestávka – § 91 ZP:** pri zmene dlhšej ako 6 h aspoň 30 min.
   Bežná prestávka nie je pracovným časom; ak je primeraný čas na jedlo
   zabezpečovaný bez prerušenia práce, započítava sa. Obyčajná automatická
   paušálna zrážka bez relevantného režimu nie je bezpečná.
   Zdroj: https://www.ip.gov.sk/ukrajina-ukrana/nepretrzity-denny-odpocinok-shhodennij-vdpochinok.html
   **Stav:** kontrolné upozornenia áno; konfigurácia platenej prestávky
   pre každú konkrétnu zmenu a previazaný mzdový výpočet ešte nie.
3. **Denný odpočinok – § 92:** referenčne aspoň 12 h, za zákonných
   podmienok možné skrátenie na 8 h; neexistuje univerzálna výnimka pre každého
   zamestnanca, ktorému je v systéme zvolený zmenový režim.
   **Stav:** upozornenia iba orientačné, výnimky treba schváliť HR.
4. **Lekár a sprevádzanie – § 141 ods. 2:** pracovné voľno na nevyhnutne
   potrebný čas, pri splnení zákonných podmienok platené štandardne
   najviac 7 dní za kalendárny rok pre vlastné vyšetrenie a sprievod
   rodinného príslušníka. Od 1.1.2026 je po splnení osobitných podmienok
   pri sprevádzaní dieťaťa do 15 rokov osamelým zamestnancom možných
   ďalších 7 platených dní – kumulatívne až 14.
   NIP: https://www.ip.gov.sk/pracovnopravne-vztahy/pracovny-cas-doba-odpocinku/novinky-prekazkach-praci-od-1-januara-2026.html
   **Stav:** osobitný limit 7+7 dní a HR schválenie áno, automatizované
   vyhodnocovanie individuálnych dokumentov a osobitných podmienok NIE.
5. **Sviatky 2026:** 8.5.2026 a 15.9.2026 nie sú dňami pracovného
   pokoja, ale zostáva mzdové zvýhodnenie za prácu v tieto sviatky;
   štandardný fond ich preto zahŕňa. 1.9., 28.10. a 17.11.
   sú v zákonom definovanom režime pracovnými dňami bez sviatočného zvýhodnenia.
   NIP: https://www.ip.gov.sk/pracovnopravne-vztahy/pracovny-cas-doba-odpocinku/sviatky-8-maj-15-september-2026-z-pohladu-pracovneho-prava.html
   Zákon: https://www.slov-lex.sk/ezbierky/pravne-predpisy/SK/ZZ/1993/241/20261029
   **Stav:** kalendár rozlišuje deň pracovného pokoja a sviatok na mzdové
   účely; vyplatenie zvýhodnenia musí byť potvrdené v mzdovom systéme.
6. **Práca nadčas – § 97:** saldo „+8 h“ NIE JE automaticky 8 h nadčasu.
   Dôležitý je príkaz/súhlas a práca nad rozsah určeného rozvrhu, vrátane
   pravidiel rozpočítania. **Stav:** žiadne automatické uznanie nadčasu.
7. **Dovolenka:** zákonná základná výmera a rozšírený nárok vyplývajú z § 103
   a ďalších ustanovení ZP; pomerný nárok, krátenie, minuloročný prenos a
   individuálne rozvrhy treba rátať od prípadu k prípadu.
   **Stav:** HR zadaný nárok, čerpanie a orientačný zostatok;
   automatické schvaľovanie nároku bez HR sa nesmie používať.
8. **Kontrolný mechanizmus a GDPR:** zodpovedná osoba musí pred ostrou
   prevádzkou preveriť potrebu prerokovania so zástupcami zamestnancov
   podľa § 13 ods. 4 ZP, informovanie podľa čl. 13 GDPR, prístupové roly,
   dobu uchovávania, práva dotknutých osôb a posúdenie vplyvu, ak je potrebné.

## Čo prevzaté zo ZIP-u funguje alebo bolo doplnené

- strom útvarov s vedúcim, zástupcom, strediskom; prístup do podstromu
- individuálne terminálové kľúče, ochrana opakovaného pípnutia, odosielanie
  offline fronty do 72 h
- fiktívni zamestnanci a rozpis dispečingu 24/7 pre testovanie
- konfigurovateľné exportné profily CSV, XLSX, JSON, XML; kódy sú pripravené
  na prispôsobenie až po získaní šablóny mzdového softvéru
- mesačné PDF, audit operácií a doplnkové kontroly dochádzky.

## Dôležité zostávajúce nedostatky

- NEDOKONČENÉ: trvalé produkčné PostgreSQL s automatickými zálohami,
  verifikovaná obnova pri incidente a migrácia starej SQLite databázy
- NEDOKONČENÉ: právne schválenie individuálnych pracovných režimov a
  kompletných mzdových zložiek, schvaľovanie nadčasov, pracovná pohotovosť
- NEDOKONČENÉ: komplexná oprava pípnutí s nezmeniteľnou auditnou stopou,
  lock všetkých historických úprav a individuálna evidencia break-paid
- NEDOKONČENÉ: penetračný test, bezpečnostný audit kódu, integrita
  offline času terminálov, ochrana proti klonovaniu bežných RFID UID
- NEDOKONČENÉ: automatické zálohy so 7/30/90 dennou retenciou,
  overené disaster recovery, monitoring, GDPR procesy a prístupové protokoly.

## Dátové úložisko

GitHub slúži na zdrojové kódy, migrácie a CI. **Nie je vhodnou databázou
osobných údajov.** Pre ostrú prevádzku je nutná perzistentná PostgreSQL
s riadnymi zálohami. Render Free PostgreSQL, založená 27.11.2026,
exspiruje 27.12.2026. Ani šifrovaný export na GitHub nie je náhradou
riadeného bezpečného zálohovania.

Fiktívny testovací dataset sa vytvorí len keď súčasne platí:
`APP_ENV=preview`, `DEMO_SEED=10`, SQLite a prázdna tabuľka zamestnancov.
Nikdy sa nesmie zapínať na produkcii.
