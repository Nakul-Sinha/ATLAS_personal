# ATLAS landing page

A minimal, single-screen landing page: one frosted-glass card over a dark, moody
aurora background with fine film grain. Short by design; the full details live in
the repository README.

It is fully self-contained static HTML and CSS with a tiny optional script. No
build step, no external requests, no remote fonts or images (the mark and grain
are inline SVG).

## Deploy

- Open `index.html` directly in a browser, or
- Serve the folder with any static server:

  ```bash
  python -m http.server 8000
  ```

- Or enable GitHub Pages pointing at this folder. A `.nojekyll` file is included so
  Pages serves it verbatim.
