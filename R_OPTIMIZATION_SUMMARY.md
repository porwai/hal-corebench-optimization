# R Dependency Installation Optimization Summary

## Problem Statement
Agents were performing worse on R capsules because R dependencies were slower and harder to install. The main issues were:

1. **R base installation at runtime**: R base was being installed during agent execution, adding significant overhead
2. **Sequential package installation**: R packages were installed one-by-one, which is very slow
3. **No caching**: Packages were re-installed even if already present
4. **Aggressive early abort**: Installation would stop after just 2 failures
5. **No timeout handling**: Package installations could hang indefinitely
6. **Poor error handling**: Limited retry logic and error reporting

## Solutions Implemented

### 1. Pre-install R Base in VM Setup (`hal/utils/setup_vm.sh`)
**Change**: Added R base and R base-dev installation during VM setup phase
- **Benefit**: R is available immediately when agent starts, saving 1-2 minutes per run
- **Location**: Lines 17-20 in `setup_vm.sh`

```bash
# Pre-install R base to avoid runtime installation overhead
echo "Pre-installing R base..."
DEBIAN_FRONTEND=noninteractive apt-get install -y r-base r-base-dev
echo "R base installed"
```

### 2. Pre-install R Base in Docker (`hal/utils/docker/Dockerfile`)
**Change**: Added R base and required system libraries to Docker image
- **Benefit**: Consistent R availability across Docker and VM environments
- **Location**: Lines 3-15 in `Dockerfile`

### 3. Optimized R Package Installation (`agents/core_agent/main.py`)
**Major improvements to `ensure_cran_packages_installed()` function:**

#### a. Package Caching
- **Feature**: Checks which packages are already installed before attempting installation
- **Benefit**: Skips re-installation of already present packages, saving time
- **Implementation**: Lines 624-639

#### b. Batch Installation
- **Feature**: Attempts to install all packages in a single batch command first
- **Benefit**: Much faster for multiple packages (can be 5-10x faster than sequential)
- **Fallback**: Falls back to individual installation if batch fails
- **Implementation**: Lines 643-661

#### c. Timeout Handling
- **Feature**: Each package installation has a configurable timeout (default: 5 minutes)
- **Benefit**: Prevents hanging installations from blocking the entire process
- **Implementation**: Lines 675, 689

#### d. Improved Error Handling
- **Feature**: 
  - More lenient early abort (only after 5 failures or >30% failure rate)
  - Better error messages with stderr preview
  - Continues installation even if some packages fail (if majority succeed)
- **Benefit**: More resilient to transient failures, better diagnostics
- **Implementation**: Lines 698-712

#### e. Dependency Resolution
- **Feature**: Uses `dependencies=TRUE` in `install.packages()` to automatically install dependencies
- **Benefit**: Reduces manual dependency management and installation failures
- **Implementation**: Lines 647, 671

## Performance Improvements

### Expected Time Savings:
1. **R base installation**: ~1-2 minutes saved per run (moved to VM setup)
2. **Batch installation**: ~50-80% faster for multiple packages (e.g., 10 packages: 10-15 min → 2-4 min)
3. **Package caching**: ~100% time saved for already-installed packages
4. **Timeout handling**: Prevents indefinite hangs

### Example Scenario:
**Before**: 
- R base install: 2 min
- 10 packages sequential: 15 min
- **Total: ~17 minutes**

**After**:
- R base: 0 min (pre-installed)
- 10 packages batch: 3 min
- **Total: ~3 minutes**

**Time saved: ~14 minutes (82% reduction)**

## Testing Recommendations

1. **Test on R capsules**: Run the agent on R capsules to verify the optimizations work
2. **Monitor logs**: Check `[R-INSTALL]` log messages to see batch vs individual installation
3. **Verify caching**: Run the same capsule twice to confirm packages are cached
4. **Test failure scenarios**: Verify that partial failures don't break the entire process

## Configuration

The timeout can be adjusted by modifying the `timeout_per_package` parameter in the `ensure_cran_packages_installed()` function call (default: 300 seconds = 5 minutes).

## Backward Compatibility

All changes are backward compatible:
- If R base is already installed, the pre-install step is skipped
- If batch installation fails, it falls back to the previous sequential method
- The function signature change (added `timeout_per_package`) has a default value

## Files Modified

1. `hal/utils/setup_vm.sh` - Added R base pre-installation
2. `hal/utils/docker/Dockerfile` - Added R base to Docker image
3. `agents/core_agent/main.py` - Optimized `ensure_cran_packages_installed()` function

