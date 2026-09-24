import os
import argparse
import subprocess
import re
import sys
import shutil
import glob
import importlib
import importlib.util
import platform

# Loaded after the dependency check so the script can repair a missing
# nbformat installation instead of crashing immediately on startup.
nbf = None

#Command to make a new homework with the first number 
#being the homework number and second number being number of problems.


# Command to Generate the files         python genhw.py gen -hw 1 -n 2

# Command to Generate the pdfs          python genhw.py pdf -hw 2



# --- CONFIGURATION DEFAULTS ---
FIRST_NAME = "Sean"
LAST_NAME = "Merrill"
SUBFOLDER = "Homework Problems"
PDF_MARGIN = "0.5in"
REMOVE_NOTEBOOK_TITLE_CELL = True
REMOVE_EXECUTION_PROMPTS = True
UNNUMBER_MARKDOWN_HEADINGS = True
# ------------------------------


# Python packages used by this script and by the starter notebook it creates.
PYTHON_DEPENDENCIES = {
    "nbformat": "nbformat",
    "nbconvert": "nbconvert",
    "numpy": "numpy",
    "pandas": "pandas",
    "matplotlib": "matplotlib",
}


def _command_works(command, version_args=("--version",)):
    """Return True only when a command exists and can actually run."""
    executable = shutil.which(command)
    if not executable:
        return False
    try:
        result = subprocess.run(
            [executable, *version_args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
        return result.returncode == 0
    except Exception:
        return False


def _python_module_works(module_name):
    """Check that a Python dependency is importable, not merely installed."""
    try:
        if importlib.util.find_spec(module_name) is None:
            return False
        importlib.import_module(module_name)
        return True
    except Exception:
        return False


def _ask_yes_no(prompt, default=True):
    """Small interactive yes/no helper; Enter accepts the default."""
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        try:
            answer = input(prompt + suffix).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please enter y or n.")


def _install_python_dependencies(packages):
    """Install/reinstall Python packages into the interpreter running this script."""
    if not packages:
        return True
    print("\n[*] Installing Python dependencies...")
    cmd = [sys.executable, "-m", "pip", "install", *packages]
    try:
        result = subprocess.run(cmd)
        return result.returncode == 0
    except Exception as e:
        print(f"[!] Could not run pip: {e}")
        return False


def _system_install_command(missing_commands):
    """Return a platform/package-manager install command for Pandoc/XeLaTeX."""
    system = platform.system().lower()
    need_pandoc = "pandoc" in missing_commands
    need_xelatex = "xelatex" in missing_commands

    if system == "windows":
        if shutil.which("winget"):
            commands = []
            if need_pandoc:
                commands.append([
                    "winget", "install", "--id", "JohnMacFarlane.Pandoc", "-e",
                    "--accept-package-agreements", "--accept-source-agreements",
                ])
            if need_xelatex:
                commands.append([
                    "winget", "install", "--id", "MiKTeX.MiKTeX", "-e",
                    "--accept-package-agreements", "--accept-source-agreements",
                ])
            return commands, "winget"
        if shutil.which("choco"):
            packages = []
            if need_pandoc:
                packages.append("pandoc")
            if need_xelatex:
                packages.append("miktex")
            return [["choco", "install", "-y", *packages]], "Chocolatey"

    elif system == "darwin":
        if shutil.which("brew"):
            commands = []
            if need_pandoc:
                commands.append(["brew", "install", "pandoc"])
            if need_xelatex:
                commands.append(["brew", "install", "--cask", "mactex-no-gui"])
            return commands, "Homebrew"

    elif system == "linux":
        if shutil.which("apt-get"):
            packages = []
            if need_pandoc:
                packages.append("pandoc")
            if need_xelatex:
                packages.extend(["texlive-xetex", "texlive-fonts-recommended", "texlive-plain-generic"])
            prefix = ["sudo"] if shutil.which("sudo") else []
            return [
                prefix + ["apt-get", "update"],
                prefix + ["apt-get", "install", "-y", *packages],
            ], "apt"
        if shutil.which("dnf"):
            packages = []
            if need_pandoc:
                packages.append("pandoc")
            if need_xelatex:
                packages.extend(["texlive-xetex", "texlive-collection-fontsrecommended"])
            prefix = ["sudo"] if shutil.which("sudo") else []
            return [prefix + ["dnf", "install", "-y", *packages]], "dnf"

    return None, None


def _install_system_dependencies(missing_commands):
    """Interactively install Pandoc/XeLaTeX using an available package manager."""
    commands, manager = _system_install_command(missing_commands)
    if not commands:
        print("\n[!] I could not find a supported system package manager automatically.")
        print("    Please install the following and then rerun the command:")
        if "pandoc" in missing_commands:
            print("      - Pandoc: https://pandoc.org/installing.html")
        if "xelatex" in missing_commands:
            print("      - XeLaTeX via MiKTeX, TeX Live, or MacTeX")
        return False

    print(f"\n[*] {manager} can install the missing system dependencies.")
    if not _ask_yes_no(f"Run the {manager} installer now?", default=True):
        return False

    for cmd in commands:
        print("    > " + " ".join(cmd))
        try:
            result = subprocess.run(cmd)
        except Exception as e:
            print(f"[!] Installer failed to start: {e}")
            return False
        if result.returncode != 0:
            print(f"[!] Installer returned exit code {result.returncode}.")
            return False
    return True


def ensure_dependencies(require_pdf=False):
    """Check dependencies and offer to install anything missing or broken.

    The check is intentionally interactive only when something is wrong. A normal
    working setup starts exactly as before without prompting.
    """
    global nbf

    missing_python = [
        package for module, package in PYTHON_DEPENDENCIES.items()
        if not _python_module_works(module)
    ]

    missing_system = []
    if require_pdf:
        if not _command_works("pandoc"):
            missing_system.append("pandoc")
        if not _command_works("xelatex"):
            missing_system.append("xelatex")

    if missing_python or missing_system:
        print("\n[!] Missing or non-working dependencies detected:")
        if missing_python:
            print("    Python packages: " + ", ".join(missing_python))
        if missing_system:
            print("    System tools: " + ", ".join(missing_system))

        if not _ask_yes_no("Would you like to install/repair them now?", default=True):
            print("[!] Dependency setup cancelled.")
            return False

        if missing_python and not _install_python_dependencies(missing_python):
            print("[!] One or more Python dependencies could not be installed.")
            return False

        if missing_system and not _install_system_dependencies(missing_system):
            return False

        # Invalidate import caches after pip/system installers and verify again.
        importlib.invalidate_caches()
        still_missing_python = [
            package for module, package in PYTHON_DEPENDENCIES.items()
            if not _python_module_works(module)
        ]
        still_missing_system = []
        if require_pdf:
            if not _command_works("pandoc"):
                still_missing_system.append("pandoc")
            if not _command_works("xelatex"):
                still_missing_system.append("xelatex")

        if still_missing_python or still_missing_system:
            print("\n[!] Some dependencies are still not available:")
            if still_missing_python:
                print("    Python packages: " + ", ".join(still_missing_python))
            if still_missing_system:
                print("    System tools: " + ", ".join(still_missing_system))
                if platform.system().lower() == "windows":
                    print("    If these were just installed, restart the terminal so PATH updates, then rerun the command.")
            return False

    # Load nbformat only after the dependency check has had a chance to repair it.
    if nbf is None:
        nbf = importlib.import_module("nbformat")
    return True


def cleanup_temp_artifacts(temp_base):
    """Remove every temporary file/folder created for one notebook conversion."""
    # nbconvert may create __tmp_name.tex/.pdf/.aux/.log plus a
    # __tmp_name_files directory containing extracted figures.
    for path in glob.glob(temp_base + "*"):
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"    [!] Could not remove temporary artifact '{path}': {e}")

def get_base_path():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if SUBFOLDER.strip():
        path = os.path.join(script_dir, SUBFOLDER.strip())
        os.makedirs(path, exist_ok=True)
        return path
    return script_dir

def get_pandoc_path():
    """Finds the Pandoc executable used by nbconvert."""
    try:
        from nbconvert.utils.pandoc import find_pandoc
        return find_pandoc()
    except Exception:
        import shutil
        return shutil.which("pandoc") or "pandoc"

def sanitize_latex(text):
    """Escape LaTeX special characters in plain text using a single pass."""
    if not text:
        return ""
    replacements = {
        '\\': r'\textbackslash{}',
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
    }
    return re.sub(r'[\\&%$#_{}~^]', lambda m: replacements[m.group(0)], text)


def sanitize_latex_preserving_math(text):
    """Escape title text while preserving inline LaTeX math such as $\\pi$."""
    if not text:
        return ""
    # Keep $...$ and \\(...\\) math untouched; escape only surrounding text.
    parts = re.split(r'(\$[^$]*\$|\\\([^)]*\\\))', text)
    out = []
    for part in parts:
        if (part.startswith('$') and part.endswith('$')) or (part.startswith(r'\(') and part.endswith(r'\)')):
            out.append(part)
        else:
            out.append(sanitize_latex(part))
    return ''.join(out)



def _html_inline_to_markdown(text):
    """Translate a conservative set of inline HTML tags to Markdown/raw TeX."""
    if not text:
        return text
    # These preserve formatting without changing surrounding text/layout.
    text = re.sub(r'<\s*(?:b|strong)\s*>', '**', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/\s*(?:b|strong)\s*>', '**', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*(?:i|em)\s*>', '*', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*/\s*(?:i|em)\s*>', '*', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*u\s*>([\s\S]*?)<\s*/\s*u\s*>', r'\\underline{\1}', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*sup\s*>([\s\S]*?)<\s*/\s*sup\s*>', r'\\textsuperscript{\1}', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*sub\s*>([\s\S]*?)<\s*/\s*sub\s*>', r'\\textsubscript{\1}', text, flags=re.IGNORECASE)
    text = re.sub(r'<\s*br\s*/?\s*>', '  \\n', text, flags=re.IGNORECASE)
    return text


def _markdown_fragment_to_latex(text):
    """Convert a Markdown fragment to LaTeX for use inside an alignment block."""
    pandoc_bin = get_pandoc_path()
    if not pandoc_bin:
        return text
    try:
        cleaned = _html_inline_to_markdown(text)
        res = subprocess.run(
            [pandoc_bin, '-f', 'markdown+raw_tex', '-t', 'latex'],
            input=cleaned,
            capture_output=True,
            text=True,
            encoding='utf-8',
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return text


def preserve_markdown_html_formatting(text):
    """Preserve common HTML presentation tags when exporting Markdown to PDF.

    nbconvert/Pandoc normally discards HTML-only alignment such as <center>
    and CSS text-align. Only cells that actually contain these HTML tags are
    touched; ordinary notebook Markdown is left byte-for-byte unchanged.
    """
    if not text or '<' not in text:
        return text

    def latex_raw_block(env, body):
        body_latex = _markdown_fragment_to_latex(body)
        return (
            '\n```{=latex}\n'
            f'\\begin{{{env}}}\n'
            f'{body_latex}\n'
            f'\\end{{{env}}}\n'
            '```\n'
        )

    # Legacy <center>...</center>.
    text = re.sub(
        r'<\s*center\s*>([\s\S]*?)<\s*/\s*center\s*>',
        lambda m: latex_raw_block('center', m.group(1)),
        text,
        flags=re.IGNORECASE,
    )

    # <div>/<p> with align="..." or style="text-align: ...".
    pair_pattern = re.compile(
        r'<(?P<tag>div|p)\b(?P<attrs>[^>]*)>(?P<body>[\s\S]*?)</\s*(?P=tag)\s*>',
        flags=re.IGNORECASE,
    )

    def replace_aligned_pair(match):
        attrs = match.group('attrs') or ''
        align_match = re.search(
            r'\balign\s*=\s*["\']?\s*(center|left|right)\s*["\']?',
            attrs,
            flags=re.IGNORECASE,
        )
        if not align_match:
            align_match = re.search(
                r'text-align\s*:\s*(center|left|right)',
                attrs,
                flags=re.IGNORECASE,
            )
        if not align_match:
            return match.group(0)

        align = align_match.group(1).lower()
        env = {'center': 'center', 'left': 'flushleft', 'right': 'flushright'}[align]
        return latex_raw_block(env, match.group('body'))

    text = pair_pattern.sub(replace_aligned_pair, text)

    # Preserve common inline HTML formatting outside alignment blocks too.
    text = _html_inline_to_markdown(text)

    # Horizontal rules are already understood by Markdown; convert HTML <hr>.
    text = re.sub(r'<\s*hr\s*/?\s*>', '\n\n---\n\n', text, flags=re.IGNORECASE)
    return text

def scan_notebook_for_problems(nb_path):
    """Pre-flight scan for layout risks that Pandoc cannot always fix automatically."""
    try:
        with open(nb_path, 'r', encoding='utf-8') as f:
            nb = nbf.read(f, as_version=4)
    except Exception as e:
        print(f"[!] Could not read notebook for scanning: {e}")
        return

    warnings = []
    for i, cell in enumerate(nb.cells):
        if cell.cell_type != 'markdown':
            continue
        # Markdown tables with many columns are the main predictable PDF layout risk.
        for line in cell.source.splitlines():
            if line.strip().startswith('|') and line.count('|') > 8:
                warnings.append(f"Cell {i}: Wide Markdown table detected; it may need wrapping.")

    if warnings:
        print(f"\n[!] PRE-FLIGHT WARNINGS for {os.path.basename(nb_path)}:")
        for w in warnings:
            print(f"    - {w}")
        print("-" * 40)

def extract_title_and_author(nb, filename, override_title=None):
    """
    Safely extracts Title and Author with a multi-level fallback cascade.
    Never returns None. Never leaves raw __tmp_ filenames.
    """
    if override_title:
        return override_title, f"{FIRST_NAME} {LAST_NAME}"

    title = None
    author = None

    # LEVEL 1: Try to extract from the first markdown cell
    for cell in nb.cells:
        if cell.cell_type == 'markdown':
            lines = [l.strip() for l in cell.source.splitlines() if l.strip()]
            for line in lines:
                if line.startswith('# ') and not title:
                    raw = line.lstrip('# ').strip()
                    title = raw.replace('*', '')
                elif line.startswith('**') and line.endswith('**') and not author:
                    author = line.strip('*').strip()
            if title:
                break

    # LEVEL 2: Try to parse structured filename (e.g., Jacob_Turley_HW2_Problem01)
    if not title or not author:
        base = os.path.splitext(os.path.basename(filename))[0]
        base = re.sub(r'^_+tmp_+', '', base, flags=re.IGNORECASE)
        parts = base.split('_')
        
        if len(parts) >= 4 and 'HW' in parts[2]:
            author = author or f"{parts[0]} {parts[1]}"
            hw = parts[2].replace('HW', 'Homework ')
            prob_num = re.sub(r'(?i)^Problem0*', '', parts[3])
            prob = f"Problem {prob_num}"
            title = title or f"{hw}: {prob}"
        else:
            # LEVEL 3: Clean generic filename (e.g., lab_experiment_final -> Lab Experiment Final)
            clean_base = base.replace('_', ' ').replace('-', ' ').strip().title()
            title = title or (clean_base if clean_base else "Homework Submission")
            author = author or f"{FIRST_NAME} {LAST_NAME}"

    # LEVEL 4: Absolute safe default
    final_title = title if title else "Homework Submission"
    final_author = author if author else f"{FIRST_NAME} {LAST_NAME}"

    return final_title, final_author

def prepare_notebook_for_pdf(nb):
    """Clean a temporary notebook copy for PDF export without altering the original."""
    if REMOVE_NOTEBOOK_TITLE_CELL and nb.cells:
        first = nb.cells[0]
        if first.cell_type == 'markdown':
            lines = [line.strip() for line in first.source.splitlines() if line.strip()]
            has_title = any(line.startswith('# ') for line in lines)
            has_author = any(line.startswith('**') and line.endswith('**') for line in lines)
            if has_title and has_author:
                # The same title/author are already inserted with LaTeX's \\maketitle.
                nb.cells.pop(0)

    # Preserve presentation-oriented HTML in Markdown cells for PDF export.
    # This only modifies the temporary export copy, never the original notebook.
    for cell in nb.cells:
        if cell.cell_type == 'markdown':
            cell.source = preserve_markdown_html_formatting(cell.source)

    # Remove useless object reprs like <matplotlib.legend.Legend at 0x...> while
    # retaining the actual plot image output.
    noisy_repr = re.compile(r'^<matplotlib\.[^>]+ at 0x[0-9A-Fa-f]+>$')
    for cell in nb.cells:
        if cell.cell_type != 'code':
            continue
        cleaned = []
        for output in cell.get('outputs', []):
            data = output.get('data', {})
            text_plain = data.get('text/plain')
            if isinstance(text_plain, list):
                text_plain = ''.join(text_plain)
            if isinstance(text_plain, str) and noisy_repr.match(text_plain.strip()):
                # If this output contains an image too, keep it but remove the text repr.
                if any(k.startswith('image/') for k in data):
                    data.pop('text/plain', None)
                    cleaned.append(output)
                # Otherwise drop only this noisy execute/display result.
                continue
            cleaned.append(output)
        cell['outputs'] = cleaned
    return nb


def convert_html_tables_to_latex(nb):
    """Converts HTML tables (like Pandas df.style) to LaTeX via Pandoc."""
    pandoc_bin = get_pandoc_path()
    if not pandoc_bin:
        return

    for cell in nb.cells:
        if cell.cell_type != 'code':
            continue
        for output in cell.get('outputs', []):
            data = output.get('data', {})
            if 'text/html' in data:
                raw_html = data['text/html']
                html_str = "".join(raw_html) if isinstance(raw_html, list) else str(raw_html)

                tables = re.findall(r'<table[\s\S]*?</table>', html_str, re.IGNORECASE)
                if not tables:
                    continue

                combined_html = "\n\n".join(tables)
                try:
                    res = subprocess.run(
                        [pandoc_bin, "-f", "html", "-t", "latex"],
                        input=combined_html,
                        capture_output=True,
                        text=True,
                        encoding='utf-8'
                    )
                    if res.returncode == 0 and res.stdout.strip():
                        latex = res.stdout

                        # Pandas Styler puts captions in the table HTML, but the
                        # nbconvert LaTeX template globally suppresses normal
                        # LaTeX captions. Render the HTML caption ourselves so
                        # it is visible and its basic CSS placement/alignment is
                        # respected without changing any other PDF formatting.
                        caption_match = re.search(
                            r'<caption[^>]*>([\s\S]*?)</caption>',
                            html_str,
                            re.IGNORECASE,
                        )
                        if caption_match:
                            # Pandoc has already converted the caption text to
                            # LaTeX for us; reuse that converted text so symbols
                            # and escaping stay consistent with the table.
                            latex_caption = re.search(
                                r'\\caption\{([\s\S]*?)\}\\label\{[^}]*\}\\tabularnewline',
                                latex,
                            )
                            if latex_caption:
                                caption_text = latex_caption.group(1).strip()
                                latex = latex[:latex_caption.start()] + latex[latex_caption.end():]

                                caption_side = 'bottom' if re.search(
                                    r'caption-side\s*:\s*bottom', html_str, re.IGNORECASE
                                ) else 'top'
                                centered = bool(re.search(
                                    r'text-align\s*:\s*center', html_str, re.IGNORECASE
                                ))
                                bold = bool(re.search(
                                    r'font-weight\s*:\s*(?:bold|[6-9]00)', html_str, re.IGNORECASE
                                ))

                                rendered_caption = caption_text
                                if bold:
                                    rendered_caption = rf'\textbf{{{rendered_caption}}}'
                                if centered:
                                    rendered_caption = (
                                        '\n\\begin{center}\n'
                                        + rendered_caption
                                        + '\n\\end{center}\n'
                                    )
                                else:
                                    rendered_caption = '\n' + rendered_caption + '\n'

                                if caption_side == 'bottom':
                                    latex = latex.replace(
                                        r'\end{longtable}',
                                        r'\end{longtable}' + rendered_caption,
                                        1,
                                    )
                                else:
                                    latex = rendered_caption + latex

                        data['text/latex'] = latex
                except Exception:
                    pass

def patch_latex(tex_content, title, author):
    """Clean document metadata, headings, margins, code layout, and wide tables."""
    # 1. Fix Python/nbconvert counter issue. Use a real newline, not a literal "\\n".
    if r"\newcounter{none}" not in tex_content:
        tex_content = tex_content.replace(
            r"\begin{document}",
            "\\newcounter{none}\n\\begin{document}",
            1,
        )

    # 2. Make the page geometry deterministic. nbconvert often emits a later
    #    \\geometry{...} command that otherwise overrides package options.
    if r"\usepackage{array}" not in tex_content:
        tex_content = tex_content.replace(
            r"\usepackage{geometry}",
            r"\usepackage{geometry}" + "\n" + r"\usepackage{array}",
            1,
        )
    tex_content = re.sub(
        r'\\geometry\{[^}]*\}',
        lambda _: f"\\geometry{{margin={PDF_MARGIN}}}",
        tex_content,
        count=1,
    )
    # Prevent LaTeX from vertically stretching sparse pages.
    tex_content = tex_content.replace(r"\begin{document}", r"\begin{document}" + "\n" + r"\raggedbottom", 1)

    # 3. Clean and format document title/author. Preserve inline title math.
    if ' - ' in title:
        main_t, sub_t = title.split(' - ', 1)
        esc_main = sanitize_latex_preserving_math(main_t.strip())
        esc_sub = sanitize_latex_preserving_math(sub_t.strip())
        formatted_title = f"\\textbf{{\\LARGE {esc_main}}}\\\\[0.4em]\\Large {esc_sub}"
    else:
        esc_title = sanitize_latex_preserving_math(title.strip())
        formatted_title = f"\\textbf{{\\LARGE {esc_title}}}"

    esc_author = sanitize_latex(author.strip())
    tex_content = re.sub(
        r'\\title\{[\s\S]*?\}',
        lambda _: f"\\title{{{formatted_title}}}",
        tex_content,
        count=1,
    )
    if r'\author{' in tex_content:
        tex_content = re.sub(
            r'\\author\{[\s\S]*?\}',
            lambda _: f"\\author{{{esc_author}}}",
            tex_content,
            count=1,
        )
    else:
        tex_content = tex_content.replace(r'\maketitle', f"\\author{{{esc_author}}}\n\\maketitle", 1)

    # 4. The notebook questions already contain their own problem numbers.
    #    Star LaTeX section commands to stop nbconvert from adding 1, 1.1, 1.1.1, etc.
    if UNNUMBER_MARKDOWN_HEADINGS:
        for cmd in ('section', 'subsection', 'subsubsection', 'paragraph', 'subparagraph'):
            tex_content = re.sub(rf'\\{cmd}(?!\*)\{{', rf'\\{cmd}*{{', tex_content)

    # 5. Wrap Pandas/Pandoc longtables. Pandoc column specs contain nested @{}
    #    tokens, so the old "[^}]" regex stopped at the first brace and never worked.
    table_pattern = re.compile(
        r'\\begin\{longtable\}\[\]\{([^\n]*)\}([\s\S]*?)\\end\{longtable\}'
    )

    def fit_longtable(match):
        old_spec = match.group(1)
        body = match.group(2)
        # Remove Pandoc spacing decorators before counting alignment columns.
        stripped = re.sub(r'@\{[^}]*\}', '', old_spec)
        num_cols = len(re.findall(r'(?<!\\)[lcrX]', stripped))
        if num_cols <= 0:
            return match.group(0)

        # Leave narrow tables close to normal size; wrap wider tables aggressively.
        if num_cols <= 3:
            size = r'\normalsize'
            total_fraction = 0.90
            tabcolsep = '4pt'
        elif num_cols <= 6:
            size = r'\footnotesize'
            total_fraction = 0.86
            tabcolsep = '2.5pt'
        else:
            size = r'\scriptsize'
            total_fraction = 0.82
            tabcolsep = '2pt'

        width = total_fraction / num_cols
        new_spec = ''.join(
            rf'>{{\raggedright\arraybackslash}}p{{{width:.4f}\textwidth}}'
            for _ in range(num_cols)
        )
        return (
            "\\begingroup\n"
            f"{size}\n"
            f"\\setlength{{\\tabcolsep}}{{{tabcolsep}}}\n"
            "\\renewcommand{\\arraystretch}{1.05}\n"
            f"\\begin{{longtable}}[]{{{new_spec}}}{body}\\end{{longtable}}\n"
            "\\endgroup"
        )

    tex_content = table_pattern.sub(fit_longtable, tex_content)
    return tex_content

def process_single_file(ipynb_path, override_title=None, debug=False):
    """Converts a notebook to PDF with clean title, pandas tables, and LaTeX patches."""
    ipynb_path = os.path.abspath(ipynb_path)
    if not os.path.exists(ipynb_path):
        print(f"[!] File not found: {ipynb_path}")
        return

    base_name = os.path.splitext(ipynb_path)[0]
    target_dir = os.path.dirname(ipynb_path)
    
    scan_notebook_for_problems(ipynb_path)
    print(f"[*] Processing: {os.path.basename(ipynb_path)}")

    temp_ipynb = os.path.join(target_dir, f"__tmp_{os.path.basename(ipynb_path)}")
    temp_base = os.path.splitext(temp_ipynb)[0]
    temp_tex = temp_base + ".tex"
    temp_pdf = temp_base + ".pdf"
    final_pdf = base_name + ".pdf"

    try:
        with open(ipynb_path, 'r', encoding='utf-8') as f:
            nb = nbf.read(f, as_version=4)

        # Extract metadata before removing the duplicate title cell from the temporary copy.
        doc_title, doc_author = extract_title_and_author(nb, ipynb_path, override_title)
        nb = prepare_notebook_for_pdf(nb)
        convert_html_tables_to_latex(nb)

        with open(temp_ipynb, 'w', encoding='utf-8') as f:
            nbf.write(nb, f)

        # Convert to LaTeX
        convert_res = subprocess.run(
            [
                sys.executable, "-m", "nbconvert", "--to", "latex",
                "--TemplateExporter.exclude_input_prompt=" + str(REMOVE_EXECUTION_PROMPTS),
                "--TemplateExporter.exclude_output_prompt=" + str(REMOVE_EXECUTION_PROMPTS),
                temp_ipynb
            ], 
            capture_output=True, text=True
        )
        
        if convert_res.returncode != 0:
            print(f"    [FAILED] nbconvert failed: {convert_res.stderr[:300]}")
            return

        if not os.path.exists(temp_tex):
            print("    [FAILED] .tex file was not created.")
            return

        # Patch LaTeX
        with open(temp_tex, 'r', encoding='utf-8') as f:
            patched = patch_latex(f.read(), doc_title, doc_author)
        with open(temp_tex, 'w', encoding='utf-8') as f:
            f.write(patched)

        # Compile with xelatex
        pdf_res = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "-output-directory=" + target_dir, os.path.basename(temp_tex)],
            cwd=target_dir,
            capture_output=True, text=True
        )

        # xelatex can leave a partial/corrupt PDF behind on failure, so require
        # both a zero return code and a non-empty output file.
        pdf_ok = (
            pdf_res.returncode == 0
            and os.path.exists(temp_pdf)
            and os.path.getsize(temp_pdf) > 0
        )

        if pdf_ok:
            if os.path.exists(final_pdf):
                os.remove(final_pdf)
            os.replace(temp_pdf, final_pdf)
            print(f"    [SUCCESS] -> {os.path.basename(final_pdf)} (Title: '{doc_title}')")
        else:
            print("    [FAILED] xelatex failed to produce a valid PDF.")
            if debug:
                details = (pdf_res.stdout or "") + "\n" + (pdf_res.stderr or "")
                print(f"    --- LaTeX Error Log ---\n{details[-2000:]}")

    except Exception as e:
        print(f"    [ERROR] {e}")
    finally:
        # Always clean temporary files/folders unless debug mode was explicitly
        # requested. This also removes failed/partial PDFs and extracted image
        # folders left behind by nbconvert or XeLaTeX.
        if not debug:
            cleanup_temp_artifacts(temp_base)
        else:
            print(f"    [DEBUG] Temporary artifacts preserved at: {temp_base}*")

def create_notebooks(hw_num, num_problems):
    base_dir = get_base_path()
    target_path = os.path.join(base_dir, f"HW{hw_num}")
    os.makedirs(target_path, exist_ok=True)
    
    overwrite_all = False
    skip_all = False

    starter_code = (
        "# Setup & settings\n"
        "import numpy as np\n"
        "import matplotlib.pyplot as plt\n"
        "import pandas as pd\n\n"
        "# Ensures pandas Styler tables export directly to LaTeX/PDF\n"
        "pd.set_option('styler.render.repr', 'latex')\n"
    )

    for i in range(1, num_problems + 1):
        filename = f"{FIRST_NAME}_{LAST_NAME}_HW{hw_num}_Problem{i:02d}.ipynb"
        filepath = os.path.join(target_path, filename)

        if os.path.exists(filepath) and not overwrite_all and not skip_all:
            choice = input(f"[?] {filename} already exists. Overwrite? (y/n/all/skip): ").lower()
            if choice == 'all': overwrite_all = True
            elif choice == 'skip': skip_all = True; continue
            elif choice != 'y': continue

        if skip_all: continue

        nb = nbf.v4.new_notebook()
        cells = [
            nbf.v4.new_markdown_cell(f"# Homework {hw_num}: Problem {i} - *Problem Title*\n**{FIRST_NAME} {LAST_NAME}**"),
            nbf.v4.new_markdown_cell("(statement)"),
            nbf.v4.new_markdown_cell("## Solution"),
            nbf.v4.new_code_cell(starter_code),
            nbf.v4.new_markdown_cell("## Discussion\n\nAI Declaration: (declaration)\n\n(discussion)")
        ]
        nb['cells'] = cells
        with open(filepath, 'w', encoding='utf-8') as f:
            nbf.write(nb, f)
        print(f"  + Generated: {filename}")

def main():
    parser = argparse.ArgumentParser(description="Resilient HW CLI Tool")
    subparsers = parser.add_subparsers(dest="command")

    gen = subparsers.add_parser('gen')
    gen.add_argument('-hw', '--hw_num', type=str, required=True)
    gen.add_argument('-n', '--num', type=int, required=True)

    pdf = subparsers.add_parser('pdf')
    pdf.add_argument('-hw', '--hw_num', type=str)
    pdf.add_argument('-m', '--manual', type=str)
    pdf.add_argument('-t', '--title', type=str, help='Manually override document title')
    pdf.add_argument('-d', '--debug', action='store_true')

    args = parser.parse_args()

    # Check only after argument parsing so --help still works even on a fresh
    # machine. PDF conversion additionally requires Pandoc and XeLaTeX.
    if args.command in ('gen', 'pdf'):
        if not ensure_dependencies(require_pdf=(args.command == 'pdf')):
            return

    if args.command == 'gen':
        create_notebooks(args.hw_num, args.num)
    elif args.command == 'pdf':
        if args.manual:
            process_single_file(args.manual, override_title=args.title, debug=args.debug)
        elif args.hw_num:
            base_dir = get_base_path()
            target_dir = os.path.join(base_dir, f"HW{args.hw_num}")
            if not os.path.exists(target_dir):
                print(f"[!] Folder {target_dir} not found.")
                return
            files = sorted([f for f in os.listdir(target_dir) if f.endswith('.ipynb')])
            for f in files:
                process_single_file(os.path.join(target_dir, f), override_title=args.title, debug=args.debug)
        else:
            print("[!] Provide -hw or -m")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()