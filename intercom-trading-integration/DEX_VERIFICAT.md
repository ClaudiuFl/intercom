# Intercom DEX: documentație și implementare verificate

Repository oficial: https://github.com/Trac-Systems/intercom-dex
Commit inspectat: **90dcd473f89576cbb588f12e08802229b060a8b9**, package version **0.1.47**, engines Node >=23.11.0. Inspecția a fost statică într-un checkout separat temporar. Nu am pornit DEX, deblocat walleturi sau instalat/rulat protocolul. Repository-ul Intercom existent a rămas neschimbat.

## Surse fixate la commit
- [API.md](https://github.com/Trac-Systems/intercom-dex/blob/90dcd473f89576cbb588f12e08802229b060a8b9/src/core/API.md)
- [Control HTTP](https://github.com/Trac-Systems/intercom-dex/blob/90dcd473f89576cbb588f12e08802229b060a8b9/src/roles/control.js)
- [Trader/takeOffer](https://github.com/Trac-Systems/intercom-dex/blob/90dcd473f89576cbb588f12e08802229b060a8b9/src/roles/trader.js)
- [Market HTTP](https://github.com/Trac-Systems/intercom-dex/blob/90dcd473f89576cbb588f12e08802229b060a8b9/src/market-feed/http.js)
- [Market snapshot](https://github.com/Trac-Systems/intercom-dex/blob/90dcd473f89576cbb588f12e08802229b060a8b9/src/market-feed/view.js)
- [Envelope/signatures](https://github.com/Trac-Systems/intercom-dex/blob/90dcd473f89576cbb588f12e08802229b060a8b9/src/core/envelope.js)
- [Assets/units](https://github.com/Trac-Systems/intercom-dex/blob/90dcd473f89576cbb588f12e08802229b060a8b9/src/market/assets.js)
- [SKILL: amounts, tools, fees, recovery](https://github.com/Trac-Systems/intercom-dex/blob/90dcd473f89576cbb588f12e08802229b060a8b9/SKILL.md)

## Autentificare și suprafață HTTP

GET `/v1/market/view` este o citire publică a rolului market-feed, care ascultă numai pe 127.0.0.1. În cod, această rută NU cere viewer bearer key. Cheia viewer este verificată pentru POST de chat, nu trebuie confundată cu tokenul de trading. Market-feed nu are wallet sau rute de trading.

API-ul local control folosește `Authorization: Bearer <token>`, token citit din `config.control.tokenFile`, și ascultă numai pe 127.0.0.1. GET `/status` și GET `/wallets` sunt rute de citire autentificate. POST `/offer`, `/take`, `/cancel`, `/withdraw` au efecte; tokenul de control conferă puteri largi, nu doar citire. Nu trebuie dat modelului AI și nu trebuie încorporat în JSON-ul n8n. Este distinct de Google Client Secret, de cheia guard și de cheia HMAC internă.

Nu am găsit `/prepare` în implementarea oficială inspectată. Acesta rămâne un adaptor local necunoscut și este exclus. Nu este nevoie să îl folosim pentru un viitor conector oficial, dar orice comportament al său ar necesita codul local pentru verificare.

## Semnare și executare

DEX semnează intern envelope-urile Ed25519 cu identitatea locală, prefixul de domeniu `intercom-dex/v1\n`, structura canonică, tipul, canalul, timestamp și nonce. Walleturile și keyring-ul sunt gestionate de program; aprobarea OIDC nu este o semnătură blockchain și nu înlocuiește identitatea DEX. Nu exportăm chei în n8n și nu construim manual transferuri de active.

POST `/take` primește `{offerId, baseAmount, price}`. Prețul este EXACT șirul ofertei; cantitatea este șir întreg de unități de bază. Luarea unei oferte `sell` înseamnă BUY pentru noi; luarea unei oferte `buy` înseamnă SELL. Nu se folosește doar un nivel agregat bid/ask: este necesară oferta semnată cunoscută traderului.

`takeOffer` verifică oferta proprie, registrul, software-ul/pauza, prețul exact, termenul ofertei (mai mult de 60 secunde), cantitatea, comitetul și fondurile; apoi creează un trade, îl adaugă la host și livrează un tick. Protocolul continuă automat către negocieri, lock, transferuri, claim/refund, în funcție de rol și fază. POST `/take` este un punct de efect real; nu este preview și nu necesită un apel ulterior `/execute` ca să mute eventual fonduri.

Un timeout HTTP nu dovedește lipsa efectului. Implementarea generează cheia trade-ului cu un `random32()` nou; ruta nu expune clientOrderId/idempotency key al apelantului. O reluare poate crea alt trade. Înainte de activare LIVE sunt necesare o înregistrare persistentă SUBMITTING, oprirea la rezultat ambiguu și reconcilierea cu traderul/jurnalul. Dacă statusul existent nu permite identificarea unică după crash, trebuie un mecanism idempotent verificat în trader sau un adaptor cu jurnal atomic adecvat. Nu promit exactly-once pe baza SQLite-ului simulării.

Un maker POST `/offer` poate răspunde automat mai multor takeri; nu îl folosim pentru regula „o aprobare per tranzacție”. Viitorul mod inițial trebuie să fie taker, cu offerId, cantitate și preț aprobate exact, fără rerutare automată la altă ofertă. Un rezultat de submit nu este settlement final; fazele și dovezile trebuie reconciliate.

## Date și unități

Feed-ul este `{v:1,ts,pairs,offers,trades}`. `pairs` include bestBuy/bestSell ca șiruri preț, plus status și paused în implementarea curentă. Timestamp-urile sunt secunde Unix. `ts` este momentul construirii snapshotului cache-uit, nu dovada că fiecare cotație a sosit atunci; book-urile pot fi păstrate până la 300 secunde. O citire HTTP recentă nu dovedește singură prospețimea executabilă.

`offers.amount` și `offers.left` din feed sunt șiruri în tokeni întregi/zecimali, iar left poate fi null: cantitate rămasă necunoscută, NU lichiditate zero sau garantată. `postedAt` este prima observație, NU timestamp-ul ultimei reanunțări. Pentru admiterea unei tranzacții trebuie statusul autentificat al traderului, oferta, registryVersion, lastSeen, expiresAt și limitele inventarului.

| Activ | Zecimale |
| --- | --- |
| TNK | 18 |
| RESET | 8 |
| USDC | 6 |
| SOL | 9 |

Prețul este USDC per token de bază, șir cu maximum 12 zecimale. `quoteAmount = floor(baseAmount * priceUnits * 10^6 / 10^(baseDecimals+12))`. Conversiile și rotunjirea sunt implementate/testate fără float în `dex_contract.py`. Acest modul produce doar un preview de payload `/take`; nu îl trimite.

Comisioanele provin din registrul semnat și terms, nu din valori hardcodate: platform fee și venue fee se rotunjesc în jos separat. Exemplul documentat 2.5 RESET la 0.04 dă 100000 unități USDC, respectiv 100600 cu 10+50 bps. Valorile bps din exemplu nu trebuie tratate drept configurație permanentă. Există separat comisioane/cerințe de fonduri TNK și SOL; acestea nu pot fi incluse într-un plafon total exprimat USDC fără o politică de evaluare și rezerve.

## Ce rămâne înainte de LIVE

- Verificarea versiunii DEX instalate pe laptop față de commitul inspectat, profilului/rețelei și identității venue.
- Conector de citire reală și admitere care corelează feed, status, registry, wallet funds și comisioane; momentan guard-ul folosește SyntheticMarket.
- Persistarea în propunerea aprobată a offerId, baseAmount, prețului exact, versiunii/pinilor și plafonului de fees. Nu convertim direct vechile numere AI în `/take`.
- Executor taker fără retry orb, cu reconciliere la timeout/crash și finalitate. Nu este implementat în acest build.
- Ledger pentru poziții și P&L, limitele de pierdere stabilite de utilizator și politica de ieșire/rezervă native fees. Limitele curente de 10 USDC/ordin și 20 USDC/24h sunt controale de simulare, nu stop-loss real.
- Validare Google OIDC reală și n8n pe laptop; apoi teste local-network/DEX fără fonduri reale și autorizare explicită ulterioară pentru activare.

LIVE rămâne imposibil în codul livrat, inclusiv după configurarea Google și aprobarea în browser. Nu s-au făcut requesturi către un DEX operat de utilizator sau vreo semnare de wallet.
