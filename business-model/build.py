"""Gera o modelo de negócio do programa de créditos do Maná Comedoria (HTML + PDF).

Roda o render.py da skill business-model-blueprint, que já aplica a identidade
visual pyetro.cod (o documento é material do desenvolvedor, não do cliente),
e imprime o PDF A4 pelo Chrome.

Uso (na raiz do repositório):
    python business-model/build.py            # HTML + PDF
    python business-model/build.py --no-pdf   # só HTML
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = HERE / "spec.json"
HTML = HERE / "modelo.html"
PDF = HERE / "modelo.pdf"
RENDER = Path.home() / ".claude" / "skills" / "business-model-blueprint" / "scripts" / "render.py"


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
