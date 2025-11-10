# Testing `prepare_environment_minimal_plus` on a VM

This guide explains how to test the `prepare_environment_minimal_plus` function on a VM before running a full agent evaluation.

## Quick Test (Recommended)

### Option 1: Automatic VM creation (Recommended)

**Easiest way** - Let the script create a VM automatically:

```bash
# From the agents/core_agent directory
python test_env_prep_vm.py
```

This will:
1. **Create a new VM** automatically (takes 2-5 minutes)
2. **Set up the VM** (install conda, dependencies, etc.)
3. Copy the test script and main.py
4. Run the test
5. Show you the results
6. Download the report JSON file
7. **Automatically destroy the VM** and all associated resources

**No VM name needed!** The script handles everything.

### Option 2: Test on an existing VM

If you already have a VM running from a previous agent run:

```bash
# Without cleanup (VM remains after test):
python test_env_prep_vm.py --vm-name <vm_name>

# With cleanup (VM destroyed after test):
python test_env_prep_vm.py --vm-name <vm_name> --cleanup

# Example:
python test_env_prep_vm.py --vm-name agent-corebench-hard-abc123 --cleanup
```

### Option 3: Manual SSH test

If you prefer to SSH manually:

```bash
# 1. SSH into your VM
ssh -i $SSH_PRIVATE_KEY_PATH agent@<VM_IP>

# 2. On the VM, navigate to where the agent files are (usually /home/agent)
cd /home/agent

# 3. Copy test_env_prep.py to the VM (from your local machine)
#    On your local machine:
scp -i $SSH_PRIVATE_KEY_PATH test_env_prep.py agent@<VM_IP>:/home/agent/

# 4. Run the test
python3 test_env_prep.py
```

## What the Test Does

The test script will:

1. **Check current environment**: Working directory, user, root status
2. **Run prepare_environment_minimal_plus()**: Execute all environment setup steps
3. **Report results**:
   - ✓ Steps that completed successfully
   - ✗ Errors encountered
   - Tool availability (Rscript, pdflatex, pandoc, etc.)
   - apt-get installation results
   - R package installation status
   - Symlink creation status

## Understanding the Output

### Successful Output Example:
```
STEPS COMPLETED:
  ✓ chdir:/code
  ✓ mkdir:created 6 dirs
  ✓ symlinks:/data:created,/code:created,/results:created
  ✓ apt-install:15 pkgs
  ✓ xvfb:started
  ✓ xvfb:DISPLAY=:99
  ✓ Rprofile:set cairo/ragg
  ✓ R_packages:rmarkdown:installed,knitr:installed,tinytex:installed

ERRORS ENCOUNTERED:
  (no errors)

SANITY CHECK - Available Tools:
  ✓ Rscript: available
  ✓ pdflatex: available
  ✓ pandoc: available
  ✓ xvfb-run: available
  ✓ gs: available
  ✓ convert: available
```

### Error Output Example:
```
STEPS COMPLETED:
  ✓ chdir:/code
  ✓ mkdir:created 3 dirs

ERRORS ENCOUNTERED:
  ✗ mkdir failed ../results: [Errno 13] Permission denied: '../results'
  ✗ symlink /data failed: [Errno 13] Permission denied: '/data'
  ✗ apt-get install failed: E: Could not open lock file /var/lib/dpkg/lock-frontend
```

## Common Issues and Solutions

### Permission Denied Errors

**Problem**: `Permission denied` when creating directories or symlinks

**Solutions**:
- The function now handles these gracefully and continues
- Check if directories already exist
- Some operations may require sudo (apt-get will try sudo automatically)

### R Not Installed

**Problem**: Rscript not found

**Solution**: The function will attempt to install `r-base` via apt-get. If it fails:
- Check if you have sudo access
- Check if apt-get update works
- The error will be reported in the output

### R Packages Can't Install

**Problem**: R packages fail to install (internet blocked)

**Solution**: 
- The function will try to install packages but continue if it fails
- Check the `R_packages` section in the output
- If internet is blocked, packages may need to be pre-installed or provided offline

### Graphics Libraries Missing

**Problem**: R rendering fails with "png device" errors

**Solution**: The function installs graphics libraries automatically:
- `libcairo2`, `libx11-6`, `libxt6`, etc.
- Check the `apt-install` section to see if they were installed

## Files Created

After running the test, you'll find:

1. **env_prep_test_report.json**: Full JSON report with all details
2. **env_report.json**: Report created by the function itself (if it succeeds)

## Next Steps

After testing:

1. **If test passes**: You're ready to run a full agent evaluation
2. **If test has errors**: 
   - Review the error messages
   - Check if the errors are critical (some may be non-fatal)
   - The function is designed to continue even with some failures
   - Try running a simple agent task to see if it works despite errors

## Running a Full Agent Test

Once you've verified the environment prep works:

```bash
hal-eval --benchmark corebench_hard \
  --agent_dir agents/core_agent \
  --agent_function main.run \
  --agent_name "Test Agent" \
  -A model_name="openai/o4-mini-2025-04-16" \
  --task_ids <task_id> --vm
```

The `prepare_environment_minimal_plus` function will run automatically at the start of each agent run.

