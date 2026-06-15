---
name: md-to-pdf
description: Convert a Markdown file to a clean, business-ready PDF using md-to-pdf (via npx). Accepts a path to a .md file and outputs a .pdf in the same directory.
allowed-tools: Bash
arguments: [file]
---

Convert the Markdown file at `$ARGUMENTS` to a PDF.

Rules:
- The input must be a `.md` file. If no argument is provided, ask the user for the file path.
- Output the PDF to the same directory as the input file, with the same base name and a `.pdf` extension.
- Use the exact `npx --yes md-to-pdf` command below — do not substitute another tool.
- After generating, report the output path and file size.
- If the command fails, show the error output and suggest the user check that Node.js ≥ 14 is installed.

Run this command (replace `<input>` with the resolved absolute path to the .md file):

```
npx --yes md-to-pdf <input> \
  --stylesheet "https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.5.1/github-markdown.min.css" \
  --css "body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; max-width: 900px; margin: 40px auto; padding: 0 40px; } h1 { font-size: 22px; border-bottom: 2px solid #333; padding-bottom: 8px; } h2 { font-size: 17px; border-bottom: 1px solid #ccc; padding-bottom: 4px; margin-top: 28px; } table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 12px; } th { background: #f0f0f0; padding: 6px 10px; border: 1px solid #ccc; text-align: left; } td { padding: 5px 10px; border: 1px solid #ddd; } pre { background: #f6f8fa; padding: 12px; border-radius: 4px; font-size: 11px; overflow-x: auto; } code { font-size: 11px; } @media print { pre { white-space: pre-wrap; word-break: break-word; } }" \
  --pdf-options '{"format":"A4","margin":{"top":"25mm","bottom":"25mm","left":"20mm","right":"20mm"},"printBackground":true}'
```