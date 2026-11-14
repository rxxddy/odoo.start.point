#!/usr/bin/env python3
"""Build the handbook as a static site (MkDocs Material) for GitHub Pages.

Usage: python .github/pages/build.py <repo_root> <output_dir>

The book is written for GitBook. This script copies the chapters to a scratch
directory, rewrites the GitBook-only syntax ({% hint %} blocks, <details>) into
what MkDocs understands, builds the navigation from SUMMARY.md and runs MkDocs.
The Markdown files in the repository are not modified.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SITE_URL = "https://rxxddy.github.io/odoo.start.point/"
REPO_URL = "https://github.com/rxxddy/odoo.start.point"
HINT_OPEN = re.compile(r'^(\s*)\{%\s*hint\s+style="(\w+)"\s*%\}\s*$')
HINT_CLOSE = re.compile(r'^\s*\{%\s*endhint\s*%\}\s*$')
HINT_TYPES = {"info": "info", "warning": "warning", "danger": "danger", "success": "success"}


PART_LINK = re.compile(r"\]\(((?:\.\./)?)(\d\d-[a-z0-9-]+)/\)")


def convert(text: str, first_pages=None) -> str:
    if first_pages:
        # links to a part folder ("../06-orm/") become links to its first chapter
        text = PART_LINK.sub(
            lambda m: f"]({m.group(1)}{first_pages[m.group(2)]})" if m.group(2) in first_pages else m.group(0),
            text,
        )
    out, lines = [], text.split("\n")
    i = 0
    in_fence = False
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        m = None if in_fence else HINT_OPEN.match(line)
        if m:
            indent, style = m.group(1), HINT_TYPES.get(m.group(2), "info")
            body = []
            i += 1
            while i < len(lines) and not HINT_CLOSE.match(lines[i]):
                body.append(lines[i])
                i += 1
            while body and not body[0].strip():
                body.pop(0)
            while body and not body[-1].strip():
                body.pop()
            out.append(f'{indent}!!! {style} ""')
            for b in body:
                out.append(f"{indent}    {b}" if b.strip() else "")
            out.append("")
        else:
            out.append(line)
        i += 1
    result = "\n".join(out)
    result = re.sub(r"<details>", '<details markdown="1">', result)
    return result


def parse_summary(summary: str):
    nav, group = [], None
    for raw in summary.split("\n"):
        line = raw.rstrip()
        m = re.match(r"^## (.+)$", line)
        if m:
            group = (m.group(1).strip(), [])
            nav.append(group)
            continue
        m = re.match(r"^\s*\* \[(.+?)\]\((.+?)\)\s*$", line)
        if m:
            title, path = m.group(1), m.group(2)
            if group is None:
                nav.append((title, path))
            else:
                group[1].append((title, path))
    return nav


def yaml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def nav_yaml(nav, mapping) -> str:
    lines = ["nav:"]
    for item in nav:
        if isinstance(item[1], str):
            lines.append(f"  - {yaml_str(item[0])}: {mapping(item[1])}")
        else:
            lines.append(f"  - {yaml_str(item[0])}:")
            for title, path in item[1]:
                lines.append(f"      - {yaml_str(title)}: {mapping(path)}")
    return "\n".join(lines)


def main(root: Path, out_dir: Path) -> None:
    pages_dir = root / ".github" / "pages"
    summary = (root / "SUMMARY.md").read_text(encoding="utf-8")
    nav = parse_summary(summary)
    work = Path(tempfile.mkdtemp(prefix="handbook-pages-"))
    docs = work / "docs"
    docs.mkdir()

    first_pages = {}
    for item in nav:
        if not isinstance(item[1], str) and item[1]:
            path = item[1][0][1]
            first_pages[path.split("/")[0]] = path
    sources = sorted(p for p in root.glob("[0-9][0-9]-*/*.md"))
    for src in sources:
        dest = docs / src.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(convert(src.read_text(encoding="utf-8").replace("\r\n", "\n"), first_pages), encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    (docs / "index.md").write_text(convert(readme, first_pages), encoding="utf-8")
    (docs / "stylesheets").mkdir()
    shutil.copy(pages_dir / "extra.css", docs / "stylesheets" / "extra.css")

    def mapping(path: str) -> str:
        return "index.md" if path == "README.md" else path

    config = f"""site_name: Odoo Developer Handbook
site_description: Handbook for Odoo module developers, Odoo 16 to 20
site_url: {SITE_URL}
repo_url: {REPO_URL}
repo_name: rxxddy/odoo.start.point
edit_uri: edit/main/
docs_dir: docs
use_directory_urls: true
theme:
  name: material
  language: en
  font: false
  palette:
    - media: "(prefers-color-scheme: light)"
      scheme: default
      primary: custom
      accent: custom
      toggle:
        icon: material/weather-night
        name: Switch to dark mode
    - media: "(prefers-color-scheme: dark)"
      scheme: slate
      primary: custom
      accent: custom
      toggle:
        icon: material/weather-sunny
        name: Switch to light mode
  features:
    - navigation.sections
    - navigation.top
    - navigation.footer
    - navigation.instant
    - search.suggest
    - search.highlight
    - toc.follow
    - content.code.copy
    - content.action.edit
extra_css:
  - stylesheets/extra.css
markdown_extensions:
  - admonition
  - attr_list
  - md_in_html
  - tables
  - toc:
      permalink: false
  - pymdownx.details
  - pymdownx.superfences
  - pymdownx.highlight:
      anchor_linenums: false
  - pymdownx.inlinehilite
plugins:
  - search
{nav_yaml(nav, mapping)}
"""
    (work / "mkdocs.yml").write_text(config, encoding="utf-8")
    out_dir = out_dir.resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "-f", str(work / "mkdocs.yml"), "-d", str(out_dir)],
        check=True,
    )
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
