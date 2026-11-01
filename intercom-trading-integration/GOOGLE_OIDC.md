# Configurare Gmail + Google OIDC pe laptop

## Cum funcționează versiunea curentă

n8n trimite prin Gmail propunerea și linkul `http://localhost:8766/approve?proposal_id=...`. Linkul nu conține token de aprobare sau secret. Pe același laptop, browserul te autentifică prin Google, apoi afișează conținutul exact și două butoane POST: aprobă numai simularea / respinge. GET-ul inițial, scanarea emailului și autentificarea NU aprobă nimic.

Serverul verifică tokenul Google cu cheile publice Google, RS256, issuer, audience, authorized party, expirare, momentul emiterii, email verificat și nonce; fluxul folosește state, PKCE S256 și cookie HttpOnly/SameSite=Lax legat de browser. Confirmarea mai cere Origin exact și token CSRF, consumă sesiunea o singură dată și leagă decizia de digestul propunerii. Emailul autorizat și identificatorul Google `sub` trebuie să corespundă. După POST se recitește piața prin guard și se aplică limitele. În acest build piața și rezultatul sunt sintetice, iar ordinul real este imposibil.

Nicio soluție nu poate garanta „nimeni altcineva” dacă este compromis contul Google, browserul sau sistemul de operare. Activează passkey/2-Step Verification la Google și blochează laptopul. Un destinatar căruia i se redirecționează emailul, autentificat cu alt cont, este refuzat. Nu este cerută o nouă introducere a parolei Google la fiecare tranzacție: o sesiune Google deja autentificată poate fi folosită; confirmarea explicită a propunerii este însă obligatorie.

## 1. Google Cloud / Google Auth Platform

- Creează sau selectează un proiect Google Cloud. Creează o aplicație OAuth pentru uzul tău.
- Configurează branding/consent și audience. Pentru un cont Gmail personal folosește External; cât aplicația este în Testing, adaugă doar propriul cont ca test user. Dacă folosești Workspace, politica organizației poate impune alte setări.
- Creează un client OAuth de tip **Web application**, separat de credențialele Gmail deja existente în n8n.
- Adaugă exact **Authorized redirect URI**: `http://localhost:8766/oidc/callback`.
- Acest client cere numai `openid email`. Nu cere acces Gmail, offline access sau refresh token. Nu are nevoie de JavaScript origins pentru fluxul server-side implementat.
- Păstrează Client ID și Client Secret în configurația locală a serviciului. Nu le trimite în chat și nu le pune în JSON-ul workflow-ului.

Endpointurile fixe utilizate: `https://accounts.google.com/o/oauth2/v2/auth`, `https://oauth2.googleapis.com/token`, JWKS `https://www.googleapis.com/oauth2/v3/certs`. Verificarea TLS rămâne activă. Dacă laptopul are o politică de egress, acestea sunt destinațiile necesare. Nu au fost apelate cu credențiale reale în mediul Codex.

Referință Google: https://developers.google.com/identity/openid-connect/openid-connect . Configurarea OAuth reală și acceptarea redirectului trebuie verificate în proiectul tău Google; Codex nu a accesat consola ta.

## 2. Configurația locală

Python 3.10+ și dependența din `requirements.txt`. În directorul pachetului:

```sh
python -m venv .venv
# Linux/macOS:
. .venv/bin/activate
# Windows PowerShell, alternativ:
# .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Variabile de mediu (setează-le local, fără valori în chat):

| Variabilă | Utilizare |
| --- | --- |
| TRADING_GUARD_DB | **Aceeași cale absolută** către SQLite pentru ambele servicii. Obligatoriu de stabilit explicit în această configurație; nu folosi două fișiere diferite. |
| TRADING_GUARD_API_KEY | Secret random independent, minimum 32 caractere; doar n8n și guard. |
| TRADING_APPROVAL_RECEIPT_KEY | Alt secret random, minimum 32 octeți; doar cele două servicii, niciodată n8n sau modelul AI. |
| TRADING_APPROVER_EMAIL | Adresa ta Google exactă, autorizată pentru aprobare. |
| TRADING_GOOGLE_CLIENT_ID | Client ID de la pasul 1. |
| TRADING_GOOGLE_CLIENT_SECRET | Client Secret de la pasul 1. |
| TRADING_GOOGLE_SUB | Se completează la pasul 3; inițial absent. |
| TRADING_GUARD_HALT_FILE | Opțional, cale absolută către fișierul de oprire; implicit `<DB>.halt`. |

Generează două valori random distincte local într-un manager de secrete/parole. Nu reutiliza tokenul DEX sau parola walletului. Configurează acces restrictiv pentru director, SQLite și variabile/fișierele de configurare. Serviciile setează umask 077 la creare pe POSIX. Un fișier `.env` nu este încărcat automat de aceste scripturi; variabilele trebuie exportate în proces sau injectate de managerul local de servicii.

## 3. Fixează identitatea Google înainte de prima aprobare

1. Cu variabilele de mai sus configurate, dar fără TRADING_GOOGLE_SUB, pornește `python oidc_server.py`.
2. Pe același laptop deschide `http://localhost:8766/oidc/setup` și autentifică-te cu adresa autorizată.
3. Pagina afișează `sub` din tokenul verificat. Copiază-l local în TRADING_GOOGLE_SUB. Acest pas nu aprobă propuneri și nu înscrie automat vreun cont.
4. Oprește și repornește serviciul OIDC cu valoarea fixată. Pornește `python server.py` într-un al doilea proces, cu aceeași bază SQLite, aceeași cheie de receipt și același TRADING_GOOGLE_SUB. Nu mai folosi vechiul TRADING_APPROVER_ID pentru configurația nouă.

Serviciile ascultă exclusiv pe `127.0.0.1:8766` (browser/OIDC) și `127.0.0.1:8765` (guard/n8n). Folosește **localhost** în browser, exact ca URI-ul înregistrat; Host `127.0.0.1:8766` este refuzat intenționat de pagina OIDC. HTTP și cookie fără Secure sunt limitate la loopback în acest build. Nu expune aceste porturi public și nu adăuga tunel pentru aprobare: pentru acces de pe telefon sau de la distanță este necesară o variantă HTTPS, redirect nou și cookie Secure configurate și testate separat.

## 4. n8n local

- Verifică versiunea prin `n8n --version`. Dacă rulează în Docker: `docker exec <numele-containerului-n8n> n8n --version`. Nu presupune că portul 5678 identifică versiunea sau metoda de instalare.
- Importă **intercom_dex_GMAIL_OIDC_SANDBOX.json** ca workflow NOU, dezactivat.
- Alege credențialele Gmail și OpenAI existente. Pentru Gmail se folosește trimitere de email, nu `sendAndWait`. Credentialele Gmail din n8n au propriul callback; nu le înlocui cu clientul OIDC al aprobărilor.
- Setează variabilele n8n `INTERCOM_APPROVER_EMAIL` cu aceeași adresă și `INTERCOM_GUARD_BASE_URL` cu URL-ul guard-ului, fără slash final. Dacă `$vars` nu este disponibil în ediția ta, în copia importată înlocuiește doar aceste expresii cu valori non-secrete configurate explicit.
- Pentru fiecare HTTP Request setează Header Auth: numele headerului `X-Guard-Key`, valoarea secretă TRADING_GUARD_API_KEY. Nu pune cheia în URL sau Code nodes.
- Dacă n8n rulează direct pe laptop: URL-ul este `http://127.0.0.1:8765`.
- Dacă n8n rulează în Docker, localhost-ul containerului nu este laptopul; simpla utilizare `host.docker.internal` poate fi insuficientă fiindcă guard-ul ascultă numai pe loopback. Pe Linux poate fi folosit host networking, dacă este disponibil; pe Docker Desktop trebuie o cale locală autentificată și testată către host, fără expunere publică. Configurația exactă depinde de instalare și nu a fost presupusă sau schimbată. Linkul din email rămâne localhost:8766 în browserul laptopului.

n8n citește starea propunerii la fiecare 5 secunde. Ciclul se încheie la SIMULATED, REJECTED sau EXPIRED. Expirarea server-side este 120 secunde; dacă nu te încadrezi, generează o propunere nouă. Nu modifica expirarea în email și nu reutiliza aprobarea. Dacă serviciul este indisponibil, workflow-ul se oprește, fără aprobare sau ordin implicit.

La prima testare verifică selectarea credențialelor, schema parserului și compatibilitatea nodurilor în versiunea ta n8n. Nu este necesar să activezi workflow-ul pentru testul manual.

## 5. Testele pe laptop

1. Rulează suita inclusă: `python -m unittest discover -s . -p 'test_*.py' -v`. Testele HTTP folosesc temporar porturile 8765/8766; rulează-le înainte să pornești propriile servicii. Sunt exclusiv locale/sintetice, fără redirect real Google sau apel Gmail/DEX.
2. Configurează Google și fixează sub conform pașilor de mai sus.
3. Execută manual workflow-ul. Dacă AI returnează WAIT, fluxul se oprește fără email; pentru test determinist folosește separat fixture-urile offline deja livrate sau o copie de test a nodului AI, fără a schimba guard-ul/OIDC.
4. La o propunere validă, verifică emailul și pagina: sub alt cont trebuie refuzată; deschiderea linkului nu trebuie să schimbe PENDING; confirmarea corectă trebuie să producă doar SIMULATED_LIMIT_ORDER_ONLY, order_sent=false.
5. Verifică refuzul, expirarea, două clickuri și redeschiderea unei aprobări consumate. n8n trebuie să afișeze starea persistentă.

Un rezultat SIMULATED nu înseamnă ordin DEX, fill, profit sau test pe mainnet. Niciun flag nu poate activa LIVE în acest build. Integrarea Google reală și execuția n8n nu au fost testate în Codex, deoarece credențialele și laptopul tău nu sunt disponibile aici.
