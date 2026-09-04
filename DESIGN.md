---
version: alpha
name: ModularDark
description: Dense dark operator console for a Windows module manager — Mica blacks, single blue signal, mono for machine text.
colors:
  primary: "#2E75B6"
  bg: "#101010"
  surface: "#161616"
  surface2: "#1D1D1D"
  well: "#0E0E0E"
  text: "#E8E8E8"
  muted: "#9A9A9A"
  accent: "#2E75B6"
  accent-hover: "#1F5C8C"
  accent-bright: "#6DB3F2"
  on-accent: "#FFFFFF"
  success: "#4CAF7D"
  warning: "#D9A441"
  danger: "#D9534F"
  tier-gold: "#C9A227"
typography:
  title:
    fontFamily: Segoe UI
    fontSize: 1.25rem
    fontWeight: 600
    lineHeight: 1.2
  card-name:
    fontFamily: Segoe UI
    fontSize: 0.8125rem
    fontWeight: 600
    lineHeight: 1.3
  body-md:
    fontFamily: Segoe UI
    fontSize: 0.875rem
    lineHeight: 1.5
  caption:
    fontFamily: Segoe UI
    fontSize: 0.75rem
    lineHeight: 1.4
  mono:
    fontFamily: Consolas
    fontSize: 0.75rem
    lineHeight: 1.4
rounded:
  sm: 6px
  md: 10px
  lg: 12px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 14px
  lg: 20px
  xl: 28px
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.sm}"
    padding: 12px
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
    textColor: "{colors.on-accent}"
  button-ghost:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: 10px
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.lg}"
    padding: 14px
  module-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.lg}"
    padding: 14px
  chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.full}"
    padding: 12px
  chip-on:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.full}"
    padding: 12px
  input:
    backgroundColor: "{colors.well}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: 10px
  page:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: 20px
  stat-tile:
    backgroundColor: "{colors.surface2}"
    textColor: "{colors.text}"
    rounded: "{rounded.lg}"
    padding: 14px
  caption-muted:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.muted}"
    rounded: "{rounded.sm}"
    padding: 8px
  rank-s:
    backgroundColor: "{colors.tier-gold}"
    textColor: "#101010"
    rounded: "{rounded.sm}"
    padding: 8px
  status-ok:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.success}"
    rounded: "{rounded.sm}"
    padding: 8px
  status-err:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.danger}"
    rounded: "{rounded.sm}"
    padding: 8px
  status-warn:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.warning}"
    rounded: "{rounded.sm}"
    padding: 8px
---

## Overview

ModularDark is the visual identity of a desktop module manager: an operator
console, not a marketing page. Screens are dense with cards, states, logs and
IDs. The mood is quiet control-room — near-black Mica surfaces, one blue
reserved strictly for action and signal, monospace reserved strictly for
machine text (IDs, paths, specs, counters). Nothing decorative earns pixels.

## Colors

- **primary (#2E75B6):** The brand key and the interaction driver — same blue
  as `accent`, deliberately. One blue, two names: spec compliance plus intent.
- **bg (#101010):** Page base. Matches Mica-under-dark so the window melts
  into the desktop.
- **surface (#161616) / surface2 (#1D1D1D) / well (#0E0E0E):** Cards on base,
  tiles on cards, input wells cut deepest. One step per nesting level.
  Hairlines between them sit at #2B2B2B — a raw value, not a token, because
  borders must never draw the eye.
- **text (#E8E8E8):** Primary copy. **muted (#9A9A9A):** Metadata, timestamps,
  secondary lines — never body copy, never on accent fills.
- **accent (#2E75B6):** The single interaction driver — primary buttons,
  toggles-on, active chips, progress. **accent-bright (#6DB3F2):** Links and
  hover only.
- **success / warning / danger:** Status dots, badges, log levels. Never used
  as decoration.
- **tier-gold (#C9A227):** Rank gradient anchor for S-tiers. Used in one place
  (rank display) so it keeps its meaning.

## Typography

Segoe UI for everything human; Consolas for everything machine. Hierarchy
comes from size and weight, never from extra families. Vietnamese diacritics
must stay legible at caption size — no condensed faces, no sub-12px muted
body text.

## Layout

4px baseline. Card padding `md` (14px), intra-card row gaps `sm` (8px),
inter-card gaps `md`, page padding `lg` (20px). Cards are full-bleed within
their column — no orphan gutters on the right. Dense grids beat long scrolls:
prefer wrapping card grids over single-column lists for collections.

## Shapes

`sm` on inputs and buttons, `lg` on cards, `full` only for avatar dots, chips
and pill badges. One radius per component class — no mixed rounding inside a
single card.

## Components

- `button-primary` is the single high-emphasis action per row (Start, Tải).
  Everything else is `button-ghost`.
- `module-card` fills its column edge-to-edge; state is a colored dot +
  mono state word, never a paragraph.
- `chip` / `chip-on` filter collections; count sits in muted mono.
- `input` is near-black (#0E0E0E) so fields read as wells cut into the card.
- Toggle ON is accent; toggle OFF is border-gray. No labels needed beyond
  On/Off affordance.

## Do's and Don'ts

- **Do** use token references (`{colors.accent}`) in components, never raw
  hex twice.
- **Do** keep machine text (IDs, specs, counters, paths) in mono.
- **Don't** add a second accent — extend usage of the one blue first.
- **Don't** put muted text on accent fills; contrast dies.
- **Don't** nest component variants. `chip-on` is a sibling of `chip`,
  not a child.
