"""Gera o modelo de negócio com a identidade visual do Manaçaí.

Roda o render.py da skill business-model-blueprint e troca a paleta padrão
pela paleta da marca, adicionando a logo na primeira página.

Uso (na raiz do repositório):
    python business-model/build.py            # HTML + PDF
    python business-model/build.py --no-pdf   # só HTML
"""
import base64
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = HERE / "spec.json"
HTML = HERE / "modelo.html"
PDF = HERE / "modelo.pdf"
LOGO = HERE.parent / "frontend" / "logo.jpg"
RENDER = Path.home() / ".claude" / "skills" / "business-model-blueprint" / "scripts" / "render.py"

# Default renderer color -> Manaçaí color. Semantic tones are kept
# (green = money, red = risk) but shifted to shades that read well on white.
PALETTE = {
    "#1d2b4a": "#3d1441",  # navy   -> roxo escuro
    "#e8ebf2": "#f1e8f2",
    "#2a4fa8": "#5b1e60",  # blue   -> roxo da marca
    "#eaf0fb": "#f6eef7",
    "#d3e0f6": "#e9d5eb",
    "#1f7a78": "#5e8f1f",  # teal   -> verde folha (escurecido para contraste)
    "#e4f3f2": "#eef6e2",
    "#c4601a": "#c98a00",  # orange -> amarelo da marca (escurecido para texto)
    "#fdf0e3": "#fff4d6",
    "#5b3d9a": "#8a3f8f",  # purple -> roxo médio
    "#f0ebf8": "#f5ebf6",
    "#2e7d4f": "#4f7f17",  # green  -> verde dinheiro
    "#e6f4ec": "#ecf5df",
    "#d9a521": "#fbb91c",  # amber (manual steps) -> amarelo da marca
    "#e9ecf1": "#efe8f0",  # page background
}

EXTRA_CSS = """
<style>
.page{border-top:6px solid #5b1e60}
.brand-logo{position:absolute;top:11mm;right:12mm;width:22mm;height:22mm;border-radius:4mm;object-fit:cover}
</style>
"""


def find_chrome():
    candidates = [
        shutil.which("chrome"), shutil.which("google-chrome"), shutil.which("chromium"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    return next((c for c in candidates if c and Path(c).exists()), None)


def main():
    if not RENDER.exists():
        sys.exit(f"render.py não encontrado em {RENDER}")

    result = subprocess.run([sys.executable, str(RENDER), str(SPEC), "-o", str(HTML)],
                            capture_output=True, text=True, encoding="utf-8")
    print(result.stdout.strip())
    if result.returncode != 0:
        sys.exit(result.stderr)

    html = HTML.read_text(encoding="utf-8")
    for old, new in PALETTE.items():
        html = html.replace(old, new).replace(old.upper(), new)

    html = html.replace("</head>", EXTRA_CSS + "</head>", 1)
    if LOGO.exists():
        logo_b64 = base64.b64encode(LOGO.read_bytes()).decode()
        img = f'<img class="brand-logo" alt="Manaçaí" src="data:image/jpeg;base64,{logo_b64}">'
        html = html.replace('<section class="page">', '<section class="page">' + img, 1)
    else:
        print(f"aviso: logo não encontrada em {LOGO}")

    HTML.write_text(html, encoding="utf-8")
    print(f"HTML com identidade Manaçaí: {HTML}")

    if "--no-pdf" in sys.argv:
        return
    chrome = find_chrome()
    if not chrome:
        print("Chrome não encontrado: imprima o HTML como PDF (A4, sem margens, gráficos de fundo).")
        return
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--disable-extensions",
                    "--no-pdf-header-footer", f"--print-to-pdf={PDF}", HTML.as_uri()],
                   capture_output=True)
    print(f"PDF: {PDF}" if PDF.exists() else "falha ao gerar o PDF")


if __name__ == "__main__":
    main()
