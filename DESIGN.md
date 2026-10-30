---
name: Signetum
description: A typographic proof specimen.
colors:
  forest: "#183e2d"
  forest-hover: "#24573e"
  paper: "#f5f5ed"
  ink: "#202c24"
  muted: "#566359"
  rule: "#c7cdc1"
  white: "#ffffff"
  wash: "#e7ecdf"
  lime: "#d5eba8"
typography:
  display:
    fontFamily: '"Instrument Serif", "Songti SC", STSong, Georgia, serif'
    fontSize: "clamp(56px, 7.4vw, 96px)"
    fontWeight: 400
    lineHeight: 1.02
    letterSpacing: "-0.025em"
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif'
    fontSize: "17px"
    lineHeight: 1.65
rounded:
  control: "4px"
spacing:
  page: "clamp(24px, 5vw, 72px)"
components:
  button-primary:
    backgroundColor: "{colors.forest}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "12px 20px"
---

# Design System: Signetum

## Overview

**Creative North Star: "The Proof Specimen"**

Editorial typography and continuous ruled surfaces make precise records readable.
The compact signet is the brand anchor. Product facts and page strategy live in
PRODUCT.md and the homepage surface brief rather than being repeated here.

## Colors

Forest carries actions and the dense reading section. Paper is the page ground;
white and wash distinguish the illustrative record. Muted ink remains legible.

## Typography

Instrument Serif is self-hosted for display; native serif fallbacks cover Chinese.
Body and navigation use the platform sans. Monospace is reserved for source names
and the copyable request. Chinese headings use the measured locale-specific scale
in `site/styles.css`; narrow screens retain natural reading order.

## Layout

The page container is capped at 1184px. Related information uses fine rules rather
than detached feature cards. At 800px narrative columns stack; at 540px the proof
specimen becomes sequential rows. Body measures stay bounded for reading.

## Elevation & Depth

Flat surfaces, ink contrast and fine rules provide hierarchy; no shadows.

## Shapes

The geometric signet is one SVG. Controls have modest corners; content remains square.

## Components

The primary button copies the setup request and announces its result. A denied
clipboard opens the manual prompt. Without scripts, native source links and prompt
remain available. Disclosures use native HTML; keyboard focus has a visible ring.

## Do's and Don'ts

- Do preserve contrast, source labels and native reading order across locales.
- Do keep examples explicitly illustrative rather than resembling earned receipts.
- Don't use the old mascot or repeat decorative mark resolutions.

Font provenance: [Instrument Serif](https://github.com/Instrument/instrument-serif/tree/65c0ef225f386a3c7e87570a4aa9cc0262c2fd81), unmodified regular TTF;
its original SIL OFL 1.1 license ships beside it in `site/fonts/OFL.txt`.
The social PNG embeds its authored HTML rendering recipe and source provenance.
