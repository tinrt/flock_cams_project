# Flock Safety Research Notes (compiled 2026-09-08)

Sources used, with author and publication date. All content verified by fetching the page unless noted.

## News / advocacy / reference sources

1. **Christian Science Monitor** — "Flock cameras: How a police tool sparked a surveillance revolt in the US" — Victoria Hoffmann — 2026-09-04 — https://www.csmonitor.com/USA/Society/2026/0904/flock-cameras-privacy-surveillance
   - 120,000+ cameras across 49 states; subscription model.
   - Each camera captures 6–12 snapshots per vehicle; plate, model, visible damage, timestamps via AI.
   - Retention reduced from 30 days to 7 days in Aug 2026.
   - Nationwide sharing network; reciprocal-access incentive.
   - Flock claims: assisted 1M+ investigations in 2025; located ~10,000 missing people.
   - Misuse: KY officer tracked ex-girlfriend 2,000+ times; Revere MA officer tracked ex.
   - Florida DOT suspended permits; TX Gov Abbott froze funding; Tempe AZ ended contract.

2. **ACLU** — "Despite 'New' Updates, Flock's Creepy Cameras Remain Major Civil Liberties Threat" — Chad Marlow — 2026-08-13 — https://www.aclu.org/news/privacy-technology/tracking-alpr-cameras/despite-new-updates-flocks-creepy-cameras-remain-major-civil-liberties-threat
   - 120,000+ ALPRs nationwide; centralized nationwide database.
   - Retention default moved from one month to one week; "Evidence Mode" for longer holds.
   - "Local control" over what offenses other customers can search.
   - Concern: AI to "uncover occupants' private patterns of life."

3. **ACLU of Massachusetts (Data for Justice)** — "Flock Gives Law Enforcement All Over the Country Access to Your Location" — Gideon Epstein — 2025-10-07 — https://data.aclum.org/2025/10/07/flock-gives-law-enforcement-all-over-the-country-access-to-your-location/
   - ~7,000 networks, ~90,000 cameras nationwide (July 2025).
   - 80+ MA police departments; >$2M taxpayer funds over 3 years.
   - "Enable National Lookup" one-click reciprocal sharing.
   - 450,000+ nationwide searches in a single 30-day period (spring 2025).
   - Vague justifications like "investigation" / "susp".
   - Cross-state access example; a TX officer search tied to an abortion investigation.
   - Federal access incl. ICE and CBP reported.

4. **BGR** — "Flock Cameras Are Tracking More Than License Plates" — Alec Hively — 2026-06-15 — https://www.bgr.com/2192089/flock-cameras-scanning-license-plate-audio-data-use/
   - Vehicle Fingerprint: make, body type, color, damage, aftermarket wheels, roof racks.
   - People detection: search by "man in blue shirt and cowboy hat."
   - Raven audio: detects gunshots, drag races, fireworks, accidents; 3-second clips.
   - Drone as First Responder (Alpha drones).

5. **KSAT (San Antonio)** — "Flock cameras explained..." — Zaria Oates / Emilio Sanchez — 2026-08-10 — https://www.ksat.com/news/local/2026/08/11/flock-cameras-what-automated-license-plate-readers-are-and-why-theyre-controversial-in-south-texas/
   - Cameras mounted along roadways log where/when a vehicle was seen; make/model/color + plate.
   - Bexar County SO: 35 cameras read 700,000+ plates in 30 days.
   - Officers in GA and NC caught misusing cameras; Guadalupe County ended contract.
   - DeFlock.org tracks camera locations.

6. **Flock Safety (vendor)** — "How an Automatic License Plate Recognition System Works" — updated 2026-07-23 — https://www.flocksafety.com/blog/how-an-automatic-license-plate-recognition-system-works
   - Workflow: capture → plate + vehicle detail recognition → add time/location → hot-list alert matching → searchable storage.
   - Claims: 98%+ plate capture, 96%+ OCR accuracy, 97%+ plate-state accuracy.
   - Default deletion after 7 days unless customer sets otherwise.
   - States an ALPR read is an investigative lead requiring human review, not standalone basis for enforcement.

7. **EFF — Street-Level Surveillance** — "Automated License Plate Readers (ALPRs)" (reference) — https://sls.eff.org/technologies/automated-license-plate-readers-alprs
   - ALPR captures all plates in view + location/date/time; thousands per minute.
   - Three types: fixed/stationary, mobile (patrol-car), trailers.
   - "Gridding" by patrol cars; vendors like Vigilant Solutions resell data.
   - Vehicle fingerprints (color, damage, bumper stickers) in advanced systems.
   - EFF 2021 report: only 0.05% of California ALPR data relevant to a public-safety interest.
   - Regulatory: California S.B. 34 (2015); 2020 state auditor found noncompliance.

8. **Institute for Justice** — "Dozens of Innocent Motorists Have Been Pulled Over, Detained at Gunpoint, or Jailed..." — Christopher Ingraham — 2026-07-01 (upd. 2026-07-20) — https://ij.org/dozens-of-innocent-motorists-have-been-pulled-over-detained-at-gunpoint-or-jailed-due-to-ai-license-plate-camera-errors/
   - 27+ confirmed wrongful-stop cases since 2018, most after 2023; ~2/3 involved drawn guns.
   - Sherwood, AR (Feb 2026): couple at gunpoint after misread, 6-week-old in car.
   - San Diego (Nov 2025): arrest based on "vehicle signature"; wrong car; one person ~1 month in jail.
   - Morristown, TN (Jun 2024): "O" misread as "0"; grandparents at gunpoint.
   - ~1/3 machine errors (obstruction, 0/O, 2/7); ~2/3 human errors.

9. **Davis Vanguard** — "Roseville Police Find Flock Cameras Misread 71% of License Plate Alerts" — Pranathi Srinivasa — 2026-08-05 — https://davisvanguard.org/2026/08/roseville-police-ai-camera-errors/
   - RPD review: 71% misread rate among 1,427 stolen-vehicle/felony alerts (2023–2024).
   - Flock disputes; cites 96%+ character accuracy under optimal conditions; blames non-standard deployment.
   - Officers must verify before action; RPD reported no documented wrongful stops.

10. **Flock Safety (vendor)** — "Flock Updates Privacy, Accountability, Security, and Transparency Safeguards" — 2026-08-13 — https://www.flocksafety.com/blog/flock-guardrails-address-lpr-privacy-concerns-and-police-transparency
    - 7-day default retention; Evidence Mode for cold cases.
    - Audit Assistance + proactive lockout (mandatory by end of 2026).
    - Required case codes by end of 2026.
    - Offense filtering (e.g., block immigration queries).
    - MFA mandatory; Bishop Fox review (findings Sept 2026); vulnerability disclosure program.
    - 1,500+ agencies with public Transparency Portals.

11. **ABC News** — "Flock cameras trigger nationwide backlash over privacy concerns, police abuse" — Max Zahn — 2026-09-01 — https://abcnews.com/US/flock-cameras-trigger-nationwide-backlash-privacy-concerns-police/story?id=136084771
    - 50+ cities/counties canceled or deactivated in 2026.
    - FL revoked ability to place LPRs on state highways; TX Gov Abbott paused funding; PA Gov Shapiro backed a bipartisan ban bill; Sen. Josh Hawley opened investigation.
    - KY officer (2,000+ tracks); 6 Savannah GA employees fired Aug 2026; IJ documented 100+ ALPR abuse incidents.
    - Vandalism in 36+ states.

## Not fetched (blocked), listed for follow-up only — do NOT cite as verified
- NBC News — "Surveillance company Flock moves to increase oversight after police misuse" — https://www.nbcnews.com/tech/security/flock-safety-police-abuse-oversight-data-retention-rcna592217 (robots.txt disallowed)
- The Hill — "Flock Safety announces new privacy rules..." — https://thehill.com/policy/technology/6027324-flock-cameras-ai-surveillance-privacy-updates/ (403)
