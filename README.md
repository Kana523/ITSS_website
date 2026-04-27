# ITSS Website

ITS-S (Interstellar Systems) is my EVE Online corporation focused on small-scale industry, planetary interaction, and reactions. This repo hosts the corporation website.

## Pages

- **Home** — Landing page with core corporate info and select merchandise highlights
- **Shop** — Marketplace for in-game item transactions
- **Trade** — Trade-related tooling and listings
- **About** — Extended overview of the corporation and its goals
- **Legal** — Disclaimers and compliance documentation

## Project Structure

```
ITSS_Website/
├── index.html
├── shop/
├── trade/
├── about/
├── legal/
└── assets/
    ├── images/
    │   ├── backgrounds/
    │   ├── icons/
    │   └── items/
    ├── js/
    └── styling/
        ├── css/        # Per-page stylesheets + base.css (CSS variables)
        └── fonts/
```

## Tech Stack

- Plain HTML, CSS, and JavaScript — no framework, no build step
- CSS custom properties defined in `assets/styling/css/base.css`

## Getting Started

Open `index.html` in a browser, or use VS Code Live Server for local development.
