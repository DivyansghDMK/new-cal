# ═══════════════════════════════════════════════════════════════════════════════
# BUILD COMMANDS — CardioX EXE (STANDARDIZED)
# Run these in PowerShell from your project root.
# This flow uses build_exe.py (default: ONEDIR) for better cross-system stability.
# ═══════════════════════════════════════════════════════════════════════════════

# STEP 0: Go to project root
cd C:\Users\DELL\Downloads\dfg\merge

# STEP 1: Activate venv
.\.venv\Scripts\Activate.ps1

# STEP 2: Install pinned build dependencies (recommended)
# pip install -r src\requirements.txt

# STEP 3: Clean old artifacts
Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force dist  -ErrorAction SilentlyContinue

# STEP 4: Build (ONEDIR recommended for consistent runtime)
python build_exe.py --name CardioX

# STEP 5: Verify critical runtime files in output
Test-Path "dist\CardioX\CardioX.exe"
Test-Path "dist\CardioX\_internal\assets\Deckmountimg.png"

# STEP 6: Run
.\dist\CardioX\CardioX.exe

# STEP 7: Build setup.exe installer (requires Inno Setup 6)
python build_setup.py --name CardioX --version 1.0.0
# OR one-shot release:
# .\build_release.ps1 -Name CardioX -Version 1.0.0

# ───────────────────────────────────────────────────────────────────────────────
# DEBUG BUILD (if app closes immediately)
# python build_exe.py --name CardioX --console
# Then run from PowerShell to see traceback:
# .\dist\CardioX\CardioX.exe
# ───────────────────────────────────────────────────────────────────────────────

# DISTRIBUTION RULE
# Zip/share entire folder: dist\CardioX\
# Do NOT send only the EXE for onedir builds.

# COMMON ISSUES
# 1) ModuleNotFoundError:
#    - Build from clean venv
#    - Install pinned deps: pip install -r src\requirements.txt
#
# 2) Works on one PC, fails on another:
#    - Use same Python major/minor on builder machine
#    - Rebuild with --clean
#    - Share complete dist\CardioX\ folder
#
# 3) COM port mismatch on target PC:
#    - ECG settings may be fixed to a specific COM (e.g., COM8)
#    - Select correct COM on target machine or use auto-detect in app
