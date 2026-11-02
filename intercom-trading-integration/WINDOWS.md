# Windows: test complet n8n → Gmail → Google OIDC → simulare

## Diagnosticul problemei

**Intercom Guard nu este un produs pe care n8n îl instalează.** Este serviciul Python creat în acest proiect, sub `intercom-trading-integration/`. Importul unui workflow nu instalează/pornește serviciile și nu creează variabilele `$vars` sau credențialele.

În repository-ul inspectat NU există Dockerfile/compose pentru această integrare. Varianta simplă de mai jos folosește Python nativ pe Windows; nu instalează Docker, nu creează reguli de firewall și nu expune servicii publice. Nu am verificat ce software rulează efectiv pe laptopul tău.

Fișiere:

| Fișier | Rol |
| --- | --- |
| guard.py | Propuneri SQLite, limite, expirare, dovezi de aprobare, revalidare sintetică; LIVE blocat. |
| server.py | API Guard pe 127.0.0.1:8765, autentificat cu X-Guard-Key. |
| oidc.py / oidc_server.py | Login Google, cont autorizat și confirmare explicită pe localhost:8766. |
| runtime_config.py | Amprentă opacă pentru a verifica aceeași configurație în cele două servicii. |
| windows_setup.py / Start-Windows.ps1 | Configurare, instalare dependențe, pornire și verificări automate Windows. |
| requirements.txt | PyJWT[crypto]==2.13.0; restul serviciului folosește biblioteca standard Python. |
| intercom_dex_WINDOWS_SANDBOX.json | Workflow complet pentru testul de pe Windows, fără `$vars` și fără OpenAI. |

## Ce se schimbă în workflow

Sunt exact trei HTTP nodes Guard:

| Nod | Apel |
| --- | --- |
| Guard - synthetic market ONLY | GET /v1/markets; date sintetice și emailul aprobatorului din setup. |
| Guard - persist immutable proposal | POST /v1/proposals; scriere locală în SQLite, fără efect DEX. |
| Guard - read decision | GET /v1/proposals/{proposal_id}; citește starea la fiecare 5 secunde. |

Toate folosesc URL-ul din singurul nod **Local sandbox configuration**, nu `INTERCOM_GUARD_BASE_URL` sau alte `$vars`. `check` poate genera automat o copie a workflow-ului cu URL-ul potrivit, inclusiv când detectează și poate verifica n8n în Docker.

Varianta Windows generează o propunere deterministă BUY TNK/USDC de 5 USDC, plus 0.01 USDC comision sintetic. Nu depinde de disponibilitatea unui model AI sau de decizia WAIT și nu cere o credențială OpenAI. Este testarea transportului și aprobării, NU o recomandare de tranzacționare. Fluxul original de analiză AI rămâne în `intercom_dex_GMAIL_OIDC_SANDBOX.json`, neschimbat. Simularea offline V2 cu cele 18 scenarii este de asemenea neschimbată.

Emailul conține linkul local, fără token de aprobare. Google verifică identitatea, apoi pagina cere POST explicit pentru aprobare/refuz. Confirmarea recitește piața sintetică, verifică digestul, expirarea, reutilizarea și limitele. n8n observă SIMULATED, REJECTED sau EXPIRED. GET/login/deschiderea linkului nu aprobă.

## Pași exacți pe Windows

### 1. Descarcă și deschide directorul corect

Descarcă ZIP-ul branch-ului `feat/intercom-trading-integration-oidc` din GitHub, extrage-l și deschide PowerShell în subdirectorul **intercom-trading-integration** care conține `Start-Windows.ps1`.

Instalează Python 3.10+ de pe python.org cu Python Launcher. Verifică o singură dată:

```powershell
py -3 --version
```

### 2. Creează clientul Google OIDC, dacă nu există deja

Conectarea Gmail în n8n NU configurează autentificarea aprobatorului.

În Google Cloud / Google Auth Platform, creează un client **Web application** separat. Configurează aplicația pentru contul tău; dacă este în Testing/External, adaugă adresa ta ca test user. Redirect URI exact:

```text
http://localhost:8766/oidc/callback
```

Serviciul cere numai scope-urile `openid email`, nu acces Gmail sau refresh tokens. Clientul Gmail existent în n8n rămâne neschimbat. Referință: https://developers.google.com/identity/openid-connect/openid-connect .

### 3. Rulează setup o singură dată

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-Windows.ps1 setup
```

Scriptul cere adresa Google, Client ID și Client Secret (input ascuns). Generează independent cheia API Guard și cheia internă pentru receipt, creează un venv și instalează `requirements.txt` cu TLS activ. Nu cere și nu folosește chei de wallet.

Configurația este criptată cu **Windows DPAPI pentru utilizatorul Windows curent**, în:

```text
%LOCALAPPDATA%\IntercomTradingSandbox\config.dpapi
```

Baza comună este `%LOCALAPPDATA%\IntercomTradingSandbox\guard.sqlite3`. Nu există secrete în cod, JSON-ul workflow-ului sau repository. Nu copia fișierul DPAPI în GitHub; nu este portabil la alt utilizator/alt calculator. Un nou setup nu suprascrie configurația existentă și nu rotește cheile în tăcere. La eroare pip, remediază accesul PyPI și reia setup; nu dezactiva TLS.

### 4. Pornește serviciile și fixează identitatea

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-Windows.ps1 start
```

Se deschid două ferestre PowerShell, Guard și OIDC. Păstrează-le deschise. În browserul aceluiași laptop deschide:

```text
http://localhost:8766/oidc/setup
```

Autentifică-te cu adresa autorizată. Pagina afișează identificatorul Google `sub`; nu aprobă nimic. Rulează în fereastra inițială:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-Windows.ps1 pin
```

Lipește identificatorul afișat. Oprește AMBELE procese cu Ctrl+C în cele două ferestre și rulează `start` din nou. Acest pas fixează explicit identitatea; nu există înscriere automată a unui aprobator.

### 5. O singură verificare automată a serviciilor

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-Windows.ps1 check
```

Verifică automat:
- Guard și OIDC disponibile, SANDBOX și LIVE OFF;
- aceeași configurație salvată în launcher și în ambele procese (DB, identitate și chei);
- configurarea și pin-ul Google, fără să pretindă că prezența lor dovedește login-ul real;
- GET market, POST proposal, GET decision — contractele celor trei noduri;
- refuzul persistent al propunerii de diagnostic, fără nicio aprobare fabricată;
- prezența endpointului n8n de pe host și, când detectează un singur container n8n standard, conectivitatea din acel container.

Crearea propunerii de diagnostic produce o înregistrare REJECTED în SQLite; nu trimite Gmail, nu consumă un trade simulat și nu contactează DEX. Raportul spune explicit că login-ul Google și livrarea Gmail NU sunt verificate de `check`.

La succes scrie fișierul de import configurat automat:

```text
%LOCALAPPDATA%\IntercomTradingSandbox\intercom_dex_WINDOWS_SANDBOX.json
```

Dacă serviciile au configurații diferite, `check` se oprește. Repornește AMBELE prin launcher; nu reconfigura fiecare nod.

### 6. O singură credențială Guard în n8n

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-Windows.ps1 copy-key
```

Cheia este copiată în clipboard fără a fi afișată în consolă. În n8n creează o credențială **Header Auth**, numită de exemplu `Intercom Guard Local`:

- Name: `X-Guard-Key`
- Value: lipește cheia din clipboard.

Nu este un Bearer token și nu este Client Secret Google. După salvare golește clipboardul (`Set-Clipboard -Value ''`; șterge și istoricul Win+V dacă este activ).

Importă fișierul Windows generat la pasul 5 ca workflow nou/separat, dezactivat. Selectează **aceeași credențială Guard** în cele trei HTTP nodes și credențiala Gmail deja conectată în nodul Gmail. Nu trebuie să refaci conexiunile, codul sau variabilele și nu ai nevoie de OpenAI pentru acest test.

Adresa destinatarului este cea configurată o dată în setup, întoarsă de Guard; nu mai este necesar `$vars.INTERCOM_APPROVER_EMAIL` sau schimbarea individuală a adresei în fiecare nod. O importare JSON nu poate instala sau selecta automat ID-urile credențialelor private din instanța ta n8n; această asociere inițială este necesară.

### 7. Testul complet

Executează manual workflow-ul Windows de la Start manual. Primești propunerea de test în Gmail. Pe același laptop, deschide linkul, autentifică-te cu contul fixat, verifică propunerea și aprobă explicit **numai simularea**. Rezultatul trebuie să fie:

```text
state: SIMULATED
result.status: SIMULATED_LIMIT_ORDER_ONLY
order_sent: false
live_enabled: false
```

Refuzul dă REJECTED; lipsa aprobării în 120 secunde dă EXPIRED. Dacă expiră, creează o propunere nouă; nu prelungim automat și nu reutilizăm aprobarea. Aprobările au maximum 3 simulări și 20 USDC expunere brută/24h, în plus față de 10 USDC per propunere cu comisionul modelat inclus. Nu șterge baza pentru a ocoli un refuz de limită.

Închide procesele numai după finalizarea testului; următoarea pornire reutilizează configurația și SQLite. Nu se pornesc automat la boot.

## Dacă n8n este în Docker pe Windows

Accesul browserului la `localhost:5678` nu dovedește instalare nativă; poate fi un port de container. Din container, `localhost:8765` NU este hostul Windows.

`check` încearcă să detecteze un singur container care are `n8n` în imagine și să verifice `host.docker.internal:8765` chiar din el, cu cheia trimisă pe stdin, nu în argumente sau loguri. Dacă reușește, exportul generat folosește automat `http://host.docker.internal:8765`. Linkul din Gmail rămâne `http://localhost:8766` pentru browserul laptopului.

Dacă sunt mai multe containere candidate sau conexiunea este refuzată, scriptul se oprește explicit: nu expune Guard pe 0.0.0.0, nu deschide firewallul și nu schimbă Docker/n8n. Configurația de rețea Docker Desktop trebuie atunci verificată local; este o limitare reală care nu poate fi diagnosticată exclusiv din GitHub. Dacă instalarea n8n folosește o imagine cu alt nume, detectarea automată nu o recunoaște. Raportul de pe host nu este o garanție pentru un runtime-container nedetectat.

Nu este inclusă o configurație Docker în această versiune: alegerea intenționată pentru pornirea simplă este Python nativ, cu un probe explicit pentru n8n dacă acesta este deja în Docker.

## Ce pot verifica din cod și ce rămâne local

Din repository și mediul de test: fișiere/dependențe, lipsa Docker/compose, cele trei rute, expresiile JSON, autentificarea Header Auth, rutarea Gmail/OIDC, cheile/digestul/expirarea, testele automate și blocarea LIVE. Am rulat 71 teste trecute și 1 test Windows DPAPI omis pe Linux; harness-urile JavaScript pentru noul export și V2 au trecut. Verificarea DPAPI portabilă folosește un mock; nu este dovadă de execuție Windows reală.

Numai pe laptop: Python/PowerShell și Windows DPAPI reale, accesul pip/Google, pornirea proceselor, adresele de rețea n8n, credențialele private, acceptarea redirectului Google, login-ul cu contul tău și livrarea Gmail. Launcher-ul `check` automatizează partea tehnică locală; login-ul Google și decizia umană nu sunt și nu trebuie automatizate.

Nu pot deduce din importul workflow-ului că Guard este instalat sau activ pe laptop. Nici o reușită a acestor teste nu activează tradingul real. Conectorul DEX, reconcilierea efectelor ambigue și limitele reale de poziție/P&L rămân de finalizat separat înainte de orice autorizare LIVE.
