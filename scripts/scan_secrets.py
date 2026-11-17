import subprocess
import re
import sys

# 1. Search full git history with git log
patterns = [
    r"AIza[0-9A-Za-z-_]{35}",
    r"sk-[a-zA-Z0-9_-]{20,}",
    r"hf_[a-zA-Z0-9]{34,}",
    r"GEMINI_API_KEY\s*=\s*['\"]?[A-Za-z0-9_-]{10,}",
    r"(?:password|passwd|secret)\s*[:=]\s*['\"][^'\"]{6,}['\"]",
]

print("=== Scanning full git history with git log -p ===")
cmd = ["git", "log", "-p", "--all", "-U0"]
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")

matches = []
current_commit = ""
current_file = ""

for line in proc.stdout:
    if line.startswith("commit "):
        current_commit = line.strip().split()[1]
    elif line.startswith("diff --git "):
        parts = line.strip().split()
        current_file = parts[-1]
    elif line.startswith("+") and not line.startswith("+++"):
        added_line = line[1:].strip()
        for p in patterns:
            if re.search(p, added_line, re.IGNORECASE):
                # Ignore placeholders like YOUR_KEY or example
                if not any(placeholder in added_line.lower() for placeholder in ["your_key", "your-api-key", "example", "dummy", "placeholder", "xxx"]):
                    matches.append((current_commit, current_file, added_line))

proc.wait()

print(f"Git log matches found: {len(matches)}")
for c, f, l in matches:
    print(f"Commit {c[:8]} | {f} | {l}")

print("\n=== Scanning currently tracked files ===")
tracked_cmd = ["git", "ls-files"]
tracked_files = subprocess.check_output(tracked_cmd, text=True, errors="replace").splitlines()

tracked_matches = []
for tf in tracked_files:
    try:
        with open(tf, "r", encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f, 1):
                for p in patterns:
                    if re.search(p, line, re.IGNORECASE):
                        if not any(placeholder in line.lower() for placeholder in ["your_key", "your-api-key", "example", "dummy", "placeholder", "xxx"]):
                            tracked_matches.append((tf, line_no, line.strip()))
    except Exception as e:
        pass

print(f"Tracked files matches found: {len(tracked_matches)}")
for tf, lno, l in tracked_matches:
    print(f"{tf}:{lno} | {l}")
