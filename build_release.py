#!/usr/bin/env python3
"""
Pegasus Galaxy MCP Suite — Release Packager
Converts documentation to styled HTML and high-definition PDF,
then packages pegasus-mcp-suite.zip replacing raw .md files with readable formats.
"""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from markdown_it import MarkdownIt

BASE_DIR = Path(r"c:\Users\D\Peg-MCP")
DIST_DIR = BASE_DIR / "dist" / "pegasus-mcp-suite"
ZIP_PATH = BASE_DIR / "pegasus-mcp-suite.zip"

BROWSER_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
]

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  --text-main: #1e293b;
  --text-muted: #64748b;
  --primary: #0284c7;
  --bg-code: #f1f5f9;
  --border: #e2e8f0;
}

@page {
  size: A4;
  margin: 18mm 16mm 18mm 16mm;
}

@media print {
  body {
    padding: 0 !important;
    background: #ffffff !important;
    color: #000000 !important;
  }
  .doc-container {
    box-shadow: none !important;
    border: none !important;
    padding: 0 !important;
    max-width: 100% !important;
  }
  .no-print { display: none !important; }
  a { text-decoration: none !important; color: #0369a1 !important; }
  pre { page-break-inside: avoid; }
  h1, h2, h3 { break-after: avoid; page-break-after: avoid; }
  table { page-break-inside: auto; }
  tr { page-break-inside: avoid; page-break-after: auto; }
  thead { display: table-header-group; }
}

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  line-height: 1.6;
  color: var(--text-main);
  background: #f8fafc;
  margin: 0;
  padding: 2rem 1rem;
}

.doc-container {
  max-width: 900px;
  margin: 0 auto;
  background: #ffffff;
  padding: 2.5rem 3rem;
  border-radius: 12px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
  border: 1px solid var(--border);
}

.doc-badge-bar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: #0284c7;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.75rem;
}

h1 {
  font-size: 2rem;
  font-weight: 800;
  color: #0f172a;
  border-bottom: 2px solid #0284c7;
  padding-bottom: 0.6rem;
  margin-top: 0;
}

h2 {
  font-size: 1.35rem;
  font-weight: 700;
  color: #0f172a;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.35rem;
  margin-top: 2rem;
}

h3 {
  font-size: 1.1rem;
  font-weight: 600;
  color: #1e293b;
  margin-top: 1.35rem;
}

p, li {
  font-size: 0.94rem;
  color: #334155;
}

code {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.88em;
  background: var(--bg-code);
  padding: 0.15em 0.35em;
  border-radius: 4px;
  border: 1px solid #e2e8f0;
  color: #0f766e;
}

pre {
  background: #0f172a;
  color: #f8fafc;
  padding: 0.85rem 1.1rem;
  border-radius: 8px;
  overflow-x: auto;
  border: 1px solid #1e293b;
}

pre code {
  background: transparent;
  padding: 0;
  border: none;
  color: #38bdf8;
  font-size: 0.85rem;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin: 1.25rem 0;
  font-size: 0.85rem;
}

th, td {
  padding: 0.55rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

th {
  background: #f1f5f9;
  font-weight: 600;
  color: #0f172a;
  border-top: 1px solid var(--border);
}

tr:nth-child(even) td {
  background: #f8fafc;
}

blockquote {
  border-left: 4px solid #0284c7;
  padding: 0.5rem 0.85rem;
  margin: 1rem 0;
  background: #f0f9ff;
  border-radius: 0 6px 6px 0;
  color: #0369a1;
}

blockquote p {
  margin: 0;
  font-weight: 500;
}

hr {
  border: none;
  border-top: 1px solid #cbd5e1;
  margin: 1.75rem 0;
}

a {
  color: #0284c7;
  text-decoration: underline;
}

img {
  max-width: 100%;
  vertical-align: middle;
}
"""


def find_browser() -> str:
    for p in BROWSER_PATHS:
        if Path(p).exists():
            return p
    return ""


def build_docs():
    print("--- 1. Generating Formatted HTML & PDF Docs ---")
    md = MarkdownIt("commonmark", {"html": True, "breaks": False}).enable("table")
    browser = find_browser()
    if not browser:
        print("Warning: No Chrome or Edge browser found for PDF printing. HTML will still be generated.")

    for doc_name in ["README", "INSTRUCTIONS"]:
        md_file = BASE_DIR / f"{doc_name}.md"
        html_file = BASE_DIR / f"{doc_name}.html"
        pdf_file = BASE_DIR / f"{doc_name}.pdf"

        if not md_file.exists():
            continue

        text = md_file.read_text(encoding="utf-8")
        body_html = md.render(text)

        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Pegasus Galaxy MCP Suite v0.2 — {doc_name}</title>
  <style>{CSS}</style>
</head>
<body>
  <div class="doc-container">
    <div class="doc-badge-bar">
      <span>🌌 Pegasus Galaxy MCP Suite v0.2</span>
      <span>•</span>
      <span>{doc_name} Documentation</span>
    </div>
    {body_html}
  </div>
</body>
</html>"""
        html_file.write_text(full_html, encoding="utf-8")
        print(f"Created HTML: {html_file.name} ({html_file.stat().st_size:,} bytes)")

        if browser:
            cmd = [
                browser,
                "--headless",
                "--disable-gpu",
                "--run-all-compositor-stages-before-draw",
                f"--print-to-pdf={str(pdf_file)}",
                "--no-pdf-header-footer",
                str(html_file),
            ]
            try:
                subprocess.run(cmd, capture_output=True, timeout=45)
                if pdf_file.exists():
                    print(f"Created PDF:  {pdf_file.name} ({pdf_file.stat().st_size:,} bytes)")
            except Exception as e:
                print(f"Failed to generate {pdf_file.name}: {e}")


def build_zip():
    print("\n--- 2. Packaging pegasus-mcp-suite.zip ---")
    
    # Files to include in zip (NOTE: .md files are replaced by .pdf and .html)
    files_to_include = [
        "peg_gui.py",
        "peg_bot.py",
        "peg_tool.py",
        "peg_client.py",
        "bot_config.json",
        "bot_strategy.py",
        "requirements.txt",
        "INSTRUCTIONS.pdf",
        "README.pdf",
        "INSTRUCTIONS.html",
        "README.html",
        ".env.example",
        ".gitignore",
        "deploy_vps.sh",
        "Dockerfile",
        "pegasus-bot.service",
        "pegasus-gui.service",
    ]

    dirs_to_include = [
        "config_profiles",
        "custom_strategies",
    ]

    # Update dist/ directory
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    for fname in files_to_include:
        src = BASE_DIR / fname
        if src.exists():
            shutil.copy2(src, DIST_DIR / fname)

    for dname in dirs_to_include:
        src = BASE_DIR / dname
        if src.exists():
            shutil.copytree(src, DIST_DIR / dname)

    # Build zip file
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        for fname in files_to_include:
            file_path = BASE_DIR / fname
            if file_path.exists():
                z.write(file_path, arcname=fname)
                print(f"Added: {fname} ({file_path.stat().st_size:,} bytes)")
            else:
                print(f"Notice: {fname} not found, skipping.")

        for dname in dirs_to_include:
            dir_path = BASE_DIR / dname
            if dir_path.exists():
                for item in sorted(dir_path.rglob("*")):
                    if item.is_file() and not item.name.endswith(".pyc") and "__pycache__" not in str(item):
                        arc = str(item.relative_to(BASE_DIR)).replace("\\\\", "/")
                        z.write(item, arcname=arc)
                        print(f"Added: {arc} ({item.stat().st_size:,} bytes)")

    zip_size = ZIP_PATH.stat().st_size
    print("=" * 50)
    print(f"SUCCESS: Rebuilt {ZIP_PATH.name}")
    print(f"Total archive size: {zip_size:,} bytes ({zip_size / 1024:.1f} KB)")
    print("Documentation in zip: INSTRUCTIONS.pdf, README.pdf, INSTRUCTIONS.html, README.html")
    print("Raw .md files kept in repository root.")


if __name__ == "__main__":
    build_docs()
    build_zip()
