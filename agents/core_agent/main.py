from typing import Optional, List, Dict, Any
import tiktoken
import subprocess
from pathlib import Path
import shutil
import re
import json
import os
import sys
import ast
from functools import partial
from typing import Optional
from smolagents import CodeAgent, tool, LiteLLMModel, DuckDuckGoSearchTool, Tool, PythonInterpreterTool, VisitWebpageTool
from smolagents.models import MessageRole, Model
from smolagents.agents import ActionStep

# Monkey-patch smolagents to handle GPT-5
import smolagents.models
import re

def supports_stop_parameter(model_id: str) -> bool:
    """
    Check if the model supports the `stop` parameter.
    
    Not supported with reasoning models openai/o3, openai/o4-mini, and gpt-5 (and their versioned variants).
    """
    model_name = model_id.split("/")[-1]
    # o3, o4-mini, and gpt-5 (including versioned variants) don't support stop parameter
    pattern = r"^(o3[-\d]*|o4-mini[-\d]*|gpt-5[-\d]*)$"
    return not re.match(pattern, model_name)

# Replace the function in smolagents
smolagents.models.supports_stop_parameter = supports_stop_parameter

from mdconvert import MarkdownConverter, DocumentConverterResult

# Import agent_hints using absolute path
sys.path.append(os.path.dirname(__file__))
from agent_hints import AGENT_HINTS

import litellm

try:
    from hal.utils.weave_utils import MODEL_PRICES_DICT
except ImportError:
    # When running on VM or Docker, the utils module is not available
    from model_prices import MODEL_PRICES_DICT

AUTHORIZED_IMPORTS = [
    "requests",
    "zipfile",
    "os",
    "pandas",
    "numpy",
    "sympy",
    "json",
    "bs4",
    "pubchempy",
    "xml",
    "yahoo_finance",
    "Bio",
    "sklearn",
    "scipy",
    "pydub",
    "io",
    "PIL",
    "chess",
    "PyPDF2",
    "pptx",
    "torch",
    "datetime",
    "fractions",
    "csv",
]

def save_agent_steps(agent, kwargs, response, sample):
    for step in agent.memory.steps:
        if isinstance(step, ActionStep):
            step.agent_memory = None
    intermediate_steps = str(agent.memory.steps)
    with open("steps.json", "w") as f:
        json.dump({
            "agent_args": kwargs,
            "intermediate_steps": intermediate_steps,
            "response": str(response),
            "sample": sample
            }, f, indent=2)


def check_budget_exceeded(agent: CodeAgent, budget: float, model_name: str) -> bool:
    total_input_tokens = agent.monitor.total_input_token_count
    total_output_tokens = agent.monitor.total_output_token_count
    
    cost = MODEL_PRICES_DICT[model_name]["prompt_tokens"] * total_input_tokens + MODEL_PRICES_DICT[model_name]["completion_tokens"] * total_output_tokens
    
    print(f"Current cost: {cost}")
    if cost >= budget:
        return True
    return False


class TextInspectorTool(Tool):
    name = "inspect_file_as_text"
    description = """
You cannot load files yourself: instead call this tool to read a file as markdown text and ask questions about it.
This tool handles the following file extensions: [".html", ".htm", ".xlsx", ".pptx", ".wav", ".mp3", ".m4a", ".flac", ".pdf", ".docx"], and all other types of text files, including files without extensions (which are treated as text files). IT DOES NOT HANDLE IMAGES."""

    inputs = {
        "file_path": {
            "description": "The path to the file you want to read as text. Can be a file with an extension (like '.pdf') or a file without an extension (which will be treated as a text file). If it is an image, use the visualizer tool instead! DO NOT use this tool for an HTML webpage: use the web_search tool instead!",
            "type": "string",
        },
        "question": {
            "description": "[Optional]: Your question, as a natural language sentence. Provide as much context as possible. Do not pass this parameter if you just want to directly return the content of the file.",
            "type": "string",
            "nullable": True,
        },
    }
    output_type = "string"
    md_converter = MarkdownConverter()

    def __init__(self, model: Model, text_limit: int):
        super().__init__()
        self.model = model
        self.text_limit = text_limit

    def forward_initial_exam_mode(self, file_path, question):
        # Check if the file has no extension (no dot in the filename or the dot is at the beginning)
        _, file_extension = os.path.splitext(file_path)
        if not file_extension:
            # Treat files without extensions as text files
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                text_content = f.read()
            # Create a DocumentConverterResult with the text content
            result = DocumentConverterResult(title=None, text_content=text_content)
        else:
            # Normal conversion for files with extensions
            result = self.md_converter.convert(file_path)

        if file_path[-4:] in [".png", ".jpg"]:
            raise Exception("Cannot use inspect_file_as_text tool with images: use visualizer instead!")

        if ".zip" in file_path:
            return result.text_content

        if not question:
            return result.text_content

        if len(result.text_content) < 4000:
            return "Document content: " + result.text_content

        messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [
                    {
                        "type": "text",
                        "text": "Here is a file:\n### "
                        + str(result.title)
                        + "\n\n"
                        + result.text_content[: self.text_limit],
                    }
                ],
            },
            {
                "role": MessageRole.USER,
                "content": [
                    {
                        "type": "text",
                        "text": "Now please write a short, 5 sentence caption for this document, that could help someone asking this question: "
                        + question
                        + "\n\nDon't answer the question yourself! Just provide useful notes on the document",
                    }
                ],
            },
        ]
        return self.model(messages).content

    def forward(self, file_path, question: Optional[str] = None) -> str:
        # Check if the file has no extension (no dot in the filename or the dot is at the beginning)
        _, file_extension = os.path.splitext(file_path)
        if not file_extension:
            # Treat files without extensions as text files
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                text_content = f.read()
            # Create a DocumentConverterResult with the text content
            result = DocumentConverterResult(title=None, text_content=text_content)
        else:
            # Normal conversion for files with extensions
            result = self.md_converter.convert(file_path)

        if file_path[-4:] in [".png", ".jpg"]:
            raise Exception("Cannot use inspect_file_as_text tool with images: use visualizer instead!")

        if ".zip" in file_path:
            return result.text_content

        if not question:
            return result.text_content

        messages = [
            {
                "role": MessageRole.SYSTEM,
                "content": [
                    {
                        "type": "text",
                        "text": "You will have to write a short caption for this file, then answer this question:"
                        + question,
                    }
                ],
            },
            {
                "role": MessageRole.USER,
                "content": [
                    {
                        "type": "text",
                        "text": "Here is the complete file:\n### "
                        + str(result.title)
                        + "\n\n"
                        + result.text_content[: self.text_limit],
                    }
                ],
            },
            {
                "role": MessageRole.USER,
                "content": [
                    {
                        "type": "text",
                        "text": "Now answer the question below. Use these three headings: '1. Short answer', '2. Extremely detailed answer', '3. Additional Context on the document and question asked'."
                        + question,
                    }
                ],
            },
        ]
        return self.model(messages).content


@tool
def query_vision_language_model(query: str, image_path: str) -> str:
    """
    Query a vision language model with text and an image.
    Args:
        query: The text query or question to ask about the image
        image_path: Path to the image file to analyze
    Returns:
        str: The vision language model's response about the image
    """
    try:
        import base64
        from litellm import completion
        
        # Check if the image file exists
        if not os.path.exists(image_path):
            return f"Error: Image file not found at {image_path}"
        
        # Read and encode the image
        with open(image_path, "rb") as image_file:
            image_content = image_file.read()
            base64_image = base64.b64encode(image_content).decode("utf-8")
        
        # Create the message with text and image
        response = completion(
            model="gpt-4o-2024-11-20",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": query
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
        )
        
        # Return the model's response
        return response.choices[0].message.content
    
    except Exception as e:
        return f"Error processing vision query: {str(e)}"


@tool
def execute_bash(command: str) -> str:
    """
    Description: Execute a bash command and return its output.

    Internet usage is permitted ONLY for CRAN package installation for R, and basic dependency installation required to run research capsules.

    Do NOT use the internet for arbitrary web scraping, external API calls, or downloading artifacts from unknown remote servers.

    Common linux and python packages are available via apt and pip.
    Args:
        command: The bash command to execute
    """
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        output = f"Exit Code: {result.returncode}\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}"
        
        # Limit output to 1000 tokens
        encoding = tiktoken.get_encoding("cl100k_base")
        tokens = encoding.encode(output)
        if len(tokens) > 1000:
            output = encoding.decode(tokens[:1000]) + "\n... (output truncated to 1000 tokens)"
        
        return output
    except Exception as e:
        return f"Error executing command: {str(e)}"
    
    
@tool
def edit_file(command: str, path: str, content: Optional[str] = None, 
              line_number: Optional[int] = None, old_str: Optional[str] = None,
              new_str: Optional[str] = None) -> str:
    """
    Edit files in the project with various operations.
    Args:
        command: One of 'view', 'create', 'str_replace', 'insert', 'delete'
        path: Path to the file to edit
        content: Content for create/insert operations
        line_number: Line number for insert/delete operations
        old_str: String to replace when using str_replace
        new_str: New string for replacement
    """
    path = Path(path)
    try:
        if command == "view":
            if not path.exists():
                return f"Path {path} does not exist"
            elif path.is_dir():
                return f"Path {path} is a directory"
            else:
                with open(path, 'r') as f:
                    content = f.read()
                    return content[:5000] + ('...' if len(content) > 5000 else '')

        elif command == "create":
            if path.exists():
                return f"Error: {path} already exists"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w') as f:
                f.write(content or "")
            return f"Created file {path}"

        elif command == "str_replace":
            if not path.is_file():
                return f"Error: {path} is not a file"
            with open(path, 'r') as f:
                file_content = f.read()
            if old_str not in file_content:
                return f"Error: Could not find exact match for replacement string"
            new_content = file_content.replace(old_str, new_str)
            with open(path, 'w') as f:
                f.write(new_content)
            return f"Successfully replaced content in {path}"

        elif command == "insert":
            if not path.is_file():
                return f"Error: {path} is not a file"
            if line_number is None:
                return f"Error: Line number is required for insert operation"
            with open(path, 'r') as f:
                lines = f.readlines()
            if not isinstance(line_number, int) or line_number < 1 or line_number > len(lines) + 1:
                return f"Error: Invalid line number {line_number}"
            lines.insert(line_number - 1, content + '\n')
            with open(path, 'w') as f:
                f.writelines(lines)
            return f"Inserted content at line {line_number} in {path}"
        
        elif command == "delete":
            if not path.is_file():
                return f"Error: {path} is not a file"
            if line_number is None:
                return f"Error: Line number is required for delete operation"
            with open(path, 'r') as f:
                lines = f.readlines()
            if not isinstance(line_number, int) or line_number < 1 or line_number > len(lines):
                return f"Error: Invalid line number {line_number}"
            del lines[line_number - 1]
            with open(path, 'w') as f:
                f.writelines(lines)
            return f"Deleted line {line_number} from {path}"

    except Exception as e:
        return f"Error performing {command} operation: {str(e)}"


@tool
def file_content_search(query: str, exclude_pattern: Optional[str] = "*.pyc,*.git*,__pycache__,*.bin,*.exe,*.dll,*.so") -> str:
    """
    Search files in the current directory and subdirectories for specific content. This will only search the content of the files, not the files themselves.
    Args:
        query: The search term or regex pattern to look for
        exclude_pattern: Comma-separated file patterns to exclude from search (default: binaries and cache files)
    Returns:
        str: Matching passages with file paths and line numbers
    """
    if not query.strip():
        return "Error: Empty search pattern. Please provide a valid search term."
        
    results = []
    matches_found = 0
    files_searched = 0
    
    context_lines = 3  # Reduced from 100 to keep output manageable
    max_matches = 10
    max_files = 50
    
    exclude_patterns = exclude_pattern.split(',') if exclude_pattern else []
    
    try:
        all_files = list(Path('.').rglob('*'))
        
        files_to_search = []
        for file_path in all_files:
            if not file_path.is_file():
                continue
                
            # Skip excluded patterns
            skip = False
            for pattern in exclude_patterns:
                pattern = pattern.strip()
                if file_path.match(pattern):
                    skip = True
                    break
                
            # skip input.json, agent_args.json, and steps.json
            if file_path.name in ["input.json", "agent_args.json", "steps.json", "main.py"]:
                skip = True
            
            if not skip:
                files_to_search.append(file_path)
        
        # Limit to max_files
        files_to_search = files_to_search[:max_files]
        
        for file_path in files_to_search:
            if matches_found >= max_matches:
                break
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                files_searched += 1
                
                for i, line in enumerate(lines):
                    if matches_found >= max_matches:
                        break
                        
                    if re.search(query, line, re.IGNORECASE):
                        start = max(0, i - context_lines)
                        end = min(len(lines), i + context_lines + 1)
                        
                        context = ''.join(lines[start:end])
                        # Truncate very long contexts
                        if len(context) > 1000:
                            context = context[:500] + "\n... (truncated) ...\n" + context[-500:]
                            
                        results.append(f"File: {file_path} (line {i+1}):\n{context}\n---")
                        matches_found += 1
                        
            except (UnicodeDecodeError, IOError):
                # Skip binary or unreadable files
                continue
    
        if not results:
            return f"No matches found for '{query}' in {files_searched} files."
        
        summary = f"Found {matches_found} matches for '{query}' in {files_searched} files.\n\n"
        full_output = summary + "\n".join(results)
        
        return full_output
    
    except Exception as e:
        return f"Error searching files: {str(e)}"

# --- minimal R bootstrap ----
def ensure_R_minimal():
    print("[R-MINIMAL] checking for Rscript...")
    if shutil.which("Rscript") is not None:
        print("[R-MINIMAL] Rscript already exists, skipping base install.")
        return
    
    print("[R-MINIMAL] Rscript not found. Attempting minimal base R install via apt...")
    
    # Update package list (no sudo needed in Docker - containers run as root)
    print("[R-MINIMAL] running: apt-get update -y")
    proc = subprocess.run("apt-get update -y", shell=True, capture_output=True, text=True)
    print(f"[R-MINIMAL] Exit code {proc.returncode}")
    if proc.stdout: print(f"[R-MINIMAL][STDOUT]\n{proc.stdout}")
    if proc.stderr: print(f"[R-MINIMAL][STDERR]\n{proc.stderr}")
    
    if proc.returncode != 0:
        print("[R-MINIMAL] ERROR: apt-get update failed. Cannot proceed with R installation.")
        return
    
    # Install R base (no sudo needed in Docker)
    print("[R-MINIMAL] running: DEBIAN_FRONTEND=noninteractive apt-get install -y r-base")
    proc = subprocess.run("DEBIAN_FRONTEND=noninteractive apt-get install -y r-base", shell=True, capture_output=True, text=True)
    print(f"[R-MINIMAL] Exit code {proc.returncode}")
    if proc.stdout: print(f"[R-MINIMAL][STDOUT]\n{proc.stdout}")
    if proc.stderr: print(f"[R-MINIMAL][STDERR]\n{proc.stderr}")
    
    if proc.returncode != 0:
        print("[R-MINIMAL] ERROR: R installation failed.")
        return
    
    # Verify R installation succeeded
    if shutil.which("Rscript") is not None:
        print("[R-MINIMAL] R installation verified: Rscript is now available.")
    else:
        print("[R-MINIMAL] WARNING: R installation completed but Rscript not found in PATH.")
    
    print("[R-MINIMAL] completed attempt to install base R.")


def maybe_install_lightweight_R_packages():
    print("[R-LIGHT] scanning repo to see if R packages needed...")
    
    # Check if Rscript is available first
    if shutil.which("Rscript") is None:
        print("[R-LIGHT] Rscript not found. Skipping lightweight R package installation.")
        return
    
    need_r = False
    for root,_,files in os.walk("."):
        for f in files:
            if f.endswith(".Rmd") or f.endswith(".R"):
                need_r = True
                break

    if not need_r:
        print("[R-LIGHT] no R/Rmd detected. Skipping rmarkdown/tinytex install.")
        return
    
    print("[R-LIGHT] R code detected. Ensuring rmarkdown + tinytex are present...")

    # Use proper quote escaping: double quotes for shell, escaped single quotes for R strings
    subprocess.run("mkdir -p ~/R/library", shell=True)
    
    cmds = [
        'Rscript -e ".libPaths(c(\\"~/R/library\\", .libPaths())); if(!requireNamespace(\\"rmarkdown\\",quietly=TRUE)) install.packages(\\"rmarkdown\\",repos=\\"https://cloud.r-project.org\\",lib=\\"~/R/library\\")"',
        'Rscript -e ".libPaths(c(\\"~/R/library\\", .libPaths())); if(!requireNamespace(\\"tinytex\\",quietly=TRUE)) install.packages(\\"tinytex\\",repos=\\"https://cloud.r-project.org\\",lib=\\"~/R/library\\")"'
    ]
    
    for c in cmds:
        print(f"[R-LIGHT] running: {c}")
        proc = subprocess.run(c, shell=True, capture_output=True, text=True)
        print(f"[R-LIGHT] Exit code {proc.returncode}")
        if proc.stdout: print(f"[R-LIGHT][STDOUT]\n{proc.stdout}")
        if proc.stderr: print(f"[R-LIGHT][STDERR]\n{proc.stderr}")
        
        if proc.returncode != 0:
            print(f"[R-LIGHT] WARNING: Package installation command failed with exit code {proc.returncode}")

    print("[R-LIGHT] completed lightweight R package ensure step.")

BASE_R_PACKAGES = {
    "stats","graphics","grDevices","utils","datasets","methods","base"
}

def ensure_cran_packages_installed(root=".", timeout_per_package=300):
    """
    Install CRAN packages detected in R files with optimized batch installation.
    
    Args:
        root: Root directory to search for R files
        timeout_per_package: Timeout in seconds for each package installation (default: 5 minutes)
    
    Returns:
        bool: True if all packages installed successfully, False otherwise
    """
    # Check if Rscript is available first
    if shutil.which("Rscript") is None:
        print("[R-INSTALL] Rscript not found. Cannot install CRAN packages.")
        return False
    
    r_files=[]
    for dp,_,fs in os.walk(root):
        for f in fs:
            if f.endswith(".R") or f.endswith(".Rmd"):
                r_files.append(os.path.join(dp,f))

    if not r_files: 
        print("[R-INSTALL] No R files found. Skipping CRAN package installation.")
        return False

    pkgs=set()
    for f in r_files:
        try:
            txt=open(f,"r",encoding="utf8",errors="ignore").read()
            # Improved regex: handles library/require with quotes, spaces, and package::function syntax
            # Matches: library(pkg), library("pkg"), library('pkg'), require(pkg), pkg::function
            # Pattern has two capturing groups: one for library/require, one for ::
            found=re.findall(r'(?:library|require)\s*\(\s*(?:"|\')?([A-Za-z0-9_.]+)(?:"|\')?\s*\)|([A-Za-z0-9_.]+)::',txt)
            for match in found:
                # match is a tuple: (group1, group2)
                # For library/require: group1 has package, group2 is empty
                # For :: syntax: group1 is empty, group2 has package
                p = match[0] or match[1]  # Get the non-empty group
                if p and p not in BASE_R_PACKAGES:
                    pkgs.add(p)
        except Exception as e:
            print(f"[R-INSTALL] WARNING: Error reading file {f}: {e}")
            continue

    if not pkgs: 
        print("[R-INSTALL] No non-base R packages detected in R files.")
        return False

    print(f"[R-INSTALL] Detected {len(pkgs)} package(s) to install: {', '.join(sorted(pkgs))}")

    subprocess.run("mkdir -p ~/R/library", shell=True)
    
    # Check which packages are already installed to avoid re-installation
    installed_packages = set()
    check_cmd = 'Rscript -e ".libPaths(c(\\"~/R/library\\", .libPaths())); cat(paste(installed.packages(lib.loc=c(\\"~/R/library\\", .libPaths()))[,1], collapse=\\",\\"))"'
    try:
        proc = subprocess.run(check_cmd, shell=True, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            installed_packages = set(proc.stdout.strip().split(","))
            print(f"[R-INSTALL] Found {len(installed_packages)} already installed package(s)")
    except Exception as e:
        print(f"[R-INSTALL] WARNING: Could not check installed packages: {e}")
    
    # Filter out already installed packages
    packages_to_install = [p for p in pkgs if p not in installed_packages]
    if not packages_to_install:
        print(f"[R-INSTALL] All {len(pkgs)} package(s) are already installed. Skipping installation.")
        return True
    
    print(f"[R-INSTALL] Installing {len(packages_to_install)} new package(s): {', '.join(sorted(packages_to_install))}")
    
    # Try batch installation first (faster for multiple packages)
    if len(packages_to_install) > 1:
        print("[R-INSTALL] Attempting batch installation of all packages...")
        packages_str = ",".join([f'"{p}"' for p in packages_to_install])
        batch_cmd = f'Rscript -e ".libPaths(c(\\"~/R/library\\", .libPaths())); install.packages(c({packages_str}), repos=\\"https://cloud.r-project.org\\", lib=\\"~/R/library\\", dependencies=TRUE)"'
        
        try:
            proc = subprocess.run(batch_cmd, shell=True, capture_output=True, text=True, timeout=timeout_per_package * len(packages_to_install))
            if proc.returncode == 0:
                print(f"[R-INSTALL] Successfully installed all {len(packages_to_install)} package(s) in batch.")
                return True
            else:
                print(f"[R-INSTALL] Batch installation failed (exit code {proc.returncode}), falling back to individual installation...")
                if proc.stderr:
                    print(f"[R-INSTALL][STDERR] {proc.stderr[:500]}")  # Limit output
        except subprocess.TimeoutExpired:
            print(f"[R-INSTALL] Batch installation timed out, falling back to individual installation...")
        except Exception as e:
            print(f"[R-INSTALL] Batch installation error: {e}, falling back to individual installation...")
    
    # Fall back to individual installation with timeout and retry logic
    install_fail_count = 0
    failed_packages = []
    successful_packages = []
    
    for p in packages_to_install:
        # Use proper quote escaping: double quotes for shell, escaped quotes for R strings
        # Set libPaths to include user library, then install to user library
        cmd = f'Rscript -e ".libPaths(c(\\"~/R/library\\", .libPaths())); install.packages(\\"{p}\\", repos=\\"https://cloud.r-project.org\\", lib=\\"~/R/library\\", dependencies=TRUE)"'
        print(f"[R-INSTALL] Installing package: {p}")
        
        try:
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout_per_package)
            
            if proc.returncode != 0:
                install_fail_count += 1
                failed_packages.append(p)
                print(f"[R-INSTALL] Failed to install {p} (exit code {proc.returncode})")
                if proc.stderr:
                    # Show last 500 chars of stderr to avoid overwhelming output
                    stderr_preview = proc.stderr[-500:] if len(proc.stderr) > 500 else proc.stderr
                    print(f"[R-INSTALL][STDERR] {stderr_preview}")
            else:
                successful_packages.append(p)
                print(f"[R-INSTALL] Successfully installed {p}")
                
        except subprocess.TimeoutExpired:
            install_fail_count += 1
            failed_packages.append(p)
            print(f"[R-INSTALL] Timeout installing {p} (exceeded {timeout_per_package}s)")
        except Exception as e:
            install_fail_count += 1
            failed_packages.append(p)
            print(f"[R-INSTALL] Error installing {p}: {e}")

        # More lenient early abort: only abort if more than 30% fail or 5+ packages fail
        failure_rate = install_fail_count / len(packages_to_install) if packages_to_install else 0
        if install_fail_count >= 5 or (len(packages_to_install) > 10 and failure_rate > 0.3):
            print(f"[R-INSTALL] Early abort – {install_fail_count} package(s) failed ({failure_rate*100:.1f}% failure rate). Continuing with remaining packages may not be reliable.")
            break
    
    if failed_packages:
        print(f"[R-INSTALL] Completed with {len(failed_packages)} failure(s) out of {len(packages_to_install)}: {', '.join(failed_packages)}")
        print(f"[R-INSTALL] Successfully installed {len(successful_packages)} package(s): {', '.join(successful_packages)}")
        # Return False only if more than 50% failed
        if len(failed_packages) > len(successful_packages):
            return False
        else:
            print("[R-INSTALL] Continuing despite some failures (majority succeeded)")
            return True
    
    print(f"[R-INSTALL] Successfully installed all {len(packages_to_install)} package(s).")
    return True

def run(input: dict[str, dict], **kwargs) -> dict[str, str]:
    # Print package versions and conda list output
    print("=== Package Versions and Environment Information ===")
    try:
        # Run conda list command and print output
        conda_output = subprocess.run(['conda', 'list'], capture_output=True, text=True)
        print(conda_output.stdout)
    except Exception as e:
        print(f"[WARNING] Failed to run 'conda list': {str(e)}")
    print("=== End of Package Versions and Environment Information ===")
    
    # Create symbolic links
    try:
        cwd = os.getcwd()
        os.symlink(f'{cwd}/environment/data', '/data', target_is_directory=True)
        os.symlink(f'{cwd}/environment/code', '/code', target_is_directory=True)
        os.symlink(f'{cwd}/environment/results', '/results', target_is_directory=True)
    except Exception as e:
        print(f"[WARNING] Failed to create symbolic links for /data, /code, and /results: {str(e)}")

    #* Normalize Environment for Core-Bench Hard
    try:
        ensure_R_minimal()
        maybe_install_lightweight_R_packages()
        ensure_cran_packages_installed()
        print("[ENV] prep: minimal R and maybe install R packages")
    except Exception as e:
        print(f"[ENV][WARNING] prep failed, continuing: {e}")

    assert 'model_name' in kwargs, 'model_name is required'
    assert len(input) == 1, 'input must contain only one task'
    
    BUDGET = kwargs['budget'] if 'budget' in kwargs else None
    
    model_params = {}
    model_params['model_id'] = kwargs['model_name']

    # Handle reasoning parameters based on provider
    if 'reasoning_effort' in kwargs:
        if 'openrouter/' in kwargs['model_name']:
            # OpenRouter doesn't support reasoning_effort, convert to reasoning.max_tokens
            effort_to_tokens = {
                'low': 1024,
                'medium': 2048,
                'high': 4096
            }
            model_params['reasoning'] = {"max_tokens": effort_to_tokens.get(kwargs['reasoning_effort'], 4096)}
        else:
            # For Anthropic direct and other providers that support reasoning_effort
            model_params['reasoning_effort'] = kwargs['reasoning_effort']

    if 'temperature' in kwargs:
        model_params['temperature'] = kwargs['temperature']
        
    if 'gemini' in kwargs['model_name']:
        model_params['model_id'] = kwargs['model_name'].replace('gemini/', 'openai/')
        model_params['api_key'] = os.getenv('GEMINI_API_KEY')
        model_params['api_base'] = "https://generativelanguage.googleapis.com/v1beta/openai/"
        
    if 'together_ai' in kwargs['model_name']:
        model_params['model_id'] = kwargs['model_name'].replace('together_ai/', 'openai/')
        model_params['api_key'] = os.environ.get("TOGETHERAI_API_KEY")
        model_params['api_base'] = "https://api.together.xyz/v1"

    if kwargs['benchmark_name'] != 'corebench_easy' and kwargs['benchmark_name'] != 'corebench_medium' and kwargs['benchmark_name'] != 'corebench_hard':
        raise ValueError(f"Unknown benchmark. HAL agent does not support this benchmark: {kwargs['benchmark_name']}")
    
    # Determine agent type based on benchmark name or flags
    benchmark_name = kwargs['benchmark_name']
    
    # Check if base_agent flag is set to true
    if kwargs.get('base_agent', False):
        # Use base agent regardless of benchmark name
        agent_type = 'base'
        print(f"Using base agent (no hints) as requested by base_agent flag")
    elif benchmark_name in AGENT_HINTS:
        # Use the benchmark name directly as the agent type
        agent_type = benchmark_name
        
    # Validate agent type
    if agent_type not in AGENT_HINTS:
        raise ValueError(f"Invalid agent_type: {agent_type}. Must be one of: {', '.join(AGENT_HINTS.keys())}")
    
    # Get hints based on agent type
    hints = AGENT_HINTS[agent_type]
        
    task_id, task = list(input.items())[0]
    
    results = {}

    # Inject OpenRouter provider selection via litellm extra_body if requested
    try:
        import litellm  # type: ignore
        # Be lenient with unknown params on different backends
        litellm.drop_params = True

        if 'openrouter_provider_only' in kwargs and 'openrouter/' in kwargs.get('model_name', ''):
            providers_value = kwargs['openrouter_provider_only']
            if isinstance(providers_value, str):
                providers = [p.strip() for p in providers_value.split(',') if p.strip()]
            elif isinstance(providers_value, (list, tuple)):
                providers = [str(p) for p in providers_value]
            else:
                providers = [str(providers_value)]

            original_completion = getattr(litellm, 'completion', None)
            original_acompletion = getattr(litellm, 'acompletion', None)

            if not original_completion and not original_acompletion:
                print("[WARNING] OpenRouter provider pinning requested but litellm completion hooks not found; skipping provider pinning.")
            else:
                print(f"[INFO] Enabling OpenRouter provider pinning: providers={providers}")

            if original_completion is not None:
                def completion_with_provider(*args, **completion_kwargs):
                    model_field = completion_kwargs.get('model')
                    if isinstance(model_field, str) and 'openrouter/' in model_field:
                        extra_body = completion_kwargs.get('extra_body', {}) or {}
                        extra_body['provider'] = {'only': providers}
                        completion_kwargs['extra_body'] = extra_body
                    return original_completion(*args, **completion_kwargs)

                litellm.completion = completion_with_provider  # type: ignore

            if original_acompletion is not None:
                async def acompletion_with_provider(*args, **completion_kwargs):
                    model_field = completion_kwargs.get('model')
                    if isinstance(model_field, str) and 'openrouter/' in model_field:
                        extra_body = completion_kwargs.get('extra_body', {}) or {}
                        extra_body['provider'] = {'only': providers}
                        completion_kwargs['extra_body'] = extra_body
                    return await original_acompletion(*args, **completion_kwargs)  # type: ignore

                litellm.acompletion = acompletion_with_provider  # type: ignore
    except Exception as e:
        # Non-fatal: if litellm is unavailable or wrapping fails, continue without provider pinning
        print(f"[WARNING] Failed to enable OpenRouter provider pinning: {e}")

    model = LiteLLMModel(**model_params)
    
    # Prepend hints to the task prompt if available
    prompt = task['prompt']
    if hints:
        prompt = f"{hints}\n\n{prompt}"
    
    # Create a custom FinalAnswerTool that includes key validation and LLM-based giving-up detection
    class CustomFinalAnswerTool(Tool):
        name = "final_answer"
        description = "Provides a final answer to the given problem."
        inputs = {"answer": {"type": "any", "description": "The final answer to the problem"}}
        output_type = "any"

        def __init__(self, base_agent_flag, task_prompt, model=None):
            super().__init__()
            self.base_agent_flag = base_agent_flag
            self.task_prompt = task_prompt
            self.model = model  # Store the model for LLM-based checks
            print(f"[DEBUG] CustomFinalAnswerTool created with base_agent_flag={base_agent_flag}")
            
        def extract_dict_keys(self, prompt):
            """Extract dictionary keys from the task prompt using ast.literal_eval."""
            # Regular expression to find the dict_keys part
            pattern = r"dict_keys\((\[.*?\])\)"
            match = re.search(pattern, prompt)

            if match:
                list_str = match.group(1)
                print(f"[DEBUG] Found dict_keys pattern in prompt: {list_str}")

                array = ast.literal_eval(list_str)
                print(f"[DEBUG] Extracted keys: {array}")
                return array
            else:
                raise ValueError("No dict_keys pattern found in the prompt.")
        
        def check_if_giving_up(self, answer):
            """Use the LLM to determine if the answer indicates giving up on the task."""
            if self.model is None:
                print("[DEBUG] No model provided for giving-up check, skipping")
                return False, "No model available for check"
                
            # Convert answer to string representation for analysis
            answer_str = str(answer)
            
            # Create a prompt for the LLM to analyze the answer
            messages = [
                {
                    "role": MessageRole.SYSTEM,
                    "content": [
                        {
                            "type": "text",
                            "text": """You are an evaluator determining if an agent's answer indicates giving up on a task.
                            
All tasks are possible to complete, and the agent should never give up by saying a task is impossible, unavailable, or not reproducible.

Analyze the answer and determine if it indicates giving up (e.g., contains phrases like "unobtainable", "unavailable", "NOT REPRODUCIBLE", "ERROR", "NOT FOUND", "unknown", or null values).

Respond with ONLY "GIVING_UP" if the answer indicates giving up, or "VALID_ATTEMPT" if it appears to be a genuine attempt at solving the problem."""
                        }
                    ]
                },
                {
                    "role": MessageRole.USER,
                    "content": [
                        {
                            "type": "text",
                            "text": f"Analyze this answer to determine if the agent is giving up:\n\n{answer_str}"
                        }
                    ]
                }
            ]
            
            # Get the LLM's evaluation
            try:
                evaluation = self.model(messages).content.strip()
                print(f"[DEBUG] LLM evaluation of answer: {evaluation}")
                
                # Check if the LLM determined the agent is giving up
                is_giving_up = "GIVING_UP" in evaluation
                
                if is_giving_up:
                    feedback = "The answer indicates giving up on the task. Remember that all tasks are possible to complete. Please try a different approach to get the answer."
                else:
                    feedback = "The answer appears to be a genuine attempt at solving the problem."
                    
                return is_giving_up, feedback
            except Exception as e:
                print(f"[DEBUG] Error during LLM evaluation: {str(e)}")
                return False, f"Error during evaluation: {str(e)}"
            
        def forward(self, answer: Any) -> Any:
            """Process the final answer with key validation if base_agent is False."""
            print(f"[DEBUG] CustomFinalAnswerTool.forward called with answer: {answer}")
            print(f"[DEBUG] base_agent_flag is {self.base_agent_flag}")
            
            # First, check if the agent is giving up
            is_giving_up, feedback = self.check_if_giving_up(answer)
            if is_giving_up:
                error_msg = f"Submission rejected: {feedback}"
                print(f"[DEBUG] {error_msg}")
                raise Exception(error_msg)
            
            if not self.base_agent_flag:
                # Extract expected keys from the task prompt
                expected_keys = self.extract_dict_keys(self.task_prompt)
                
                # Validate that the answer is a dictionary with the expected keys
                if expected_keys:
                    if not isinstance(answer, dict):
                        error_msg = f"The submitted answer must be a dictionary with the following keys: {expected_keys}"
                        print(f"[DEBUG] Validation failed: {error_msg}")
                        raise Exception(error_msg)
                    
                    # Check if all expected keys are in the answer
                    missing_keys = [key for key in expected_keys if key not in answer]
                    if missing_keys:
                        error_msg = f"The submitted answer is missing the following keys: {missing_keys}"
                        print(f"[DEBUG] Validation failed: {error_msg}")
                        raise Exception(error_msg)
                    
                    # Check if there are any extra keys in the answer
                    extra_keys = [key for key in answer if key not in expected_keys]
                    if extra_keys:
                        error_msg = f"The submitted answer contains extra keys: {extra_keys}. Expected keys: {expected_keys}"
                        print(f"[DEBUG] Validation failed: {error_msg}")
                        raise Exception(error_msg)
                    
                    print(f"[DEBUG] Validation passed for answer: {answer}")
            else:
                print("[DEBUG] Skipping validation because base_agent_flag is True")
            
            # If validation passes or base_agent is True, return the answer
            print(f"[DEBUG] Returning final answer: {answer}")
            return answer

    # Create the custom FinalAnswerTool instance
    # This will replace the default FinalAnswerTool in the agent because they share the same name
    custom_final_answer_tool = CustomFinalAnswerTool(
        base_agent_flag=kwargs.get('base_agent', False),
        task_prompt=prompt,
        model=model  # Pass the model for LLM-based checks
    )
    
    # Include the custom tool directly in the CORE_TOOLS list
    CORE_TOOLS = [
        DuckDuckGoSearchTool(),
        VisitWebpageTool(),
        PythonInterpreterTool(),
        execute_bash,
        TextInspectorTool(model=model, text_limit=5000),
        edit_file,
        file_content_search,
        query_vision_language_model,
        custom_final_answer_tool,  # Add the custom tool directly to the list
    ]
    
    # Create the agent
    agent = CodeAgent(
        tools=CORE_TOOLS,
        planning_interval=4,
        max_steps=40,
        model=model,
        additional_authorized_imports=AUTHORIZED_IMPORTS,
        budget_exceeded_callback=partial(check_budget_exceeded, budget=BUDGET, model_name=kwargs['model_name']) if BUDGET else None,
    )

    response = agent.run(prompt)
    save_agent_steps(agent, kwargs, response, task)
    results[task_id] = response
        
    return results
