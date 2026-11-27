# GujRERA Saathi: demo script, tab by tab

About 25 minutes. Every step below was rehearsed on fresh copies on 27 November 2026; the figures are what the app showed.

Exact inputs for every tab, with the expected results: `docs/DEMO_INPUTS.md`.

## Before the meeting

1. Start the apps about a minute before (they load the AI models and answer the suggested questions in the background):

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\run_gujrera_test_copy.ps1 -Fresh
   powershell -ExecutionPolicy Bypass -File scripts\run_gujrera_test_copy.ps1 -Source demo -Fresh
   ```

   - **Window A, http://localhost:5192**: the 16,257 real projects from the public GUJRERA portal. Use it for the citizen assistant and the officer reports.
   - **Window B, http://localhost:5193**: demo data shaped like GUJRERA's internal tables (scrutiny, notices, defaults, penalties). Use it for the officials' four sample questions, which need internal data. Say so: "this window is demo data".
   - `-Fresh` starts both from clean copies, so nothing from testing shows. Your own app on :5191 is not touched.

2. In window A, log in as `officer_state` (password `gujrera-demo`), open **Accuracy** and click **Run the test set** (about 3 minutes), so the POC measures have figures. Enter the manual report time if the department gave one. Log out.

3. Keep three files handy: `docs/samples/department_project_details_sample.csv` and the three PDFs in `docs/samples/circulars/`.

Logins (all `gujrera-demo`): `citizen_01`, `officer_surat`, `officer_state` (statewide, admin). Window B also has `dev_002` (promoter) and `agent_001`.

## Part 1: the citizen assistant (window A, not logged in)

| Tab | Do this | Point out |
|---|---|---|
| **Overview** | Show the page, then switch the language to ગુ (Gujarati) at the top. | 16,257 real registered projects from the public portal; charts by district; Gujarati first. |
| **Ask Saathi** | Click the Gujarati example (Mangal Square), then type **Approved projects in Gandhinagar**. | Answers in the language asked, with numbered sources. Gandhinagar: 1,685 registered projects. |
| **Ask Saathi** | Type **बिल्डर ने तय तारीख पर फ्लैट नहीं दिया, मैं क्या कर सकता हूँ?** | A Hindi law question answered from the RERA Act, Section 18, with the section cited. |
| **Ask Saathi** | Type **Is Qwzx Plaza registered?** | It says "not in the registry" instead of guessing. Never a made-up answer. |
| **Check an ad** | Click **Fake RERA number**, then **Check**; then the Gujarati sample with no number. | Flags a number that isn't in the registry, and an ad with no RERA number. |
| **Before-you-buy report** | Type **Shilp Revanta**, pick it, then **Save as PDF / Print**. | One page from the registry: dates, status, points to check before paying. |
| **Interest calculator** | From the report, click **Interest the builder owes me**; enter **5000000** and **Calculate**. | About ₹10.4 lakh (₹10,44,000 for 696 days on 27 November; it grows each day) at 10.95% (SBI MCLR + 2%, Rule 16), with the law cited. |
| **Agreement checker** | Load the **one-sided sample** and check it. | Clauses that break the model agreement are flagged, with the rule. The samples use a made-up project. |
| **Ask Saathi** | Type **I want to file a complaint**, answer the questions (project **Shilp Revanta**, a short problem, **Refund with interest**, a name, a test mobile, **skip** twice), agree, then **Submit** (typing *yes* also submits). | A complaint filed by chat in a few messages; a reference number and a 6-digit tracking code. Note both for the next steps. |
| **My complaint** | Click **Add documents** on the filed card; add any PDF. | The buyer adds evidence; PDF, JPG or PNG only, checked by content. |
| **Watched projects** | Log in as `citizen_01`, watch a project from its report. | Alerts when the project's quarterly report is filed or missed. |

## Part 2: the officer (window A)

| Tab | Do this | Point out |
|---|---|---|
| **My work queue** | Log in as `officer_surat`. | Only Surat: registrations ending, projects past their date, citizens' checks. A district officer never sees another district. |
| **Complaint desk** | Log out and in as `officer_state` (the complaint is about an Ahmedabad project, so the Surat officer does not see it). Open the complaint you just filed. Set **Hearing scheduled**, a date and a place (e.g. *GujRERA office, Gandhinagar, Court 2*), **Update**. | The brief: the law, the project record, similar decided complaints, the buyer's document. Then switch to the buyer's **My complaint**: "Next hearing: …, in N days, at …". |
| **For officers** | Ask **What percentage of projects are delayed?**, then **Show district-wise project registration trends**, then **How many complaints were received this quarter?** | A plain answer, a table and chart, and the read-only SQL shown. |
| **For officers** | After a report, type **only Surat**; then **Export to Excel**. | Follow-ups refine the last report; export to Excel or PDF; save a report. |
| **Ad enforcement** | Open the list. | Ads that citizens checked and reported, grouped by project. |
| **For officers** | Still as `officer_surat`, ask **What percentage of projects are delayed in Ahmedabad?** (or, in Ask Saathi, **projects in Ahmedabad**) | Refused: "Your access covers Surat district only", and the attempt is logged. **projects in Surat** gives the list. |

## Part 3: administration (window A, `officer_state`)

| Tab | Do this | Point out |
|---|---|---|
| **Data onboarding** | Upload `department_project_details_sample.csv`, look at the check, then load it. | The department's file is checked on a copy first; rejected rows can be downloaded and fixed. This is how week 1 works. |
| **Circulars** | Upload the three sample PDFs (one is a scanned Gujarati circular). Then in Ask Saathi ask about quarterly reports. | Scanned Gujarati is read by OCR; answers cite the circular and the page. The samples are marked SAMPLE. |
| **Accuracy** | Show the **POC measures** and the run's results by language. | Answered without a person, citizen response time, officer report time against the manual time, same answer when asked again (50 of 50). The department's test set can be imported here. |
| **Users and roles** | Add a test officer for a district, then disable it. | Accounts are managed in the app; disabling signs that person out everywhere. |
| **Audit log** | Open it. | Every question, report, export and data load in this demo is listed: who, when, what. |

## Part 4: internal data (window B, demo data)

Say first: "this window is demo data shaped like GUJRERA's internal tables; in week 1 it is the department's data".

| Tab | Do this | Point out |
|---|---|---|
| **Data onboarding** (`officer_state`) | Upload the five `docs/samples/department_*_sample.csv` files (complaints first, then orders, notices, scrutiny, defaults); check, then load each. | The department's internal exports load the same way as projects, matched by RERA number. One complaint is rejected with the reason (its project is not in the registry). |
| **For officers** (`officer_state`) | Ask the department's four sample questions: **Projects under scrutiny in Ahmedabad**; **Developers issued notices in the last six months**; **Defaulting developers in Ahmedabad in the last six months**; **Penalty orders with amounts**. | 7, 13, 2 and 17 rows after loading the five sample files (5, 11, 1 and 16 before). "Default" is defined on screen. Try one in Gujarati or with another district. |
| **Risk watch** | Open it. | Projects most at risk of delay, with the reasons. |
| **Order tracker** | Open it. | Orders and whether they were complied with. |
| **For promoters** | Log in as `dev_002`; in Ask Saathi ask **Have I received any notices?**, **Which documents are pending?**, **What is the status of my application?**, then **How do I file a QPR?** | A promoter sees only its own projects, dues, notices and applications (never the officer's notes); a how-to question is answered from the Act (Section 11), not from its records. |
| **Quarterly reports** | As `dev_002`. | Which quarterly reports are due, filed or late. |

## If asked

- **"Who is the builder of Shilp Revanta?"** The public search results we imported don't include builder names, so the app says so and shows the project. The portal's project pages do have them (Shilp Revanta's promoter is AYB BUILDCON LLP); we have asked the department for an export.
- **"Projects in Bopal"** On public data, matched by project name; with the department's addresses it uses the address.
- **"What if the AI or the server is down?"** The app checks every 15 seconds; if it cannot reach the service it shows fixed answers to common questions (from the RERA Act) and links to the GUJRERA portal, in the chosen language, and returns by itself when the service is back. To show it, close window B's API window.
- **Accessibility?** The citizen screens pass an automated WCAG 2.1 AA check in both themes and down to 320 px wide (`docs/gujrera_accessibility_check.md`); the formal GIGW/WCAG audit is done before go-live.
- **First question slow?** Only before the warm-up finishes (about 40 seconds after starting).
- **Hindi or Gujarati question slower than English?** Questions the rules don't recognise go through the local AI model: 2 to 5 seconds.
