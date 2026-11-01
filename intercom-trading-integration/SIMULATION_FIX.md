# Corecție: toate cele 18 cazuri pe False

## Concluzie și reproducere

18 rezultate invalide la primul IF NU sunt rezultatul așteptat al suitei offline livrate. Am reprodus o eroare de proiectare a testelor: fixture-urile folosesc Date.now() la creare, iar validatorul folosește un nou Date.now() și respinge datele mai vechi de 30 secunde. Rularea pe etape sau folosirea datelor fixate/pinned anterior poate astfel respinge și cele 6 cazuri care trebuiau să fie valide. Nu este nevoie să presupunem că IF-ul este defect; el compară valid cu booleanul true.

Reproducere cu ceas injectat, fără a aștepta efectiv: la întârziere 0 ms, valid=6 / invalid=12; la 31000 ms, valid=0 / invalid=18. Astfel, toate respingerile pot fi explicate de expirarea fixture-urilor. Acesta este un defect confirmat în codul livrat, dar nu dovedește singur cauza exactă din execuția utilizatorului: nu am primit exportul curent sau JSON-ul rezultatelor din instanța n8n.

## Ce am corectat

Fișierul nou este `intercom_dex_simulare_offline_v2.json`. Folosește un ceas virtual constant numai pentru fixture-uri offline și pentru avansarea controlată a timpului aprobării. Datele vechi, viitoare și aprobarea expirată rămân scenarii negative explicite; verificările nu sunt eliminate. Ceasul virtual NU este introdus în Gmail/OIDC, guard sau o viitoare integrare de date reale.

Toate Code nodes declară explicit modul Run Once for All Items. Nodul Automatic simulation summary verifică lotul complet, tipul boolean, unicitatea cazurilor și rezultatul de validare așteptat pentru fiecare. Dacă o verificare eșuează, aruncă o eroare descriptivă. Rezumatul are total=18, valid=6, invalid=12 și erorile fiecărui caz. Datele sunt apoi extinse înapoi la 18 item-uri și rutate prin IF. Fiecare nod terminal verifică rezultatul final așteptat, fără a cere inspecția manuală a tuturor nodurilor.

La prima validare:
- TRUE: valid_approved, valid_rejected, approval_string, expired_approval, changed_after_approval, sell_approved (6).
- FALSE: wait, over_budget, missing_ask, stale_market, paused, insufficient_liquidity, numeric_string, wrong_price, wrong_pair, crossed_book, invalid_mode, future_market (12).

Rezultate finale:

| Status | Număr |
| --- | ---: |
| SIMULATED_APPROVED_NO_ORDER | 2 |
| REJECTED_NO_ORDER | 2 |
| EXPIRED_NO_ORDER | 1 |
| BINDING_MISMATCH_NO_ORDER | 1 |
| INVALID_NO_ORDER | 12 |

Un caz negativ respins corect are test_passed=true. Deci „18 teste trecute” NU înseamnă „18 propuneri aprobate”. Cele 2 aprobări sunt numai simulate, fără Gmail sau ordine.

## Sunt două fluxuri în același fișier?

Fișierele livrate de Codex sunt separate:

- `intercom_dex_GMAIL_OIDC_SANDBOX.json`: 15 noduri, o singură componentă conectată, cu Gmail, Google OIDC prin serviciul local și polling pentru starea propunerii. Nu are Synthetic fixtures, Validate simulation sau cele 18 cazuri; nu folosește ceasul virtual. Citește în prezent piața sintetică din guard și nu execută DEX.
- `intercom_dex_simulare_offline_v2.json`: 12 noduri, o singură componentă conectată; numai Manual Trigger, Code și IF. Testează 18 scenarii de validare și aprobare falsificată/expirată/modificată. Nu are HTTP, Gmail, OpenAI, OIDC, credențiale sau ordine.

Prin urmare, cele 18 rezultate observate nu provin din fișierul GMAIL_OIDC livrat nemodificat. Dacă pe canvas apar și nodurile Gmail și nodurile de fixture-uri, instanța importată conține conținut combinat/diferit de exporturile inspectate. Fără exportul acelui canvas nu afirm că am verificat conexiunile sale efective. Nu muta cele 18 fixture-uri în fluxul Gmail: ar genera cereri de aprobare de test fără rost.

## Utilizare fără verificarea manuală a fiecărui nod

Importă V2 ca workflow NOU separat, fără a lipi nodurile în workflow-ul Gmail existent. Rulează de la Start manual, cu inputul generat de Synthetic fixtures. Nu reutiliza output pinned al validatorului vechi. Loturile incomplete și datele incompatibile sunt refuzate de rezumatul automat. Verifică un singur rezumat: validation_passed=true, total=18, valid=6, invalid=12. Nodurile terminale aruncă eroare dacă un status nu corespunde așteptării.

Test reproductibil din directorul integrării:

```sh
node verify_simulation_v2.cjs
```

Scriptul exercită codul JavaScript și conexiunile IF cu întârzieri reale simulate de 0, 31 secunde, 2 minute și 24 ore; toate cele 18 rezultate rămân corecte. Verifică și eșecul automat pentru un lot incomplet sau o validare coruptă. Raportul nou este scris implicit în directorul temporar al sistemului; SIMULATION_REPORT_PATH poate selecta o altă cale. Raportul comis `simulation_regression_results.json` include și reproducerea V1 făcută în mediul Codex.

n8n nu este instalat în mediul Codex: aceste teste sunt un harness Node VM, NU o execuție n8n reală. Compatibilitatea importului în versiunea utilizatorului nu este pretinsă ca verificată.

## Trading real

Obiectivul rămâne TNK/USDC și RESET/USDC, aprobare Gmail cu identitate Google verificată și limită inițială 10 USDC. Această corecție repară exclusiv testele offline. Guard-ul păstrează ceasul real, expirarea și plafonul cu comisionul USDC modelat inclus. Fixture-urile offline verifică plafonul noțional, nu toate costurile reale DEX.

Niciun ordin real nu a fost trimis. MAIN și aplicația Intercom originală nu au fost schimbate; corecția este adăugată numai în directorul integrării, pe branch-ul separat. JSON-ul Gmail/OIDC și codul său de autentificare/guard au rămas neschimbate. Executorul DEX real, reconcilierea timeouturilor și limitele de poziție/P&L rămân cerințe înainte de orice autorizare LIVE.
