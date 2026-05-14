# CSC Tournament Card Generator

Streamlit Community Cloud app for generating 1080x1350 CSC soccer tournament trading cards.

## Files

- `app.py` — main Streamlit app.
- `requirements.txt` — deployment dependencies.
- `assets/background.png` — required final card template.
- `assets/foreground_splashes.png` — optional foreground paint/splash overlay.
- `assets/fonts/` — optional bold TrueType/OpenType fonts.

## Notes

The app processes player photos in memory, removes the background with `rembg`, places the cutout using subject-aware coordinates, draws dynamic values with Pillow, and exports a PNG download.
