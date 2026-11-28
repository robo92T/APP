# BID Dochádzka v10 – domácka práca, NFC/RFID, GPS a aktualizácie stravného

## Zamestnanecké rozhranie

Každý používateľ s priradeným `account.employee_id` má prístup výhradne
k vlastným údajom cez `/api/me/summary` a nové
`GET /api/me/attendance?year=2026&month=11`.
Zobrazuje sa mesačný súhrn, denné pípnutia, odpracované hodiny,
prestávky, fond, saldo, schválené zložky, žiadosti a vlastné PDF.
Účet musí na prvom prihlásení zmeniť dočasné heslo.

## Home office je PRÁCA, nie neprítomnosť

1. Zamestnanec požiada cez `Neprítomnosti → Home office` (organizačný
   typ žiadosti, ktorý nie je vyplatenou prekážkou).
2. HR alebo vedúci schváli konkrétne dni. Záznam `home_office`
   **sám nevytvára odpracované minúty**, nenahrádza pípnutia.
3. Iba v schválený kalendárny deň a s platným prihlásením možno
   použiť `Príchod → Prestávka → Koniec prestávky → Odchod`
   v zamestnaneckom portáli.
4. Udalosti sa zapisujú ako bežné dochádzkové pípnutia podľa
   **serverového času**, so zdrojom `home_office_web`.
5. Výkaz označí schválené dni ako `Home office`; čistý odpracovaný
   čas sa po uzavretom príchode/odchode premietne do fondu a salda.
6. V deň s >4 hodinami reálne vykonanej práce sa kontroluje
   štandardný nárok na stravovanie, bez automatického krátenia za
   samotnú prácu z domu.

**Riziká a obmedzenia:** Práca na diaľku je dovolená podľa dohodnutého
režimu, nie na základe samotného pípnutia. Web bez certifikovaného
zariadenia nedokáže garantovať prítomnosť zamestnanca pri počítači.
Nie je zavedená overená IP/VPN politika, biometria, hardvérové FIDO
ani plná prevádzková politika proti neoprávnenému pípnutiu. Obmedzenie
60 sekúnd medzi pípnutím a zákaz neplatnej postupnosti pôsobí iba
proti bežnej omylovej duplicite.

## Voliteľné GPS

Pri kliknutí na pípnutie môže zamestnanec *jednorazovo* povoliť GPS.
Prehliadač vypýta povolenie a pošle súradnice na server; server
overí iba štruktúru a rozsah, **nie polohu voči bydlisku**.
Žiadne GPS súradnice, adresa ani história pohybu sa neukladajú.
Audit poznamená len informáciu, že sa voliteľné údaje zadali.
Poloha sa nepoužíva na rozhodovanie o dochádzke ani na odmietnutie
pípnutia. GPS sa dá podvrhnúť a samotná lokácia nepreukazuje prácu.
V produkcii treba GDPR posúdenie, informačnú povinnosť a interný
predpis ešte pred prípadným povinným geofencingom.

Zdroje:
- https://www.ip.gov.sk/koronavirus-informacie/homeoffice-bozp-aktualizacia.html
- https://www.ip.gov.sk/vysielanie-zamestnancov/pracovny-cas-odpocinok/evidencia-pracovneho-casu/
- https://www.ip.gov.sk/koronavirus-informacie/stravovanie-zamestnancov-pocas-home-office.html
- https://www.dataprotection.gov.sk/files/metod-edpb/23_stanovisko_k_spracuvaniu_udajov_v_praci.pdf

## NFC a RFID

Administrátor / HR má novú časť v správe zamestnancov:
`Priradenie NFC/RFID`. Zvolí zamestnanca a UID čipu z:
- podporovaného Android Chrome cez **Web NFC** (`NDEFReader`),
  ktorý podporuje iba NDEF čipy a prehliadač musí UID sprístupniť
- USB RFID/NFC čítačky so správaním klávesnice (číta UID a Enter)
- ručne zadaného UID, ak čítačka zobrazí overený identifikátor.

`/api/hr/nfc/assign` vyžaduje rolu HR/admin, kontroluje unikátnosť
UID a každé priradenie auditne zaznamená. Pri kľúčoch používateľov
sa nepoužíva ako spôsob prihlásenia; klonovateľné UID **nie je heslo**.

Aj kiosk `/kiosk` má tlačidlo `Zapnúť NFC (Android)`.
Na bezpečnom kiosku sa vyžaduje **osobitný tajný kľúč zariadenia**,
nie iba UID. NFC zariadenie je potrebné spárovať, inak pípnutie
neprejde. Bežné 125 kHz RFID / MIFARE bez NDEF cez Web NFC
nefungujú; použije sa USB čítačka.

## Automatické sledovanie stravného

Monitor sleduje:
- novelizácie zákona č. 283/2002 Z. z. a zákonníka práce §152
- všeobecný zoznam článkov `NIP → Pracovné cesty`,
  aby zachytil aj budúce príspevky o novej sadzbe
- aktuálne oznámenie č. 255/2026 Z. z.
- informácie NIP o stravnom a kilometrovnom.

Pri zmene obsahového odtlačku dostane administrátor upozornenie.
**Nič sa nemení automaticky.** HR po overení predpisu zadá
návrh nových sadzieb a ich účinnosť. Administrátor ich musí
výslovne schváliť. Až potom backend použije platné schválené
referenčné hodnoty od stanoveného dátumu.

Parametre sú uložené v DB vo fixnej presnosti:
- `domestic_5_12_cents` / `domestic_12_18_cents` /
  `domestic_over18_cents` = **centy**, napr. 980 = 9,80 €
- `private_car_milleuro_km` = **tisíciny eura na kilometer**,
  napr. 313 = 0,313 €/km

Bežná minimálna poukážka sa odvodzuje ako 75 % z pásma 5–12 h
a príspevok zamestnávateľa ako 55 % z hodnoty poukážky
s požadovaným zákonným zaokrúhľovaním. Historické sadzby 2025
a do 30.11.2026 zostávajú v overenom rozvrhu, na novšie mesiace
sa použijú schválené hodnoty.

**Upozornenie:** Detekovaná zmena stránky ešte nie je novelizácia
účinného predpisu. Automatická kontrola na bezplatnom Renderi
nie je garantovaná každých 12 h, lebo server môže spať.

## Pred produkciou

Stále je nutné pripojiť trvalú PostgreSQL databázu,
automaticky zálohovať, otestovať obnovu, uzavrieť GDPR prevádzkové
postupy a vykonať bezpečnostné posúdenie mobilného pípnutia.
