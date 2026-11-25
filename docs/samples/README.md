# Sample files for the data onboarding console

`department_project_details_sample.csv` adds site addresses to eight real projects from the public GUJRERA
records (the areas are taken from the project names). Upload it in **Data onboarding** (log in as
`officer_state`): it is recognised as *Extra details for projects already loaded*. The check shows 8 changed
and 2 rejected rows: one registration number that is not in the registry and one that is not a RERA number.
The `Contact Phone` column is not read. The phone numbers are made up.

After loading, ask "RERA approved projects in Bopal" or "અમદાવાદના બોપલ વિસ્તારમાં RERA માન્ય પ્રોજેક્ટ કયા છે?":
the projects come back by address.

## Sample circulars

`circulars/` holds three PDFs made by `scripts/make_sample_circulars.py` for testing the Circulars page. Every
page is stamped "SAMPLE FOR TESTING: NOT AN OFFICIAL GUJRERA CIRCULAR" and the wording is written for testing,
not taken from real circulars:

* `sample_circular_qpr_en.pdf`: English, with a text layer (quarterly progress reports);
* `sample_paripatra_advertisement_gu.pdf`: Gujarati; its text layer is garbled, as in many Gujarati PDFs, so it
  is read with OCR (RERA number and QR code in advertisements);
* `sample_circular_extension_scanned.pdf`: a scanned page with no text layer, read with OCR (extension of
  registration).

Log in as `officer_state`, open **Circulars**, upload them, check the details and publish. Then ask Ask Saathi,
for example "QPR ભરવા અંગે પરિપત્ર શું કહે છે?", "Is there a circular on showing the RERA number in
advertisements?" or "તાજેતરના પરિપત્રો". For the POC, load the real circulars the department shares.
