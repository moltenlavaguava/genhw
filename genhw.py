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
import json
import urllib.request
import urllib.error

# Loaded after the dependency check so the script can repair a missing
# nbformat installation instead of crashing immediately on startup.
nbf = None

# Command to make a new homework with the first number 
# being the homework number and second number being number of problems.

# Command to Generate the files         python genhw.py gen -hw 1 -n 2

# Command to Generate the pdfs          python genhw.py pdf -hw 2
# Command to Generate exam files        python genhw.py gen -exam 1 -n 2
# Command to Generate exam PDFs         python genhw.py pdf -exam 1


# ==============================================================================
# CONFIGURATION & REPOSITORY DEFAULTS
# ==============================================================================

REPO_URL = "https://github.com/moltenlavaguava/genhw"
REPO_API_COMMITS = "https://api.github.com/repos/moltenlavaguava/genhw/commits/main"
RAW_SCRIPT_URL = "https://raw.githubusercontent.com/moltenlavaguava/genhw/main/genhw.py"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")

DEFAULT_CONFIG = {
    "first_name": "First",
    "last_name": "Last",
    "subfolder": "Homework Problems",
    "exam_subfolder": "Exam Problems",
    "pdf_margin": "0.5in",
    "remove_notebook_title_cell": True,
    "remove_execution_prompts": True,
    "unnumber_markdown_headings": True,
    "check_updates": True,
}


def load_config():
    """Load configuration from config.json, prompting setup if missing."""
    if not os.path.exists(CONFIG_FILE):
        return prompt_initial_config()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
            return {**DEFAULT_CONFIG, **user_cfg}
    except Exception as e:
        print(f"[!] Warning: Could not read config.json ({e}). Using defaults.")
        return DEFAULT_CONFIG.copy()


def save_config(cfg):
    """Save dictionary to config.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
        print(f"[*] Configuration saved to {CONFIG_FILE}")
    except Exception as e:
        print(f"[!] Error saving config.json: {e}")


def prompt_initial_config():
    """Interactive prompt on first run to configure user identity."""
    print("\n" + "=" * 55)
    print(" [*] First-Time Setup: Configure your genhw profile")
    print("=" * 55)
    try:
        first = input("Enter your First Name [First]: ").strip() or "First"
        last = input("Enter your Last Name [Last]: ").strip() or "Last"
        subfolder = input("Homework subfolder [Homework Problems]: ").strip() or "Homework Problems"
        exam_sub = input("Exam subfolder [Exam Problems]: ").strip() or "Exam Problems"
    except (EOFError, KeyboardInterrupt):
        print()
        first, last, subfolder, exam_sub = "First", "Last", "Homework Problems", "Exam Problems"

    cfg = {
        **DEFAULT_CONFIG,
        "first_name": first,
        "last_name": last,
        "subfolder": subfolder,
        "exam_subfolder": exam_sub,
    }
    save_config(cfg)
    print("=" * 55 + "\n")
    return cfg


# Initialize active configuration and variables
CONFIG = load_config()
FIRST_NAME = CONFIG.get("first_name", "First")
LAST_NAME = CONFIG.get("last_name", "Last")
SUBFOLDER = CONFIG.get("subfolder", "Homework Problems")
EXAM_SUBFOLDER = CONFIG.get("exam_subfolder", "Exam Problems")
PDF_MARGIN = CONFIG.get("pdf_margin", "0.5in")
REMOVE_NOTEBOOK_TITLE_CELL = CONFIG.get("remove_notebook_title_cell", True)
REMOVE_EXECUTION_PROMPTS = CONFIG.get("remove_execution_prompts", True)
UNNUMBER_MARKDOWN_HEADINGS = CONFIG.get("unnumber_markdown_headings", True)


def reload_globals_from_config(cfg):
    """Update global variables after config changes."""
    global FIRST_NAME, LAST_NAME, SUBFOLDER, EXAM_SUBFOLDER, PDF_MARGIN
    global REMOVE_NOTEBOOK_TITLE_CELL, REMOVE_EXECUTION_PROMPTS, UNNUMBER_MARKDOWN_HEADINGS
    FIRST_NAME = cfg.get("first_name", "First")
    LAST_NAME = cfg.get("last_name", "Last")
    SUBFOLDER = cfg.get("subfolder", "Homework Problems")
    EXAM_SUBFOLDER = cfg.get("exam_subfolder", "Exam Problems")
    PDF_MARGIN = cfg.get("pdf_margin", "0.5in")
    REMOVE_NOTEBOOK_TITLE_CELL = cfg.get("remove_notebook_title_cell", True)
    REMOVE_EXECUTION_PROMPTS = cfg.get("remove_execution_prompts", True)
    UNNUMBER_MARKDOWN_HEADINGS = cfg.get("unnumber_markdown_headings", True)


# ==============================================================================
# AUTO-UPDATE & SEAMLESS RE-EXECUTION
# ==============================================================================

def check_for_updates():
    """Check for updates against GitHub and prompt to update."""
    is_git_repo = os.path.exists(os.path.join(SCRIPT_DIR, ".git"))
    if is_git_repo:
        return _check_git_updates()
    else:
        return _check_standalone_updates()


def _check_git_updates():
    """Check and pull updates using Git inside a cloned repository."""
    try:
        subprocess.run(
            ["git", "-C", SCRIPT_DIR, "fetch", "origin", "main"],
            capture_output=True,
            timeout=3,
            check=False,
        )

        res = subprocess.run(
            ["git", "-C", SCRIPT_DIR, "rev-list", "--count", "HEAD..origin/main"],
            capture_output=True,
            text=True,
            check=False,
        )

        if res.returncode == 0:
            behind_count = int(res.stdout.strip() or 0)
            if behind_count > 0:
                print("\n" + "=" * 60)
                print(f" [!] An update is available! You are {behind_count} commit(s) behind {REPO_URL}.")
                print("=" * 60)
                if _ask_yes_no("[?] Would you like to pull the latest updates now?", default=True):
                    print("[*] Pulling latest updates...")
                    pull_res = subprocess.run(
                        ["git", "-C", SCRIPT_DIR, "pull", "--ff-only"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if pull_res.returncode == 0:
                        print("[SUCCESS] Repository updated successfully!")
                        return True
                    else:
                        print(f"[!] Git pull failed: {pull_res.stderr.strip()}")
                        print("    You may have local uncommitted changes.\n")
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass
    return False


def _check_standalone_updates():
    """Fallback update check for standalone genhw.py without a .git folder."""
    try:
        req = urllib.request.Request(
            REPO_API_COMMITS,
            headers={"User-Agent": "genhw-updater"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            remote_sha = data.get("sha", "")[:7]

        sha_file = os.path.join(SCRIPT_DIR, ".version")
        local_sha = ""
        if os.path.exists(sha_file):
            with open(sha_file, "r") as f:
                local_sha = f.read().strip()

        if remote_sha and local_sha and remote_sha != local_sha:
            print("\n" + "=" * 60)
            print(f" [!] A new release of genhw is available on GitHub (commit {remote_sha})!")
            print("=" * 60)
            if _ask_yes_no("[?] Update genhw.py directly from GitHub?", default=True):
                with urllib.request.urlopen(RAW_SCRIPT_URL, timeout=5) as dl:
                    new_code = dl.read().decode("utf-8")
                with open(__file__, "w", encoding="utf-8") as f:
                    f.write(new_code)
                with open(sha_file, "w") as f:
                    f.write(remote_sha)
                print("[SUCCESS] genhw.py updated successfully!")
                return True
    except Exception:
        pass
    return False


# Python packages used by this script and by the starter notebook it creates.
PYTHON_DEPENDENCIES = {
    "nbformat": "nbformat",
    "nbconvert": "nbconvert",
    "numpy": "numpy",
    "pandas": "pandas",
    "matplotlib": "matplotlib",
    "scipy": "scipy",
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


def _get_uv_command():
    """Return command prefix to run 'uv pip install' targeting the active Python, if uv is available."""
    if _command_works("uv"):
        return ["uv", "pip", "install", "--python", sys.executable]
    if _python_module_works("uv"):
        return [sys.executable, "-m", "uv", "pip", "install", "--python", sys.executable]
    return None


def _install_python_dependencies(packages):
    """Auto-install Python packages via uv if available, falling back to pip."""
    if not packages:
        return True

    # 1. Try uv first for speed
    uv_cmd = _get_uv_command()
    if uv_cmd:
        print(f"\n[*] Auto-installing Python dependencies using uv: {', '.join(packages)}")
        try:
            result = subprocess.run([*uv_cmd, *packages])
            if result.returncode == 0:
                return True
            print("[!] uv install failed; falling back to standard pip...")
        except Exception as e:
            print(f"[!] Could not run uv ({e}); falling back to standard pip...")

    # 2. Fallback to pip
    print(f"\n[*] Installing Python dependencies using pip: {', '.join(packages)}")
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
    """Check dependencies and auto-install Python packages via uv/pip; prompt for system tools."""
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

    # Auto-install Python packages via uv (or pip) without friction
    if missing_python:
        if not _install_python_dependencies(missing_python):
            print("[!] One or more Python dependencies could not be installed.")
            return False
        importlib.invalidate_caches()

    # Heavy system tools (Pandoc / LaTeX) require system-level privileges; prompt first
    if missing_system:
        print("\n[!] Missing system tools for PDF export: " + ", ".join(missing_system))
        if not _ask_yes_no("Would you like to install/repair them now?", default=True):
            print("[!] System tool installation cancelled.")
            return False

        if not _install_system_dependencies(missing_system):
            return False

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

    if nbf is None:
        nbf = importlib.import_module("nbformat")
    return True


def cleanup_temp_artifacts(temp_base):
    """Remove every temporary file/folder created for one notebook conversion."""
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


def get_base_path(exam=False):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    subfolder = EXAM_SUBFOLDER if exam else SUBFOLDER
    if subfolder.strip():
        path = os.path.join(script_dir, subfolder.strip())
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
    """Preserve common HTML presentation tags when exporting Markdown to PDF."""
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

    text = re.sub(
        r'<\s*center\s*>([\s\S]*?)<\s*/\s*center\s*>',
        lambda m: latex_raw_block('center', m.group(1)),
        text,
        flags=re.IGNORECASE,
    )

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
    text = _html_inline_to_markdown(text)
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
        for line in cell.source.splitlines():
            if line.strip().startswith('|') and line.count('|') > 8:
                warnings.append(f"Cell {i}: Wide Markdown table detected; it may need wrapping.")
                break

    if warnings:
        print(f"\n[!] PRE-FLIGHT WARNINGS for {os.path.basename(nb_path)}:")
        for w in warnings:
            print(f"    - {w}")
        print("-" * 40)


def extract_title_and_author(nb, filename, override_title=None):
    """Safely extracts Title and Author with a multi-level fallback cascade."""
    if override_title:
        return override_title, f"{FIRST_NAME} {LAST_NAME}"

    title = None
    author = None

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

    if not title or not author:
        base = os.path.splitext(os.path.basename(filename))[0]
        base = re.sub(r'^_+tmp_+', '', base, flags=re.IGNORECASE)
        parts = base.split('_')
        
        if len(parts) >= 4 and re.fullmatch(r'(HW|Exam)\d+', parts[2], re.IGNORECASE):
            author = author or f"{parts[0]} {parts[1]}"
            hw = re.sub(r'^(HW|Exam)', lambda m: 'Homework ' if m[0].lower() == 'hw' else 'Exam ', parts[2], flags=re.IGNORECASE)
            prob_num = re.sub(r'(?i)^Problem0*', '', parts[3])
            prob = f"Problem {prob_num}"
            title = title or f"{hw}: {prob}"
        else:
            clean_base = base.replace('_', ' ').replace('-', ' ').strip().title()
            title = title or (clean_base if clean_base else "Homework Submission")
            author = author or f"{FIRST_NAME} {LAST_NAME}"

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
                nb.cells.pop(0)

    for cell in nb.cells:
        if cell.cell_type == 'markdown':
            cell.source = preserve_markdown_html_formatting(cell.source)

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
                if any(k.startswith('image/') for k in data):
                    data.pop('text/plain', None)
                    cleaned.append(output)
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

                        caption_match = re.search(
                            r'<caption[^>]*>([\s\S]*?)</caption>',
                            html_str,
                            re.IGNORECASE,
                        )
                        if caption_match:
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
                                alignment = r'\centering ' if centered else r'\raggedright '
                                rendered_caption = alignment + rendered_caption

                                if caption_side == 'bottom':
                                    marker = r'\GenhwBottomCaption{' + rendered_caption + '}'
                                    latex = latex.replace(r'\endlastfoot', marker + '\n' + r'\endlastfoot', 1)
                                else:
                                    marker = r'\GenhwTopCaption{' + rendered_caption + '}'
                                    latex = latex.replace(r'\toprule', marker + '\n' + r'\toprule', 1)

                        data['text/latex'] = latex
                except Exception:
                    pass


def patch_latex(tex_content, title, author):
    """Clean document metadata, headings, margins, code layout, and wide tables."""
    # 1. Fix Python/nbconvert counter issue.
    if r"\newcounter{none}" not in tex_content:
        tex_content = tex_content.replace(
            r"\begin{document}",
            "\\newcounter{none}\n\\begin{document}",
            1,
        )

    # 2. Make the page geometry deterministic.
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

    # 4. Heading unnumbering.
    if UNNUMBER_MARKDOWN_HEADINGS:
        for cmd in ('section', 'subsection', 'subsubsection', 'paragraph', 'subparagraph'):
            tex_content = re.sub(rf'\\{cmd}(?!\*)\{{', rf'\\{cmd}*{{', tex_content)

    return fit_longtables(tex_content)


def brace_end(text, start):
    """Return the index after a balanced {...} group, or raise ValueError."""
    if start >= len(text) or text[start] != '{':
        raise ValueError("Expected opening brace")
    depth = 0
    i = start
    while i < len(text):
        if text[i] == '\\':
            i += 2
            continue
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("Unclosed brace group")


def column_count(spec):
    """Count top-level standard columns, ignoring width/decorator contents."""
    count = 0
    i = 0
    while i < len(spec):
        char = spec[i]
        if char.isspace() or char == '|':
            i += 1
            continue
        if char in '@!><':
            i += 1
            while i < len(spec) and spec[i].isspace():
                i += 1
            i = brace_end(spec, i)
        elif char in 'lcrXpmb':
            count += 1
            i += 1
            if char in 'pmb':
                while i < len(spec) and spec[i].isspace():
                    i += 1
                i = brace_end(spec, i)
        elif char == '*':
            i += 1
            while i < len(spec) and spec[i].isspace():
                i += 1
            end = brace_end(spec, i)
            repeats = int(spec[i + 1:end - 1])
            i = end
            while i < len(spec) and spec[i].isspace():
                i += 1
            end = brace_end(spec, i)
            count += repeats * column_count(spec[i + 1:end - 1])
            i = end
        else:
            raise ValueError("Unsupported custom column type")
    return count


def fit_longtables(text):
    """Fit standard longtables and keep HTML captions in their header/footer."""
    opening = re.compile(r'\\begin\{longtable\}(?:\[[^\]]*\])?\s*\{')
    ending = r'\end{longtable}'
    replacements = []
    for match in opening.finditer(text):
        try:
            end_spec = brace_end(text, match.end() - 1)
            num_cols = column_count(text[match.end():end_spec - 1])
            end_table = text.index(ending, end_spec)
            if num_cols < 1:
                continue
        except ValueError:
            continue
        body = text[end_spec:end_table]
        for command in ('GenhwTopCaption', 'GenhwBottomCaption'):
            marker = '\\' + command + '{'
            while marker in body:
                start = body.index(marker)
                end = brace_end(body, start + len(marker) - 1)
                caption = body[start + len(marker):end - 1]
                row = (rf'\multicolumn{{{num_cols}}}{{c}}{{'
                       rf'\parbox{{0.94\linewidth}}{{\normalfont {caption}\par}}}}'
                       + r'\\*[0.5em]')
                body = body[:start] + row + body[end:]
        if num_cols <= 3:
            size, spacing = r'\normalsize', '4pt'
        elif num_cols <= 6:
            size, spacing = r'\footnotesize', '2.5pt'
        else:
            size, spacing = r'\scriptsize', '2pt'
        width = 0.96 / num_cols
        spec = ''.join(
            rf'>{{\raggedright\arraybackslash}}p{{\dimexpr {width:.6f}\linewidth-2\tabcolsep\relax}}'
            for _ in range(num_cols)
        )
        replacement = (
            '\\begingroup\n' + size + '\n'
            + rf'\setlength{{\tabcolsep}}{{{spacing}}}' + '\n'
            + r'\renewcommand{\arraystretch}{1.05}' + '\n'
            + rf'\begin{{longtable}}[]{{{spec}}}' + body + ending
            + '\n\\endgroup'
        )
        replacements.append((match.start(), end_table + len(ending), replacement))
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


def compile_pdf(temp_tex, target_dir, max_passes=3):
    """Rerun XeLaTeX only when its output requests another pass."""
    rerun = re.compile(
        r'rerun to get|label\(s\) may have changed|rerun to get cross-references|'
        r'table widths have changed|rerun LaTeX|Please \(re\)run', re.IGNORECASE
    )
    for pass_number in range(1, max_passes + 1):
        print(f"    [*] Compiling PDF (pass {pass_number}/{max_passes})...", flush=True)
        result = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error",
             "-output-directory=" + target_dir, os.path.basename(temp_tex)],
            cwd=target_dir, capture_output=True, text=True,
        )
        log = (result.stdout or '') + '\n' + (result.stderr or '')
        if result.returncode != 0 or not rerun.search(log):
            return result
    print("    [!] LaTeX still requests another pass; review references/table widths.")
    return result


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

        doc_title, doc_author = extract_title_and_author(nb, ipynb_path, override_title)
        print("    [*] Preparing notebook and converting HTML tables...", flush=True)
        nb = prepare_notebook_for_pdf(nb)
        convert_html_tables_to_latex(nb)

        with open(temp_ipynb, 'w', encoding='utf-8') as f:
            nbf.write(nb, f)

        print("    [*] Converting notebook to LaTeX...", flush=True)
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

        print("    [*] Formatting tables, captions, and page layout...", flush=True)
        with open(temp_tex, 'r', encoding='utf-8') as f:
            patched = patch_latex(f.read(), doc_title, doc_author)
        with open(temp_tex, 'w', encoding='utf-8') as f:
            f.write(patched)

        pdf_res = compile_pdf(temp_tex, target_dir)

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
        if not debug:
            cleanup_temp_artifacts(temp_base)
        else:
            print(f"    [DEBUG] Temporary artifacts preserved at: {temp_base}*")


def create_notebooks(hw_num, num_problems, exam=False):
    label = "Exam" if exam else "Homework"
    prefix = "Exam" if exam else "HW"
    base_dir = get_base_path(exam=exam)
    target_path = os.path.join(base_dir, f"{prefix}{hw_num}")
    os.makedirs(target_path, exist_ok=True)
    
    overwrite_all = False
    skip_all = False

    starter_code = (
        "# Setup & settings\n"
        "import math\n"
        "import numpy as np\n"
        "from scipy.optimize import fsolve\n"
        "import matplotlib.pyplot as plt\n"
        "import pandas as pd\n\n"
        "# Display tables in VS Code; genhw.py converts HTML tables for PDF.\n"
        "pd.set_option('styler.render.repr', 'html')\n"
    )

    for i in range(1, num_problems + 1):
        filename = f"{FIRST_NAME}_{LAST_NAME}_{prefix}{hw_num}_Problem{i:02d}.ipynb"
        filepath = os.path.join(target_path, filename)

        if os.path.exists(filepath) and not overwrite_all and not skip_all:
            choice = input(f"[?] {filename} already exists. Overwrite? (y/n/all/skip): ").lower()
            if choice == 'all': overwrite_all = True
            elif choice == 'skip': skip_all = True; continue
            elif choice != 'y': continue

        if skip_all: continue

        nb = nbf.v4.new_notebook()
        cells = [
            nbf.v4.new_markdown_cell(f"# {label} {hw_num}: Problem {i} - *Problem Title*\n**{FIRST_NAME} {LAST_NAME}**"),
            nbf.v4.new_markdown_cell("(statement)"),
            nbf.v4.new_markdown_cell("## Solution"),
            nbf.v4.new_code_cell(starter_code),
            nbf.v4.new_markdown_cell(
                "## Discussion\n\n(discussion)" if exam else
                "## Discussion\n\nAI Declaration: (declaration)\n\n(discussion)"
            )
        ]
        nb['cells'] = cells
        with open(filepath, 'w', encoding='utf-8') as f:
            nbf.write(nb, f)
        print(f"  + Generated: {filename}")


def positive_int(value):
    """Reject invalid numbers before checking dependencies or creating folders."""
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive integer")
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


# ==============================================================================
# CLI INTERFACE
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Homework and Exam Notebook/PDF Tool")
    parser.add_argument("--skip-update", action="store_true", help="Skip checking for updates")
    subparsers = parser.add_subparsers(dest="command")

    gen = subparsers.add_parser('gen', help="Create problem notebook templates")
    gen_target = gen.add_mutually_exclusive_group(required=True)
    gen_target.add_argument('-hw', '--hw_num', type=positive_int, help='Homework number')
    gen_target.add_argument('-exam', '--exam', '--exam_num', dest='exam_num', type=positive_int, help='Exam number')
    gen.add_argument('-n', '--num', type=positive_int, required=True, help='Number of problem notebooks to create')

    pdf = subparsers.add_parser('pdf', help="Export notebooks to PDF")
    pdf_target = pdf.add_mutually_exclusive_group(required=True)
    pdf_target.add_argument('-hw', '--hw_num', type=positive_int, help='Export a homework folder')
    pdf_target.add_argument('-exam', '--exam', '--exam_num', dest='exam_num', type=positive_int, help='Export an exam folder')
    pdf_target.add_argument('-m', '--manual', type=str, help='Export one notebook by path')
    pdf.add_argument('-t', '--title', type=str, help='Manually override document title')
    pdf.add_argument('-d', '--debug', action='store_true', help='Preserve intermediate LaTeX files')

    # Command: config
    cfg_cmd = subparsers.add_parser('config', help="View or modify user configuration")
    cfg_cmd.add_argument('--set', nargs='+', help="Set config values (e.g. --set first_name=Alice subfolder='Homework')")

    # Command: update
    subparsers.add_parser('update', help="Force check and pull updates from GitHub")

    args = parser.parse_args()

    # Load configuration from config.json
    cfg = load_config()
    reload_globals_from_config(cfg)

    # Explicit update command
    if args.command == 'update':
        updated = check_for_updates()
        if not updated:
            print("[*] genhw is already up to date.")
        return

    # Automatic update check (with instant command resume)
    if cfg.get("check_updates", True) and not args.skip_update and args.command != 'config':
        if check_for_updates():
            clean_args = [arg for arg in sys.argv[1:] if arg != "--skip-update"] + ["--skip-update"]
            print("[*] Resuming command with updated version...\n")
            try:
                res = subprocess.run([sys.executable, os.path.abspath(__file__), *clean_args])
                sys.exit(res.returncode)
            except Exception as e:
                print(f"[!] Error resuming command: {e}")
                sys.exit(1)

    # Config command handler
    if args.command == 'config':
        if args.set:
            for item in args.set:
                if '=' in item:
                    k, v = item.split('=', 1)
                    k, v = k.strip(), v.strip()
                    if v.lower() in ("true", "yes", "1"):
                        cfg[k] = True
                    elif v.lower() in ("false", "no", "0"):
                        cfg[k] = False
                    else:
                        cfg[k] = v
            save_config(cfg)
            reload_globals_from_config(cfg)
        else:
            print(f"\nCurrent Configuration ({CONFIG_FILE}):")
            print(json.dumps(cfg, indent=4))
            print(f"\nModify via: python genhw.py config --set first_name=YourName\n")
        return

    # Check dependencies only for commands that need them
    if args.command in ('gen', 'pdf'):
        if not ensure_dependencies(require_pdf=(args.command == 'pdf')):
            return

    if args.command == 'gen':
        exam = args.exam_num is not None
        create_notebooks(args.exam_num if exam else args.hw_num, args.num, exam=exam)
    elif args.command == 'pdf':
        if args.manual:
            process_single_file(args.manual, override_title=args.title, debug=args.debug)
        elif args.hw_num is not None or args.exam_num is not None:
            exam = args.exam_num is not None
            prefix = "Exam" if exam else "HW"
            number = args.exam_num if exam else args.hw_num
            base_dir = get_base_path(exam=exam)
            target_dir = os.path.join(base_dir, f"{prefix}{number}")
            if not os.path.exists(target_dir):
                print(f"[!] Folder {target_dir} not found.")
                return
            files = sorted(f for f in os.listdir(target_dir)
                           if f.lower().endswith('.ipynb')
                           and not f.lower().startswith('__tmp_')
                           and os.path.isfile(os.path.join(target_dir, f)))
            if not files:
                print(f"[!] No notebooks found in {target_dir}.")
            for f in files:
                process_single_file(os.path.join(target_dir, f), override_title=args.title, debug=args.debug)
        else:
            print("[!] Provide -hw, -exam, or -m")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()