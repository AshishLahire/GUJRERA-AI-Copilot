# What to type in each tab (demo inputs)

Every input below was run on 27 November 2026 on fresh copies; the result column is what the app gave.
Figures that grow daily (interest) are marked "about". Password for every login: `gujrera-demo`.

**Window A** = http://localhost:5192 (16,257 real projects from the public portal).
**Window B** = http://localhost:5193 (demo data shaped like GUJRERA's internal tables; say so).

## Window A: citizen, not logged in

| Tab | Type or click | Result |
|---|---|---|
| Overview | Switch language ગુ → हि → EN; click a suggested question | 16,257 projects; charts by district |
| Ask Saathi | `Approved projects in Gandhinagar` | 1,685 registered projects |
| | `ગાંધીનગરમાં કેટલા પ્રોજેક્ટ છે?` | Same answer, in Gujarati |
| | `શિલ્પ રેવન્તા નું પઝેશન ક્યારે મળશે?` | Completion date 31 December 2024, now passed |
| | `बिल्डर ने तय तारीख पर फ्लैट नहीं दिया, मैं क्या कर सकता हूँ?` | RERA Act Section 18, cited |
| | `Is Qwzx Plaza registered?` | "Could not find" (never guesses) |
| | `Is PR/GJ/SURAT/OLPAD/SUDA/RAA99999/010122 registered?` | Not in the registry |
| | `How many projects are delayed?` | 9,433 of 16,257 past their completion date, table by district |
| | `Projects in Bopal`, then `which of these were registered after 2020?` | List, then the list narrowed |
| | `How do I file a QPR?` | RERA Act Section 11 (the promoter's quarterly update) |
| | `What is RERA?` | Short explanation |
| | `Which projects are under scrutiny?` | "Available to GUJRERA officers" (internal data protected) |
| | `how do i cook dal` | Politely out of scope |
| Ask Saathi: file a complaint | `I want to file a complaint` → `Shilp Revanta` → `The builder has not given possession on the promised date` → `Refund with interest` → `Test Buyer` → `9999999999` → `skip` → `skip` → `yes` (agree) → **Submit** | Reference number (MOCK-CMP-2026-…) and a 6-digit tracking code: **write both down** |
| My complaint | The reference and the tracking code → **Add documents** → any PDF (e.g. `docs/samples/circulars/sample_circular_qpr_en.pdf`) | Complaint status; the document listed |
| Check an ad | Sample **"a registration number that is not in the registry"** → **Check** | Red: not found; "do not pay" |
| | The Gujarati sample (ad with no RERA number) → **Check** | No RERA number |
| | Paste `SHILP REVANTA, Sanand. GujRERA Reg. No: PR/GJ/AHMEDABAD/SANAND/AUDA/MAA07874/050121. Possession Dec 2024.` → **Check** | Number found; possession date compared with the registry |
| | **Report this ad to GUJRERA** on the red result | Sent to the officers' Ad enforcement list |
| Before-you-buy report | Type `Shilp Revanta`, pick it → **Save as PDF / Print** | One-page report |
| Interest calculator | From the report: **Interest the builder owes me** → Amount `5000000` → **Calculate** | About ₹10,44,000 for 696 days at 10.95% (SBI MCLR + 2%) |
| | Choose **withdraw**; payments `1000000` on 10 Jan 2022 and `2000000` on 1 Mar 2023 → **Calculate** | Refund of ₹30,00,000 plus interest |
| Agreement checker | **Load the one-sided sample** → **Check** | Clauses that break the model agreement, with the rule |
| Watched projects | Log in `citizen_01`; open the Shilp Revanta report → **Watch this project** | Listed under Watched projects |

## Window A: officer `officer_surat`

| Tab | Type or click | Result |
|---|---|---|
| My work queue | (opens on login) | Surat only: registrations ending, projects past their date |
| For officers | `What percentage of projects are delayed?` | Statement, table, chart, SQL shown |
| | `Show district-wise project registration trends`, then `last 3 years` | Trend; then narrowed |
| | `સુરતમાં કેટલા પ્રોજેક્ટ નોંધાયા?` | Same kind of report, in Gujarati |
| | `कितने प्रोजेक्ट की समापन तिथि बीत चुकी है?` | In Hindi |
| | **Export to Excel**; **Save** | .xlsx file; saved report |
| | `Projects registered in Ahmedabad` | Refused: "Your access covers Surat district only"; logged |
| | `delete all projects` | Refused: read-only |
| Ad enforcement | (after reporting the fake-number ad above) | The reported ad, grouped by project |

## Window A: officer `officer_state` (statewide, admin)

| Tab | Type or click | Result |
|---|---|---|
| Complaint desk | Open the complaint filed above → **Hearing scheduled**, date, place `GujRERA office, Gandhinagar, Court 2` → **Update** | Then in **My complaint** (buyer): next hearing, in N days, at that place |
| For officers | `How many complaints were received this quarter?` | Includes the complaint just filed |
| Data onboarding | Upload `docs/samples/department_project_details_sample.csv` → check → **Load** | 8 changed, 2 rejected (download the rejected rows) |
| Ask Saathi | `RERA approved projects in Bopal` (after loading) | Now matched by address |
| Circulars | Upload the 3 PDFs in `docs/samples/circulars/` → **Publish** | Scanned Gujarati circular read by OCR |
| Ask Saathi | `QPR ભરવા અંગે પરિપત્ર શું કહે છે?` | Answer citing the sample circular and page |
| Accuracy | **Run the test set**; manual report time `45` | POC measures with figures (about 1 to 3 minutes) |
| Users and roles | Add `officer_rajkot_demo`, role officer, district Rajkot → **Reset password** → **Disable** | New temporary password; account disabled |
| Audit log | Open | Every question, report, export and load above |

## Window B: demo data

| Tab | Login | Type or click | Result |
|---|---|---|---|
| Data onboarding | `officer_state` | Upload in this order: `department_complaints_sample.csv`, `_orders_`, `_notices_`, `_scrutiny_`, `_defaults_` → **Load** each | Each recognised; 1 complaint rejected (project not in registry) |
| For officers | `officer_state` | `Projects under scrutiny in Ahmedabad` | 7 rows |
| | | `Developers issued notices in the last six months` | 13 rows |
| | | `Defaulting developers in Ahmedabad in the last six months` | 2 rows, "default" defined |
| | | `Penalty orders with amounts` | 17 rows |
| | | `અમદાવાદમાં તપાસ હેઠળના પ્રોજેક્ટ` / `पिछले छह महीनों में नोटिस पाने वाले डेवलपर` | Same reports in Gujarati / Hindi |
| Risk watch | `officer_state` | Open | Projects at risk of delay, with reasons |
| Order tracker | `officer_state` | Open; mark an order **complied** | Compliance status updated |
| Ask Saathi | (not logged in) | `Tell me about Aangan Developers` | 6 projects: 3 ongoing, 3 completed |
| | | `Are there complaints against Aangan Developers?` | 29 complaints, 15 open, orders on record |
| | | `How many projects has Aangan Developers completed?` | 3 completed |
| For promoters | `dev_002` | Open | Own dues, notices, quarterly reports, registrations |
| Ask Saathi | `dev_002` | `Have I received any notices?` | 1 show-cause notice awaiting a reply |
| | | `Which documents are pending?` | Quarterly reports not filed, pending fire NOC, query on an application |
| | | `What is the status of my application?` | Query raised on the Sarjan Towers extension |
| | | `Do I have any outstanding dues?` / `મારી બાકી ચુકવણી કેટલી છે?` | 11 dues, ₹2,60,000 |
| | | `How do I file a QPR?` | RERA Act Section 11 |
| | | `Show dues of Kesar Builders` | Only its own records |
| Quarterly reports | `dev_002` | Open a project's draft → **Check** | Due / filed / late, and the check result |
| Ask Saathi | `agent_001` | `my registration status` | Agent registration and validity |

## Do not use in the demo

- The **microphone** for Gujarati or Hindi: it gets 2 and 3 of 10 test questions right until IndicConformer is installed. Type instead (English voice works).
- Builder names, complaints and internal records on **window A**: the public data has none; use window B and say it is demo data.
