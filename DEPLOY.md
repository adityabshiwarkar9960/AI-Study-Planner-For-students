Deploy requirements

- Python runtime: use Python 3.11.x (example: `python-3.11.9` in `runtime.txt`).
- Build command: use `pip install --prefer-binary -r requirements.txt` so pip prefers wheels over source builds (see `render.yaml`).
- Pin packages with compiled extensions to known wheel-supporting versions:
  - `numpy==1.26.4`
  - `pandas==2.2.3`

Troubleshooting

- If Render still compiles `pandas` from source, check the Render build log for the Python version and ABI (e.g., `cpython-314` indicates Python 3.14). Ensure the service's runtime matches `runtime.txt`.
- If no matching wheel exists for the platform/ABI, try using older/newer pinned versions that have wheels for your target platform, or switch to a build image that matches wheel availability.

If you want, I can also append a short pointer to this file in `README.md`. Paste the Render build log here and I'll analyze it if builds still fail.
