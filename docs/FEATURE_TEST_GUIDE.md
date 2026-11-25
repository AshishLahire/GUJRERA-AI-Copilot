# GujRERA Saathi: feature test guide

Test every feature yourself, step by step: where to click, what to type, what you should see. Tick each box as you go.

Testing creates accounts, uploads files and loads data, so **test on a copy**. Your real-data app
(http://localhost:5191) is never touched.

Numbers marked "about" depend on today's date, so they change a little from day to day.

---

## 0. Start the test copies

Open PowerShell in the project folder (`pramaan-main\pramaan-main`) and run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_gujrera_test_copy.ps1
```

You get the **real public data** test copy at **http://localhost:5192**. It's used for sections A, B, D and E.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_gujrera_test_copy.ps1 -Source demo
```

You get the **demo data** test copy at **http://localhost:5193**. It's used for section C: officer records (scrutiny,
notices, defaults) that only the department's internal data will have.

To start again from a clean copy, add `-Fresh` to either command.

**Before you start:** Ollama should be running (`ollama serve`) for free-form questions. The first AI answer after a start
can take about a minute. Ask one question first to warm it up.

**Logins** (password `gujrera-demo` for all):

| Username | Role | Use for |
|---|---|---|
| (not logged in) | Citizen | A |
| `citizen_01` | Home buyer | Watch (A6) |
| `officer_surat` | Officer, Surat only | B, E |
| `officer_ahmedabad` | Officer, Ahmedabad only | E |
| `officer_state` | Officer, statewide, **administrator** | C, D |

The **EN / ગુ / हि** buttons at the top switch the language of the app.

---

## A. Citizen assistant (http://localhost:5192, not logged in)

### A1. Home page
- [ ] A yellow banner reads "Every RERA answer, in your language", with a badge "Public GUJRERA records · 16,257 projects".
- [ ] **"Buying a home: your five steps"** shows 5 cards, each with buttons.
- [ ] Tiles show about **16,257** registered, **9,430** past completion date and **588** ending in 90 days.
- [ ] "The registry in pictures" shows 4 charts. Hover a bar to see its number, and click **Show as table**.
- [ ] The menu shows only citizen tools: Overview, Check an ad, Ask Saathi, Before-you-buy report, Agreement
  checker, Watched projects, Interest calculator.

### A2. Ask Saathi
| Type this | You should see |
|---|---|
| `BANSARI SKYVIEW નું પઝેશન ક્યારે મળશે?` | Completion date **30 April 2029**, with a [1] source |
| `When will I get possession of Sunrise Skyline Towers?` | "I couldn't find… Did you mean…?". A made-up name is **never** answered |
| `Can a builder take 20% before the agreement?` | **Section 13** of the RERA Act, with the quoted text and "not legal advice" |
| `અમદાવાદના બોપલ વિસ્તારમાં RERA માન્ય પ્રોજેક્ટ કયા છે?` | Projects whose **name** mentions Bopal, with a note that public records have no addresses (D1 changes this) |
| `I want to file a complaint` | Step-by-step complaint form starts |
| `what is the weather today` | Polite "outside RERA" answer |

- [ ] Click **Sources** under an answer. Each source is listed.
- [ ] Under each answer: **Was this helpful? 👍 👎**. Click 👎, pick **Should have found it**, type a comment and click
  **Send**. You see "Thank you". This appears in D4.

### A3. Check an ad
Paste this:
```
OFIRA SIESTA, Surat City. Possession Nov 2026. RERA PR/GJ/SURAT/SURAT CITY/SUDA/RAA03767/A1R/EX4/150925/310726. Book with 25% now.
```
- [ ] Verdict: **registered, with warnings**. The 25% booking is flagged (the limit is 10% before an agreement).
- [ ] Change the number to `PR/GJ/SURAT/OLPAD/SUDA/RAA99999/010122`. Verdict: **not found**, with a **Report this ad** button.

### A4. Before-you-buy report
- [ ] Search `OFIRA SIESTA`. The report shows "Registration ends on 30 November 2026", and a
  **Next for this project** strip.
- [ ] Search `SAKET TEXTILE MARKET`. The report says "completion date 2 December 2025 has passed… **5 extension(s)**",
  and asks you to request the completion certificate or extension order. **Next** offers "Interest the builder owes me".
- [ ] **Save as PDF / Print** opens a clean printable page.

### A5. Agreement checker
- [ ] Click **One-sided sample**, then **Check agreement**. One-sided or missing clauses are listed.

### A6. Watch a project (log in as `citizen_01`)
- [ ] Open the SAKET TEXTILE MARKET report and click **Watch this project**.
- [ ] Open **Watched projects**. An alert says the completion date has passed, with the number of extensions.

### A7. Interest calculator
- [ ] Project `SAKET TEXTILE MARKET`, **I will stay**, amount `2500000`, paid on `10/01/2023`, then **Calculate**.
- [ ] Interest is counted from **2 Dec 2025** to today at **10.95%** (SBI MCLR + 2%), with the working shown.

---

## B. Officer, one district (http://localhost:5192, log in as `officer_surat`)

### B1. My work queue (opens straight after login)
- [ ] The header reads "My work queue · Surat district".
- [ ] Tiles show about **126** ending in 90 days, **1,311** past completion date and **84** extended twice or more.
- [ ] Charts show registrations ending month by month (a peak in December), and projects past their date by
  taluka (Surat City, Chorasi, Kamrej…).
- [ ] On any item, type a note and click **Action taken**. The item moves to the bottom with your name and the time.
- [ ] **Open record** opens that project's report.
- [ ] The menu shows officer tools only. **No** Data onboarding, Circulars, Accuracy, Users or Audit log (those are for the state admin).

### B2. For officers (reports by asking)
- [ ] Click **Lapsed or soon-ending registrations**. You get about **126** rows, limited to Surat.
- [ ] Type `top 10` and click **Run**. It narrows to the first **10**, and a **Top: 10** chip appears.
- [ ] Type `Projects past their completion date` (a new report): Surat only. The first **500** rows are shown, with a note
  that there are more (Surat has about 1,311). Excel and CSV get the same 500.
- [ ] Click a column heading to sort. Click **Excel**: a .xlsx downloads, with the question, "District scope: Surat",
  the time, your name, and the SQL on a second sheet.
- [ ] **Print / PDF** opens a printable page.
- [ ] Type a name, then **Save report**. It appears under **My saved reports**, and clicking it runs it again.
- [ ] 👍/👎 appears under the report as well.

---

## C. Officer reports on internal-style data (http://localhost:5193, demo copy, log in as `officer_state`)

These need the department's internal records (scrutiny, notices, defaults), which only the demo data has.

- [ ] For officers: type `Projects under scrutiny in Ahmedabad`. You get **5** projects under scrutiny (South Bopal,
  Shela, Satellite, Thaltej).
- [ ] Type `only Shela`. It narrows to **2**, and an **Area: Shela** chip appears.
- [ ] New report: `Developers issued notices`, about 36 rows. Then `only Ahmedabad` gives fewer rows, then `last 6 months`
  fewer again, each shown as a chip. Then `top 5` gives a ranking.
- [ ] In Gujarati: `અમદાવાદમાં છેલ્લા છ મહિનામાં ડિફોલ્ટ કરનાર ડેવલપર્સ`. You get defaulting developers, with the period stated.
- [ ] In **Ask Saathi**, the same report works, and a follow-up like `last 3 months` starts with "Narrowed the last report".

---

## D. Administration (http://localhost:5192, log in as `officer_state`)

### D1. Data onboarding
- [ ] Open **Data onboarding**. Tiles show 16,257 projects, and 0 with an address.
- [ ] Upload `docs\samples\department_project_details_sample.csv`.
- [ ] The file is recognised as **Extra details for projects already loaded**. The columns are matched, and
  **Not read: Contact Phone** is shown.
- [ ] Click **Check every row (saves nothing)**. It shows **8 would change** and **2 rejected**, with reasons
  ("not in the registry", "unrecognised registration number").
- [ ] Click **Load**. The tiles change to **8 with a site address** and **8 with a locality**. The history row shows your name.
- [ ] Click **Rejected rows** in the history. A CSV of the 2 bad rows downloads.
- [ ] In Ask Saathi, ask `અમદાવાદના બોપલ વિસ્તારમાં RERA માન્ય પ્રોજેક્ટ કયા છે?` again. The Bopal projects are now found **by address**.

### D2. Circulars
- [ ] Open **Circulars** and upload the 3 PDFs in `docs\samples\circulars\`. The first one can take about a minute.
- [ ] Each one appears as a **Draft**, with its number, date and subject filled in. The Gujarati and scanned ones
  say "1 read with OCR".
- [ ] Ask Saathi about a draft. It isn't found yet.
- [ ] Click **Publish** on all 3, then ask:

| Type this | You should see |
|---|---|
| `QPR ભરવા અંગે પરિપત્ર શું કહે છે?` | SAMPLE/GUJRERA/2025/07, quoting "within fifteen days…" |
| `Is there a circular on showing the RERA number in advertisements?` | SAMPLE/GUJRERA/2025/09, the Gujarati circular |
| `circular about extension of registration` | SAMPLE/GUJRERA/2025/11, "at least three months before…" |
| `તાજેતરના પરિપત્રો` | A list of the 3, newest first |
| `circular about parking charges for visitors` | "could not find a GUJRERA circular" |

- [ ] Open **Sources**: the circular link opens the PDF at the cited page.

### D3. Users and roles, and the Audit log
- [ ] **Users and roles**: create `officer_bharuch`, Role **GUJRERA officer**, District **Bharuch**.
  A **one-time password** appears once. Copy it.
- [ ] In a **private/incognito window**, open http://localhost:5192 and log in as `officer_bharuch` with that password.
  The work queue shows **Bharuch district**.
- [ ] Back as admin, click **Disable** on `officer_bharuch`. In the private window, the next click logs them out, and
  logging in again says "This account is disabled".
- [ ] Click **Enable**, then **Reset password**. A new one-time password appears, and the old one no longer works.
- [ ] You can't disable your own account (no button on "(you)").
- [ ] **Audit log**: click **Refusals**. You see failed and disabled logins (username only, never the password).
  **Accounts** shows "Created an account" and "Changed an account". Times are in India time.
- [ ] **Download CSV** downloads the current view.

### D4. Accuracy
- [ ] **Accuracy**: under "User feedback to review", the 👎 from A2 appears with its reason and comment.
- [ ] Type `could not find` in "…must not contain" and click **Add to test set**.
- [ ] Click **Generate from the registry**. It says "Generated 240 questions".
- [ ] Download the **CSV template**, then **Import the department's test set** with it (the 2 sample rows).
- [ ] Click **Run the test set**. A progress bar appears. It takes about 3–4 minutes.
- [ ] Results: about **100%** on the generated questions. There are bars by language, role, source and category, a
  **Failed** list with reasons, **To review by hand** for questions with only a model answer, and **All results (CSV)**.
- [ ] Run again later: the **Accuracy by run** chart shows the trend.

---

## E. Security checks

- [ ] Not logged in, open http://localhost:5192/?tab=today: it asks you to log in. The officer menu isn't shown.
- [ ] As `officer_surat`, ask in For officers: `Projects past their completion date in Ahmedabad`. It's **refused**:
  "your access is limited to Surat". It appears in the Audit log as "Asked about another district".
- [ ] As `officer_surat`: `delete all notices` is **refused** (reports are read-only), and appears as "Tried to change data".
- [ ] As `officer_surat`, open http://localhost:5192/?tab=users: "Administration is for state-level officers".
- [ ] Wrong password 5 times for one user: the next try says "Too many failed attempts", and the account is locked for
  5 minutes. It appears in the Audit log as "Login locked". (Use `citizen_01`, so you don't lock an account you need.)

---

## F. When you are done

Close the windows titled "GujRERA API :8102 / app :5192" (and :8103 / :5193). To test again from scratch, run the
launcher with `-Fresh`. Nothing you did here changed `data\gujrera\gujrera_public.sqlite`.

Automated checks (optional): `python -m pytest tests/test_gujrera_*.py -q` runs 388 tests.
