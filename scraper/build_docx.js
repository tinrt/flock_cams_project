// Builds the Task 1 research document as a .docx
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  ExternalHyperlink, BorderStyle, PageBreak, LevelFormat, ShadingType,
  Table, TableRow, TableCell, WidthType, TableLayoutType
} = require("docx");

const BRAND = "1F3864";     // dark blue
const FACT = "1E6B34";      // green
const CONCERN = "9C2B2B";   // red
const GREY = "595959";

// ---------- helpers ----------
function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 320, after: 140 },
    children: [new TextRun({ text, bold: true, color: BRAND, size: 30 })],
  });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 220, after: 100 },
    children: [new TextRun({ text, bold: true, color: BRAND, size: 25 })],
  });
}
// paragraph from an array of runs/text; supports inline citation refs
function p(children, opts = {}) {
  const kids = (Array.isArray(children) ? children : [children]).map((c) =>
    typeof c === "string" ? new TextRun({ text: c, size: 22 }) : c
  );
  return new Paragraph({
    spacing: { after: 140, line: 276 },
    alignment: opts.align || AlignmentType.LEFT,
    children: kids,
  });
}
function t(text, extra = {}) { return new TextRun({ text, size: 22, ...extra }); }
function bullet(children, level = 0) {
  const kids = (Array.isArray(children) ? children : [children]).map((c) =>
    typeof c === "string" ? new TextRun({ text: c, size: 22 }) : c
  );
  return new Paragraph({
    numbering: { reference: "bullets", level },
    spacing: { after: 80, line: 276 },
    children: kids,
  });
}
function link(text, url) {
  return new ExternalHyperlink({
    link: url,
    children: [new TextRun({ text, style: "Hyperlink", size: 22 })],
  });
}
// small colored tag like [Confirmed fact] / [Concern]
function tag(text, color) {
  return new TextRun({ text: text + "  ", bold: true, color, size: 20 });
}
// a shaded callout box (single-cell table)
function callout(title, titleColor, bodyParas, fill) {
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    columnWidths: [9360],
    layout: TableLayoutType.FIXED,
    borders: {
      top: { style: BorderStyle.SINGLE, size: 2, color: titleColor },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: titleColor },
      left: { style: BorderStyle.SINGLE, size: 12, color: titleColor },
      right: { style: BorderStyle.SINGLE, size: 2, color: titleColor },
      insideHorizontal: { style: BorderStyle.NONE },
      insideVertical: { style: BorderStyle.NONE },
    },
    rows: [
      new TableRow({
        children: [
          new TableCell({
            width: { size: 9360, type: WidthType.DXA },
            shading: { type: ShadingType.CLEAR, color: "auto", fill },
            margins: { top: 120, bottom: 120, left: 160, right: 160 },
            children: [
              new Paragraph({
                spacing: { after: 80 },
                children: [new TextRun({ text: title, bold: true, color: titleColor, size: 22 })],
              }),
              ...bodyParas,
            ],
          }),
        ],
      }),
    ],
  });
}
function ref(n, authorTitle, outlet, date, url) {
  return new Paragraph({
    spacing: { after: 120, line: 264 },
    children: [
      new TextRun({ text: `[${n}] `, bold: true, size: 21 }),
      new TextRun({ text: authorTitle, size: 21 }),
      new TextRun({ text: ` ${outlet}. `, italics: true, size: 21 }),
      new TextRun({ text: `Published ${date}. `, size: 21, color: GREY }),
      new ExternalHyperlink({ link: url, children: [new TextRun({ text: url, style: "Hyperlink", size: 21 })] }),
    ],
  });
}
function cite(nums) { return new TextRun({ text: ` [${nums}]`, size: 22, superScript: false, color: BRAND }); }

// ---------- document body ----------
const children = [];

// Title block
children.push(new Paragraph({
  spacing: { before: 400, after: 60 },
  alignment: AlignmentType.LEFT,
  children: [new TextRun({ text: "Flock Safety Cameras: A Plain-Language Overview", bold: true, color: BRAND, size: 44 })],
}));
children.push(new Paragraph({
  spacing: { after: 40 },
  children: [new TextRun({ text: "How they work, what they collect, and how they differ from older license plate readers", italics: true, color: GREY, size: 24 })],
}));
children.push(new Paragraph({
  spacing: { after: 200 },
  children: [new TextRun({ text: "Background briefing for the Information Systems PhD research project “flock_cams”  ·  Prepared 8 September 2026", color: GREY, size: 20 })],
}));
children.push(new Paragraph({
  spacing: { after: 240 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: BRAND, space: 6 } },
  children: [new TextRun({ text: "" })],
}));

// How to read this document
children.push(callout(
  "How to read this document",
  BRAND,
  [
    p([t("This briefing keeps two things apart on purpose. Statements marked "), tag("[Confirmed fact]", FACT), t("describe what cameras and companies actually do, or events that have been reported by reliable sources. Statements marked "), tag("[Concern]", CONCERN), t("describe worries, criticisms, or possible effects raised by advocates, researchers, or officials — these are interpretations and debates, not settled facts.")]),
    p([t("Every factual claim ends with a number in brackets, like "), new TextRun({ text: "[1]", color: BRAND, size: 22 }), t(", that points to the full source in the References list at the end. Sources include the publication date and a clickable link.")]),
  ],
  "F2F5FB"
));

// 1. What are Flock cameras
children.push(h1("1. What are Flock Safety cameras?"));
children.push(p([
  t("Flock Safety is a company that sells camera systems used mainly by police departments, but also by cities, businesses, and neighborhood groups. Its best-known product is an "),
  t("automated license plate reader", { bold: true }),
  t(" (often shortened to ALPR or LPR). These are small cameras, usually mounted on poles beside roads, that take a picture of every vehicle that passes by."),
  cite("5,6"),
]));
children.push(p([
  t("The cameras are sold as a subscription service. Instead of buying the cameras outright, a customer pays a recurring fee, and Flock installs the cameras and runs the software and storage behind them. As of 2026, Flock reported operating "),
  t("more than 120,000 cameras across 49 U.S. states", { bold: true }),
  t("."),
  cite("1,2"),
]));
children.push(callout("[Confirmed fact]", FACT, [
  p([t("Flock says its cameras assisted in over one million criminal investigations and public-safety incidents in 2025, and helped locate nearly 10,000 missing people. These are figures reported by the company."), cite("1")]),
], "EAF3EC"));

// 2. How they work
children.push(h1("2. How the cameras work, step by step"));
children.push(p("The basic process is simple to describe. Flock and independent reporting describe roughly the same sequence:"));
children.push(bullet([t("Take the picture. ", { bold: true }), t("As a vehicle passes, the camera captures several still images — reporting suggests roughly 6 to 12 snapshots per vehicle."), cite("1,6")]));
children.push(bullet([t("Read the plate. ", { bold: true }), t("Software reads the license plate characters from the image (this step is called optical character recognition, or OCR) and notes the plate’s home state."), cite("6")]));
children.push(bullet([t("Describe the vehicle. ", { bold: true }), t("AI software also records details about the vehicle itself — things like make, body type, and color, plus distinguishing features when visible."), cite("4,6")]));
children.push(bullet([t("Add time and place. ", { bold: true }), t("Each detection is stamped with the date, time, and camera location, so it becomes a record of “this vehicle was here, at this moment.”"), cite("6")]));
children.push(bullet([t("Check against a watch list. ", { bold: true }), t("Customers can load “hot lists” (for example, stolen cars, AMBER Alerts, or active warrants). If a passing plate matches, the system sends an instant alert."), cite("6")]));
children.push(bullet([t("Store and make searchable. ", { bold: true }), t("Every detection is saved to Flock’s cloud so it can later be searched, mapped, or linked to a case."), cite("6")]));
children.push(p([
  t("Flock states its cameras achieve, under good conditions, over 98% plate capture, over 96% character (OCR) accuracy, and over 97% accuracy on the plate’s state. The company also says a camera read should be treated as an "),
  t("investigative lead that needs human review", { italics: true }),
  t(", not as proof on its own."),
  cite("6"),
]));

// 3. What they collect
children.push(h1("3. What information the cameras collect"));
children.push(p("Older plate readers mostly recorded a plate number. Flock cameras record much more. The main categories reported are:"));
children.push(bullet([t("License plate number and state.", { bold: true }), cite("6")]));
children.push(bullet([new TextRun({ text: "“Vehicle Fingerprint.” ", bold: true, size: 22 }), t("An AI-generated description of the vehicle: make, body type, color, visible damage or dents, and distinguishing features such as roof racks, bumper stickers, or aftermarket wheels. This lets police search for a vehicle even when they do not have the plate number."), cite("4,7")]));
children.push(bullet([t("Time and location.", { bold: true }), t(" The date, time, and place of each sighting."), cite("6")]));
children.push(bullet([t("People detection (on some systems). ", { bold: true }), t("Reporting describes a feature that can find people in footage using plain-language descriptions, such as “man in a blue shirt and cowboy hat.”"), cite("4")]));
children.push(bullet([new TextRun({ text: "Audio detection (“Raven”, on some systems). ", bold: true, size: 22 }), t("Reporting describes audio sensors that listen for specific sounds — gunshots, fireworks, drag racing, or crashes — and save short (about three-second) clips when triggered."), cite("4")]));
children.push(callout("[Confirmed fact] What the cameras generally do not read", FACT, [
  p([t("Flock states its license plate cameras photograph vehicles, not people’s faces, and are not facial-recognition cameras. Independent reporting focuses on the vehicle and location data described above rather than face identification."), cite("6")]),
], "EAF3EC"));

// 4. Storage
children.push(h1("4. How the information is stored"));
children.push(p([
  t("Detections are kept in Flock’s cloud (its central computer systems), not just on the camera. How long a record is kept is called the "),
  t("retention period", { bold: true }),
  t(". This has changed recently and is important for the research:"),
]));
children.push(bullet([t("Flock’s original default retention was about 30 days (one month)."), cite("1,2")]));
children.push(bullet([t("In August 2026, Flock reduced the default to 7 days (one week)."), cite("1,10")]));
children.push(bullet([t("Customers can keep data longer. An “Evidence Mode” lets an agency preserve specific records tied to an active case or cold case, and existing customers may keep their previously approved, longer retention settings."), cite("2,10")]));
children.push(p([t("Flock also says customers, not Flock, own the data their cameras capture and control who may access or share it."), cite("10")]));

// 5. Searching
children.push(h1("5. How the information is searched"));
children.push(p([
  t("Stored detections become a searchable database. An authorized user (typically a police employee) can search in two main ways:"),
]));
children.push(bullet([t("Real-time alerts. ", { bold: true }), t("If a passing plate matches a hot list, the system pushes an immediate alert to officers."), cite("6")]));
children.push(bullet([t("Historical search. ", { bold: true }), t("A user can look back through saved records — for example, searching for a plate, or for all silver SUVs with a roof rack seen near a location during a time window. Because many cameras feed one system, results can map a vehicle’s movements across many points."), cite("3,7")]));
children.push(callout("[Confirmed fact] The scale of searching", FACT, [
  p([t("An analysis by the ACLU of Massachusetts found more than 450,000 nationwide database searches in a single 30-day period in spring 2025. It also found that officers often typed vague reasons for a search, such as “investigation” or “susp,” rather than specific case details."), cite("3")]),
], "EAF3EC"));

// 6. Sharing
children.push(h1("6. How the information is shared"));
children.push(p([
  t("This is one of the biggest differences between Flock and older systems. Flock operates a "),
  t("nationwide sharing network", { bold: true }),
  t(". An agency can choose to share its camera data with other agencies, and in return gain the ability to search data shared by others. Advocates describe this as a “you show me yours, I’ll show you mine” arrangement: turning on national sharing (a setting sometimes labeled “Enable National Lookup”) unlocks access to a very large pool of data from thousands of other places."),
  cite("1,3"),
]));
children.push(p([t("As of mid-2025, the ACLU of Massachusetts counted roughly 7,000 networks and about 90,000 cameras feeding this system. This means a local camera’s data can, in practice, be searchable by officers in distant states."), cite("3")]));
children.push(p([t("Flock says agencies keep “local control” and can limit which offense types other customers are allowed to search their data for — for example, allowing stolen-vehicle searches while blocking immigration-related queries."), cite("2,10")]));

// 7. Differences
children.push(h1("7. How Flock cameras differ from older license plate readers"));
children.push(p("License plate readers are not new. Police have used them for years. Flock did not invent the plate reader; what changed is the scale, the connectivity, and the kind of data collected. The table below summarizes the main differences reported by reliable sources."));

// comparison table
function cellPara(runs, opts = {}) {
  return new Paragraph({
    spacing: { after: 40, line: 252 },
    children: (Array.isArray(runs) ? runs : [runs]).map(r => typeof r === "string" ? new TextRun({ text: r, size: 20, ...opts }) : r),
  });
}
function hdrCell(text, w) {
  return new TableCell({
    width: { size: w, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, color: "auto", fill: BRAND },
    margins: { top: 80, bottom: 80, left: 100, right: 100 },
    children: [new Paragraph({ children: [new TextRun({ text, bold: true, color: "FFFFFF", size: 20 })] })],
  });
}
function bodyCell(runs, w, fill) {
  return new TableCell({
    width: { size: w, type: WidthType.DXA },
    shading: fill ? { type: ShadingType.CLEAR, color: "auto", fill } : undefined,
    margins: { top: 80, bottom: 80, left: 100, right: 100 },
    children: [cellPara(runs)],
  });
}
const COLS = [1900, 3730, 3730];
const rowsData = [
  ["Reach", "Older systems were often a camera on a patrol car or a few fixed cameras run by one agency.", "A dense, always-on network of 120,000+ fixed cameras run as a shared national service."],
  ["Connection", "Data often stayed with the local agency, or in limited regional sharing.", "Built-in nationwide sharing; one click can open searching across thousands of networks."],
  ["What is recorded", "Mainly the plate number, time, and place.", "Plate plus an AI “Vehicle Fingerprint” (color, damage, stickers, roof racks); some units add people- and sound-detection."],
  ["Search style", "Look up a known plate.", "Search by vehicle description even without a plate; map movements across many cameras."],
  ["Who runs it", "Usually the police agency itself.", "A private company hosts the cameras, software, storage, and the sharing network."],
];
const tableRows = [
  new TableRow({ tableHeader: true, children: [hdrCell("Feature", COLS[0]), hdrCell("Older license plate readers", COLS[1]), hdrCell("Flock-style networked cameras", COLS[2])] }),
];
rowsData.forEach((r, i) => {
  const fill = i % 2 ? "F2F5FB" : "FFFFFF";
  tableRows.push(new TableRow({ children: [
    new TableCell({ width: { size: COLS[0], type: WidthType.DXA }, shading: { type: ShadingType.CLEAR, color: "auto", fill }, margins: { top: 80, bottom: 80, left: 100, right: 100 }, children: [cellPara(r[0], { bold: true })] }),
    bodyCell(r[1], COLS[1], fill),
    bodyCell(r[2], COLS[2], fill),
  ]}));
});
children.push(new Table({ width: { size: 100, type: WidthType.PERCENTAGE }, columnWidths: COLS, layout: TableLayoutType.FIXED, rows: tableRows }));
children.push(p([t("For background, privacy researchers describe three older ALPR forms: fixed cameras at set points, mobile cameras on patrol cars (sometimes driven street-by-street in a practice called “gridding”), and portable trailer units. Some older commercial vendors, such as Vigilant Solutions, also gathered and resold plate data. Flock’s model combines the fixed-camera approach with a large, centrally hosted sharing network and richer AI data."), cite("7")], { align: AlignmentType.LEFT }));

// 8. Concerns
children.push(h1("8. Concerns and possible unintended consequences"));
children.push(p([t("The items below are "), tag("[Concern]", CONCERN), t("statements: criticisms, worries, and possible effects raised by civil-liberties groups, researchers, and public officials. Where an actual documented event is a confirmed fact, it is marked separately.")]));

children.push(h2("Mass tracking of ordinary people"));
children.push(p([tag("[Concern]", CONCERN), t("Critics argue that because the cameras record every vehicle — not just suspects — the system creates a detailed history of ordinary people’s movements, potentially revealing trips to workplaces, schools, healthcare, places of worship, or protests."), cite("1,2")]));
children.push(p([tag("[Confirmed fact]", FACT), t("A 2021 EFF study of California data found only 0.05% of collected plate data was relevant to a public-safety interest — i.e., the overwhelming majority of records were of uninvolved people."), cite("7")]));

children.push(h2("Misuse by insiders"));
children.push(p([tag("[Confirmed fact]", FACT), t("Reported misuse includes a Kentucky officer accused of using the cameras to track an ex-girlfriend more than 2,000 times; an officer in Revere, Massachusetts accused of tracking a former girlfriend; and six Savannah, Georgia police employees fired in August 2026 over suspected abuse. The Institute for Justice has documented over 100 ALPR abuse incidents."), cite("1,11")]));
children.push(p([tag("[Concern]", CONCERN), t("Advocates argue these cases show that a powerful search tool with weak logging invites stalking and other abuse.")]));

children.push(h2("Wrong-person stops from misreads"));
children.push(p([tag("[Confirmed fact]", FACT), t("The Institute for Justice documented at least 27 cases since 2018 of innocent motorists wrongly stopped, detained at gunpoint, or jailed after camera errors, most occurring after 2023. Examples: a couple held at gunpoint in Sherwood, Arkansas (Feb 2026) with a six-week-old in the car after a misread; a wrongful arrest in San Diego (Nov 2025) based on a “vehicle signature” match to the wrong car, where one person spent nearly a month in jail; and grandparents held at gunpoint in Morristown, Tennessee (June 2024) after an “O” was read as “0.”"), cite("8")]));
children.push(p([tag("[Confirmed fact]", FACT), t("A Roseville, California police review found a 71% misread rate among 1,427 stolen-vehicle and felony alerts from 2023–2024. Flock disputes this figure, saying its cameras read more than 96% of characters correctly under optimal conditions and blaming non-standard camera placement."), cite("9")]));
children.push(p([tag("[Concern]", CONCERN), t("Critics say that even a small error rate, multiplied across billions of monthly reads, produces many false hits that can lead to dangerous encounters. Flock counters that a read is only a lead and officers must verify before acting."), cite("6,8")]));

children.push(h2("Wide sharing and access by outside agencies"));
children.push(p([tag("[Confirmed fact]", FACT), t("The ACLU of Massachusetts reported that officers in other states could search Massachusetts residents’ data, and cited a case involving a Texas officer’s search connected to an abortion investigation. It also reported federal access, including by ICE and CBP."), cite("3")]));
children.push(p([tag("[Concern]", CONCERN), t("Advocates worry that nationwide sharing lets data collected for local policing be used for purposes a community never approved — such as immigration or abortion enforcement — and that vague search justifications make oversight hard."), cite("2,3")]));

children.push(h2("Public and government backlash"));
children.push(p([tag("[Confirmed fact]", FACT), t("By late 2026, more than 50 cities and counties had canceled or deactivated Flock cameras. Florida moved to bar plate readers on state highways; Texas Gov. Greg Abbott paused state funding; Pennsylvania Gov. Josh Shapiro backed a bipartisan ban bill; and U.S. Sen. Josh Hawley opened an investigation. Cameras were reported vandalized in at least 36 states."), cite("1,11")]));

children.push(h2("Company responses (guardrails)"));
children.push(p([tag("[Confirmed fact]", FACT), t("In August 2026 Flock announced safeguards: a 7-day default retention; “Audit Assistance” and automatic lockouts to flag abnormal use (mandatory by end of 2026); required case codes for searches (by end of 2026); the ability to filter which offenses other agencies can search; mandatory multi-factor login; an independent security review by Bishop Fox (findings due September 2026); and public transparency portals for 1,500+ agencies."), cite("10")]));
children.push(p([tag("[Concern]", CONCERN), t("Civil-liberties groups such as the ACLU argue these updates do not fix the core problem — that the system still collects and shares the movements of millions of people who are not suspected of anything."), cite("2")]));

// 9. Quick glossary
children.push(h1("9. Quick glossary"));
children.push(bullet([t("ALPR / LPR: ", { bold: true }), t("Automated (or automatic) license plate reader — a camera system that automatically reads and records plates.")]));
children.push(bullet([t("OCR: ", { bold: true }), t("Optical character recognition — software that turns a picture of text (the plate) into readable characters.")]));
children.push(bullet([t("Hot list: ", { bold: true }), t("A list of plates the system watches for (e.g., stolen cars); a match triggers an alert.")]));
children.push(bullet([t("Vehicle Fingerprint: ", { bold: true }), t("An AI description of a vehicle’s look (color, damage, stickers, racks), used to search without a plate number.")]));
children.push(bullet([t("Retention period: ", { bold: true }), t("How long a record is stored before it is automatically deleted.")]));
children.push(bullet([t("National Lookup / sharing network: ", { bold: true }), t("A setting that lets one agency search data shared by many others across the country.")]));

// References
children.push(new Paragraph({ children: [new PageBreak()] }));
children.push(h1("References"));
children.push(p([new TextRun({ text: "All sources were accessed on 8 September 2026. Vendor sources (Flock Safety) are labeled as such; the remainder are news outlets, civil-liberties organizations, or research/reference sources.", italics: true, color: GREY, size: 20 })]));
children.push(ref(1, "Hoffmann, V. “Flock cameras: How a police tool sparked a surveillance revolt in the US.”", "The Christian Science Monitor", "4 September 2026", "https://www.csmonitor.com/USA/Society/2026/0904/flock-cameras-privacy-surveillance"));
children.push(ref(2, "Marlow, C. “Despite ‘New’ Updates, Flock’s Creepy Cameras Remain a Major Civil Liberties Threat.”", "American Civil Liberties Union (ACLU)", "13 August 2026", "https://www.aclu.org/news/privacy-technology/tracking-alpr-cameras/despite-new-updates-flocks-creepy-cameras-remain-major-civil-liberties-threat"));
children.push(ref(3, "Epstein, G. “Flock Gives Law Enforcement All Over the Country Access to Your Location.”", "The Data for Justice Project, ACLU of Massachusetts", "7 October 2025", "https://data.aclum.org/2025/10/07/flock-gives-law-enforcement-all-over-the-country-access-to-your-location/"));
children.push(ref(4, "Hively, A. “Flock Cameras Are Tracking More Than License Plates: Here’s Where All That Data Goes.”", "BGR", "15 June 2026", "https://www.bgr.com/2192089/flock-cameras-scanning-license-plate-audio-data-use/"));
children.push(ref(5, "Oates, Z., & Sanchez, E. “Flock cameras explained: How automated plate readers work and their impact in South Texas.”", "KSAT (San Antonio)", "10 August 2026", "https://www.ksat.com/news/local/2026/08/11/flock-cameras-what-automated-license-plate-readers-are-and-why-theyre-controversial-in-south-texas/"));
children.push(ref(6, "Flock Safety (vendor). “How an Automatic License Plate Recognition System Works.”", "Flock Safety", "updated 23 July 2026", "https://www.flocksafety.com/blog/how-an-automatic-license-plate-recognition-system-works"));
children.push(ref(7, "Electronic Frontier Foundation. “Automated License Plate Readers (ALPRs).”", "EFF Street-Level Surveillance (reference)", "accessed 8 September 2026", "https://sls.eff.org/technologies/automated-license-plate-readers-alprs"));
children.push(ref(8, "Ingraham, C. “Dozens of Innocent Motorists Have Been Pulled Over, Detained at Gunpoint, or Jailed Due to AI License Plate Camera Errors.”", "Institute for Justice", "1 July 2026 (updated 20 July 2026)", "https://ij.org/dozens-of-innocent-motorists-have-been-pulled-over-detained-at-gunpoint-or-jailed-due-to-ai-license-plate-camera-errors/"));
children.push(ref(9, "Srinivasa, P. “Roseville Police Find Flock Cameras Misread 71% of License Plate Alerts, Raising Surveillance Concerns.”", "Davis Vanguard", "5 August 2026", "https://davisvanguard.org/2026/08/roseville-police-ai-camera-errors/"));
children.push(ref(10, "Flock Safety (vendor). “Flock Updates Privacy, Accountability, Security, and Transparency Safeguards.”", "Flock Safety", "13 August 2026", "https://www.flocksafety.com/blog/flock-guardrails-address-lpr-privacy-concerns-and-police-transparency"));
children.push(ref(11, "Zahn, M. “Flock cameras trigger nationwide backlash over privacy concerns, police abuse.”", "ABC News", "1 September 2026", "https://abcnews.com/US/flock-cameras-trigger-nationwide-backlash-privacy-concerns-police/story?id=136084771"));

// ---------- assemble ----------
const doc = new Document({
  creator: "flock_cams research project",
  title: "Flock Safety Cameras: A Plain-Language Overview",
  description: "Background briefing on how Flock cameras work, what they collect, and how they differ from older license plate readers.",
  numbering: {
    config: [{
      reference: "bullets",
      levels: [
        { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 260 } } } },
        { level: 1, format: LevelFormat.BULLET, text: "◦", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 900, hanging: 260 } } } },
      ],
    }],
  },
  styles: {
    default: { document: { run: { font: "Calibri", size: 22 } } },
    paragraphStyles: [
      { id: "Hyperlink", name: "Hyperlink", basedOn: "Normal", run: { color: "1155CC", underline: {} } },
    ],
  },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1080, bottom: 1080, left: 1440, right: 1440 } } },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("/home/claude/flock_cams_project/research_document/Flock_Safety_Cameras_Overview.docx", buf);
  console.log("Wrote docx, bytes:", buf.length);
});
