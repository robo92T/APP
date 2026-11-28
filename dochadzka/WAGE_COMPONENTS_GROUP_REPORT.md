# BID Dochádzka – hromadný výkaz: mzdové časové zložky

## Nové stĺpce v dennom aj mesačnom výkaze

| Stĺpec | Význam | Zdroj |
| --- | --- | --- |
| Lekár | Čas schváleného vyšetrenia / ošetrenia | Schválené voľno `doctor` alebo HR mzdový záznam |
| Sprevádzanie | Čas sprevádzania rodinného príslušníka | Schválené voľno `accompany` alebo HR mzdový záznam |
| Home office | Skutočný dokončený pracovný čas vykonaný z domu | Schválený home office + pípnutia, prípadne HR klasifikácia podľa pípnutí |
| Služobná cesta | Výslovne klasifikovaný pracovný čas na služobnej ceste | Mzdová klasifikácia HR (nie automaticky dĺžka cesty) |
| Služobné dôvody | Pracovné vybavovanie mimo obvyklého pracoviska – napríklad úrad, banka, iné miesto v meste | HR klasifikácia (celý deň/interval/pípnutia) |
| Trvanie cesty | Časový rozsah schváleného cestovného príkazu | Evidencia pracovných ciest; **nezapočítava sa automaticky ako odpracovaný čas** |

## Ako používať klasifikáciu

V `Hromadný výkaz` je nový panel `Mzdové zložky pracovného času`.

Personalistika vyberie zamestnanca, dátum, typ, pracovný dôvod a spôsob:
- **Celý pracovný deň** – použije individuálny plánovaný fond pre daný deň
- **Časový interval** – výslovne zadaný začiatok a koniec v jednom miestnom dni
- **Podľa dochádzkových pípnutí** – použije len dokončené odpracované intervaly daného dňa

Pre lekára a sprevádzanie sa v prednostnom poradí používajú existujúce
schválené údaje o prekážkach. Ručne zadané súbežné záznamy sa nezapočítajú
duplicitne.

Na deň možno pridať **niekoľko samostatných, neprekrývajúcich sa
časových intervalov** napríklad 08:00–09:30 lekár a
10:00–11:00 služobné vybavovanie. Celodenný záznam a režim podľa
pípnutí nie je možné s ďalším časovým úsekom kombinovať, keďže by
mohol vytvárať prekryv.

Každý nový záznam vyžaduje HR/admin účet a je auditovaný. Oprava
sa robí auditovaným stornom a novým záznamom; nemožno zasiahnuť
do globálne uzavretého ani individuálne potvrdeného mesiaca.

## Saldo a kontrola duplicít

- Existujúca dochádzka z pípnutí sa nemení.
- Záznam `podľa pípnutí` len klasifikuje skutočne odpracovaný čas a
  **nepripočítava ho druhýkrát**.
- Pri explicitnej celodennej alebo časovej zložke sa doplnkový
  kontrolný kredit obmedzí na zostávajúci fond po už odpracovaných
  a uznaných hodinách.
- Ak môžu mať intervaly obsahový prekryv s príchodom/odchodom,
  hromadný výkaz zobrazí upozornenie.
- Tieto doplnkové klasifikácie sú dnes zohľadnené v **hromadnom výkaze
  a jeho CSV/XLSX exporte**. Zatiaľ **nie sú prenesené do samostatného
  individuálneho PDF ani do finálneho mzdového exportu**. Preto
  finálna mzdová uzávierka vyžaduje kontrolu personálneho oddelenia.
- Stravné pracovnej cesty, dĺžka cestovania a hodinová klasifikácia
  práce sú oddelené veličiny.

## Právny režim

Pracovné dôvody mimo pracoviska nie sú automaticky pracovnou cestou
podľa § 2 zákona č. 283/2002 Z. z.; posúdenie závisí od
pravidelného pracoviska a konkrétnych okolností. Pri ceste
môže mať zamestnanec nárok na cestovné náhrady nezávisle
od spôsobu evidencie odpracovaných minút.

Návšteva lekára a sprevádzanie sa posudzujú podľa § 141
Zákonníka práce a interného režimu náhrady mzdy. Samotné
označenie `lekár` nesmie automaticky zmeniť právny nárok.

## Preview

Úplne fiktívni zamestnanci obsahujú aj demo zložky:
- Adam Demonštračný – služobná cesta podľa pípnutí (18.11.2026)
- Samuel Simulovaný – služobné vybavovanie 09:00–11:00 (19.11.2026)
- Bianka Neexistujúca – home office podľa pípnutí (20.11.2026)
- Filip Ukážkový – lekár (19.11.2026)
- Nina Testovacia – sprevádzanie (26.11.2026)

Údaje sú iba na ukážku; preview používa dočasnú SQLite.


## Aktualizácia v12 – presné rozdelenie práce a prekážok

**Odpracované minúty v hromadnom výkaze:** dokončené záznamy
príchod/odchod plus doplnková, schválená pracovná klasifikácia
`business_trip`, `service_errand`, `home_office` alebo
`training`. Do odpracovaných hodín vstupuje len ich pracovná
časť, ktorá ešte nie je započítaná pípnutím; práca podľa pípnutí
sa nepričítava druhýkrát. Evidencia cestovného príkazu bez klasifikácie
iba zobrazuje trvanie cesty a nikdy automaticky nevytvára odpracované hodiny.

**Uznané voľno (doplnenie fondu):** dovolenka, lekár, sprevádzanie,
platené pracovné voľno a ďalšie zložky, ktoré sú v legacy výpočte
evidované ako platené prekážky. Nie sú to odpracované hodiny.

**PN, OČR a ostatné neprítomnosti:** osobitné časové stĺpce
vrátane PN, OČR, materskej, otcovskej, rodičovskej, neplateného
voľna, neplateného lekára a sprevádzania, školení, svadby,
pohrebu, darovania krvi a inej neprítomnosti. PN/OČR
sa neklasifikujú ako odpracované ani ako bežné platené
voľno. Neprítomnosť sa uvádza v rozsahu plánovaného fondu
daného dňa, prípadne zadaných minút.

**Saldo:** odpracované + uznané voľno – fond. Ak klasifikácia
môže mať obsahový prekryv so záznamom pípnutia, systém upozorní
HR; odpracované i uznané minúty sú pri doplnení obmedzené
zostávajúcim plánovaným fondom. Nadčasy sa touto vrstvou
samostatne neschvaľujú.

V `Zobrazené stĺpce` sú voliteľne všetky vyššie uvedené
zložky v **dennom aj mesačnom** pohľade. Po zmene zostavy
sa používa nová verzia lokálneho výberu, aby sa nezdedil
starý zoznam s chýbajúcimi kategóriami.

**Oprava stavu prítomnosti:** sobotňajší alebo iný neskorší
deň nemá automaticky ukazovať „Na pracovisku“ z dlho
otvoreného starého pípnutia. Prítomnosť sa odvodzuje iba
z nedávneho záznamu. Pri neuzavretej dlhšej zmene sa však
musí vykonať personálna kontrola.

**Dôležitá hranica:** Hromadný výkaz a jeho CSV/XLSX používajú
upravené pravidlá, ale existujúce individuálne PDF a finálny
mzdový export ešte používajú starší samostatný výpočtový
modul. Rozdiely sa musia vyriešiť pred ostrými mzdami.
