# Intercom DEX + n8n + Gmail / Google OIDC

**Versiunea curentă: integrare de aprobare și simulare, LIVE blocat structural.** Nu este un executor DEX gata de mainnet. Datele sunt sintetice; niciun secret wallet, transport de trading sau funcție de semnare blockchain nu este inclusă.

## Pornire simplă pe Windows

Pentru testarea completă Gmail/OIDC folosește **WINDOWS.md**, **Start-Windows.ps1** și **intercom_dex_WINDOWS_SANDBOX.json**. Launcher-ul configurează serviciile, protejează secretele local cu Windows DPAPI și verifică automat cele trei rute Guard. Noua variantă nu folosește `$vars`, nu cere credențiale OpenAI și generează o propunere sintetică deterministă de 5 USDC. Simularea offline V2 rămâne neschimbată.

## Fișiere de folosit
- `intercom_dex_GMAIL_OIDC_SANDBOX.json`: workflow-ul n8n actual, pentru import ca workflow NOU, dezactivat.
- `GOOGLE_OIDC.md`: pașii Google Cloud, fixarea identității, configurarea pe laptop și testarea manuală.
- `DEX_VERIFICAT.md`: constatări bazate pe sursa oficială, unități, autentificare, executare și blocajele LIVE rămase.
- `guard.py`, `server.py`: propuneri persistente/limite/revalidare și API privat pentru n8n.
- `oidc.py`, `oidc_server.py`: autentificare Google și confirmare locală explicită, legată de propunere.
- `dex_contract.py`: conversii conforme DEX și preview de payload, fără trimitere.
- `requirements.txt`, `test_*.py`: dependența de verificare JWT și testele locale.

`intercom_dex_gmail_guard_SANDBOX.json` și `build_workflow.py` sunt versiunea anterioară, păstrată pentru regresii/teste. Nu o importa pentru fluxul OIDC curent: folosea Gmail sendAndWait plus un gateway extern încă neconfigurat. `build_oidc_workflow.py` produce noul JSON. `workflow_original_anonimizat.json` este exclusiv sursă pentru generator, NU workflow de importat: păstrează traseul original nesigur cu `/prepare` înaintea aprobării. Nu îl executa. Nu importa ambele drept același workflow activ.

## Traseul actual
Manual → piață sintetică → analiză AI → validare → WAIT sau persistarea propunerii → email Gmail cu link local → citirea stării la fiecare 5 secunde → rezultat SIMULATED, REJECTED sau EXPIRED.

Din email: link fără secret → Google OIDC → cont Google autorizat și sub fixat → afișarea propunerii imutabile → POST explicit cu CSRF → revalidarea pieței și limitele SQLite → simulare. Deschiderea unui link, redirecționarea emailului, autentificarea sau orice GET nu aprobă și nu execută. Noul workflow nu utilizează răspunsul Gmail approved=true și nu are URL de resume ca dovadă de identitate.

Limita rămâne 10 USDC pe propunere, cu comisionul sintetic USDC inclus; suplimentar maximum 3 simulări și 20 USDC expunere brută aprobată/24h. Expirare 120 secunde, consum unic, digest, nonce, jurnal, serializare SQLite și kill switch. Noțiunea de limită nu garantează o pierdere maximă reală; înainte de mainnet lipsesc reconcilierea pozițiilor/P&L și evaluarea comisioanelor native.

## Ce s-a verificat
Repository DEX oficial inspectat la commit 90dcd473f89576cbb588f12e08802229b060a8b9, versiunea 0.1.47. API-ul real și codul confirmă GET /v1/market/view și control bearer-token local; POST /take este cu efect real și pornește automat protocolul. /prepare nu a fost găsit și nu este folosit.

**Suita inițială de 59 teste locale rămâne trecută**: 22 guard/structură veche, 3 HTTP guard, 23 OIDC/JWT/structură nouă, 4 HTTP OIDC și 7 conversii DEX. Sunt verificate falsificarea, issuer/audience/nonce/signature/expiry, contul greșit, CSRF, state/session replay, concurența, restartul, piața schimbată, plafonul, comisioanele, kill switch și lipsa rutelor LIVE. Testele JWT folosesc chei RSA generate pentru test, iar redirecturile HTTP către Google nu sunt urmate. Nu au existat apeluri Gmail, OpenAI, Google token exchange sau DEX real.

Cu verificările Windows adăugate, suita actuală rulează 72 teste: 71 trecute și 1 test DPAPI real omis pe Linux. PowerShell și Windows DPAPI reale nu au fost executate aici.

n8n nu este disponibil în mediul Codex. Importul și execuția în versiunea de pe laptop, autentificarea Google reală și trimiterea Gmail trebuie validate după configurarea locală. Nu sunt pretinse ca testate. Succesul testelor locale nu activează LIVE.

## Rulare
Consultă GOOGLE_OIDC.md înainte de pornire. Python 3.10+, `python -m pip install -r requirements.txt`. Configurează secretele local și aceeași cale absolută SQLite pentru ambele servicii. Rulează `python server.py` și `python oidc_server.py` în procese separate, numai pe loopback. Niciun serviciu nu este pornit sau păstrat în fundal de Codex.

Teste: `python -m unittest discover -s . -p 'test_*.py' -v`, cu propriile servicii oprite pentru a elibera porturile de test 8765/8766.

API-ul guard păstrează și rutele HMAC din versiunea anterioară pentru testele de regresie; noul workflow nu le folosește pentru aprobare. O cheie API n8n singură nu poate falsifica semnătura HMAC. Totuși, serviciul/cheia HMAC și mediul local sunt componente de încredere; nu sunt protejate de compromiterea sistemului de operare. Nu expune aceste servicii public.

## Ce nu s-a făcut
Nu s-a modificat repository-ul Intercom/GitHub sau configurația publicată a mediului. Nu s-au inițializat walleturi, pornit DEX sau executat ordine. LIVE nu se activează prin variabile de mediu sau simpla schimbare a unui flag; executorul real și reconcilierea efectelor ambigue rămân de implementat/testat înaintea autorizării ulterioare a utilizatorului.
