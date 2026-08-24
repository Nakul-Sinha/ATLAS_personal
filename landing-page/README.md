# ATLAS Landing Page

A self-contained static landing page for ATLAS (Autonomous Task Learning and Action System), a full-stack AI agent that sees your screen, understands intent, and takes action across desktop apps, browsers, and mobile. It is plain HTML and CSS with one small vanilla JavaScript file for scroll reveals, so there is no build step and no external network dependency.

## Deploy

Pick whichever is easiest:

- **Open directly:** double-click `index.html` to view it in any browser.
- **Serve the folder:** from inside `landing-page/`, run a static server, for example `python -m http.server 8000`, then visit `http://localhost:8000`.
- **GitHub Pages:** in the repository settings, enable Pages and point it at this `landing-page/` folder (or copy its contents to the branch or folder Pages serves). The included `.nojekyll` file tells Pages to serve the files verbatim.

## Files

- `index.html` : page markup and the inline SVG owl mark.
- `styles.css` : all styling, dark theme with a light-scheme fallback and a reduced-motion guard.
- `script.js` : optional scroll-reveal enhancement; the page works fully without it.
- `.nojekyll` : ensures GitHub Pages serves the files as-is.
