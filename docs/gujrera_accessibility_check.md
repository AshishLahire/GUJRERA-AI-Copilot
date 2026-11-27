# Accessibility check of the citizen screens (27 November 2026)

An automated pre-audit against the WCAG 2.1 Level AA items that a script can test. It is not the formal
GIGW / WCAG audit the use case document asks for before go-live: that needs an accessibility auditor and
screen-reader testing by people.

**Screens:** Overview, Check an ad, Ask Saathi (empty and with answers, cards and sources), My complaint,
Before-you-buy report, Agreement checker, Watched projects, Interest calculator, Order tracker, and the page
shown when the service is down. The interface was in Gujarati.

**Conditions:** light and dark theme; desktop (1280 px), phone (375 px) and 320 px wide (the width WCAG uses
for reflow, the same as 400% zoom).

| Check (WCAG 2.1 criterion) | Result |
|---|---|
| Text contrast at least 4.5:1, or 3:1 for large text (1.4.3) | No failures |
| Images have a text alternative (1.1.1) | No failures |
| Buttons and links have an accessible name (4.1.2) | No failures |
| Form fields have a label (1.3.1, 3.3.2) | No failures |
| Page language is set, and changes with the chosen language (3.1.1) | Set (`gu`, `hi` or `en`) |
| No duplicate element IDs (4.1.1) | None |
| Headings do not skip levels (1.3.1) | No jumps |
| Keyboard focus is visible on every control (2.4.7) | Visible on all controls tested |
| No sideways scrolling at 320 px (1.4.10) | None |
| Skip-to-content link (2.4.1) | Present |

The checker was confirmed to work by adding deliberate faults (faint text, an unlabelled field, an image
without alternative text), which it reported.

**Not covered here, for the formal audit:** screen-reader use (NVDA, TalkBack) in Gujarati and Hindi; keyboard
order through the complaint and chat flows; text resizing to 200%; error messages announced to assistive
technology; captions or transcripts if video is added; GIGW-specific items (bilingual pages, contact and
policy pages).
