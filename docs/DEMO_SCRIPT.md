# GujRERA Saathi: demo walkthrough (about 12 minutes)

One story, told through the four people the problem statement names: a **home buyer**, a **promoter**,
an **agent** and a **GUJRERA officer**. Every answer on screen cites the record or the section of law it
comes from, and everything runs on our own machine (self-hosted model, no data leaves).

Password for every login below: `gujrera-demo`.

## 15 minutes before the call

1. Start Ollama if it is not running: `ollama serve`
2. Start the app (it picks free ports if another project is using 8000 or 5173):
   ```
   powershell -ExecutionPolicy Bypass -File scripts\run_gujrera.ps1
   ```
   The browser opens on the app. Note the address it prints (for example `http://localhost:5173`).
3. **Warm up the model**: in *Ask Saathi*, ask `Can the builder take more than 10 percent before the agreement?`
   The first model answer takes about 30–40 s while the model loads; after that, about 5 s.
4. Set the language to **ગુ** (Gujarati), browser zoom 110–125% for screen sharing, close other tabs.

## The walkthrough

| # | Who | Page | What to do | What to say |
|:-:|:--|:--|:--|:--|
| 1 | — | **Overview** | Show the home page. | "One assistant for buyers, promoters, agents and officers, in Gujarati, Hindi and English." |
| 2 | Buyer (no login) | **Ask Saathi** | Ask `મંગલ સ્ક્વેરનું પઝેશન ક્યારે મળશે?` | Answer comes from the registration record, with the original and extended dates, and is cited. English appears under the Gujarati. |
| 3 | Buyer | Ask Saathi | Ask the same in Hindi: `मंगल स्क्वेर का पज़ेशन कब मिलेगा?` Then try the **mic** button. | Same answer in Hindi; voice works for people who don't type. |
| 4 | Buyer | Ask Saathi | Ask `પઝેશનમાં વિલંબ થાય તો શું મને વ્યાજ મળે?` | Law answer citing RERA Act Section 18. |
| 5 | Buyer | **Check an ad** | Paste: `Mangal Square by Prakash Builders, Surat. 2BHK from 45 lakh. Ready possession December 2026! GujRERA No. PR/GJ/SURAT/SURAT CITY/SUDA/MOCK00009/240723` | Registered, **but**: the project is delayed and the ad promises possession almost two years before the registered date. Then change the number to `PR/GJ/AHMEDABAD/AHMEDABAD CITY/AUDA/RAA99999/010125` → **not found**, with a button to report it to GUJRERA. |
| 6 | Buyer | **Interest calculator** | Mangal Square, paid 40 lakh. | Delay interest under Section 18 at SBI MCLR + 2% (Rule 16), with the working shown. |
| 7 | Buyer | **Before-you-buy report** | Open it for Mangal Square, press **Print**. | One page a buyer can take to the bank or a lawyer. |
| 8 | Buyer | **Agreement checker** | Press **One-sided sample**. | Flags clauses that differ from the model agreement (Annexure A), each with the clause it should match. |
| 9 | Buyer `citizen_03` | Ask Saathi | Log in, ask `pending complaints`. | Their own complaints and status timeline only. |
| 10 | Buyer `citizen_01` | **Watched projects** | Log in, open the page. | Alerts when a watched project's dates, complaints or orders change. |
| 11 | Promoter `dev_002` | Ask Saathi, **Quarterly reports** | Ask `What are my dues?`, then open Quarterly reports. | Promoter sees only their own dues and overdue quarterly reports, each cited. Ask for another promoter's dues → refused. |
| 12 | Officer `officer_state` | Ask Saathi | Ask `Which promoters in Surat have the most delayed projects?` | Officer reports in plain language; the table is generated from the records. |
| 13 | Officer | **Complaint desk** | Show the queue. | Complaints sorted by urgency, with the relevant section suggested. |
| 14 | Officer | **Risk watch**, **Ad enforcement**, **Order tracker** | Click through each. | Early warning on projects likely to slip; citizen ad reports grouped into cases; orders whose compliance is overdue. |
| 15 | Officer `officer_surat` | Ask Saathi | Log in, ask `complaints by district`. | A district officer sees only their own district. |

## Close (1 minute)

- Self-hosted: the language model, speech and search run on our hardware. No buyer or promoter data goes
  to an outside AI service.
- Measured, not claimed: 300/300 test questions answered correctly and cited; 0 leaks in 31 attempts to
  read another user's data; 178/178 ad checks correct (`docs/gujrera_eval.md`).
- Ask the department: which registry fields and APIs we can connect to, which complaint and order data
  can be shared for the PoC, and their priority between the four user groups.

## If asked

- **"Is this real GUJRERA data?"** The records are a test registry shaped like GUJRERA's (marked "Demo" on
  screen). The law texts are the real RERA Act and Gujarat Rules. Connecting to the live registry is the
  first PoC step.
- **"Why did that answer take a few seconds?"** Free-form questions go to the self-hosted model on a laptop
  GPU. Routine questions answer in under a second; on a server GPU the model answers faster too.

## If something goes wrong

- **Page shows errors or "not found" everywhere**: another project is probably on the same ports. Close
  the two *GujRERA* windows and run `scripts\run_gujrera.ps1` again; it moves to free ports.
- **Free-form questions don't answer**: Ollama is not running. Start `ollama serve`; the rest of the
  app works without it.
- **Login fails**: check the password is `gujrera-demo` (set by `GUJRERA_DEMO_PASSWORD` in `.env`).
