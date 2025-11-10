# Testing Guide for `test_env_prep_vm.py`

## Quick Start

**Simplest test (creates VM, tests, destroys VM automatically):**

Run from repo root (recommended - automatically loads .env file):
```bash
python agents/core_agent/test_env_prep_vm.py
```

Or run from agents/core_agent directory:
```bash
cd agents/core_agent
python test_env_prep_vm.py
```

That's it! The script will:
1. **Load .env file** from repo root (if running from repo root)
2. Create a VM automatically
3. Set it up (conda, Python packages)
4. Test `prepare_environment_minimal_plus()`
5. **Automatically destroy the VM** (guaranteed)

## VM Cleanup Guarantee

✅ **100% Guaranteed Cleanup** - The VM will be destroyed in these scenarios:

1. **Normal completion** - Cleanup happens in `finally` block
2. **Test fails** - Cleanup happens in `finally` block  
3. **Early failure** (can't connect, setup fails) - Cleanup happens in `finally` block
4. **Keyboard interrupt (Ctrl+C)** - Cleanup happens in exception handler
5. **Unexpected exception** - Cleanup happens in exception handler

The cleanup code is in **three places** for maximum safety:
- `finally` block in `run_test_on_vm()` (primary)
- Exception handler in `main()` (backup)
- Keyboard interrupt handler in `main()` (backup)

## What Gets Deleted

When cleanup runs, `delete_vm()` removes:
- ✅ The VM itself
- ✅ OS disk
- ✅ Data disks (if any)
- ✅ Network interface
- ✅ Public IP address
- ✅ Virtual network (if not used by other resources)

## Prerequisites

**Option 1: Use .env file (Recommended)**

Create a `.env` file in your repo root with:
```bash
SSH_PUBLIC_KEY_PATH=/path/to/your/public_key.pub
SSH_PRIVATE_KEY_PATH=/path/to/your/private_key
NETWORK_SECURITY_GROUP_NAME=your-nsg-name
AZURE_SUBSCRIPTION_ID=your-subscription-id
AZURE_RESOURCE_GROUP_NAME=your-resource-group
AZURE_LOCATION=your-location  # e.g., "eastus"
```

The script will automatically load this when run from the repo root.

**Option 2: Export environment variables**

```bash
export SSH_PUBLIC_KEY_PATH="/path/to/your/public_key.pub"
export SSH_PRIVATE_KEY_PATH="/path/to/your/private_key"
export NETWORK_SECURITY_GROUP_NAME="your-nsg-name"
export AZURE_SUBSCRIPTION_ID="your-subscription-id"
export AZURE_RESOURCE_GROUP_NAME="your-resource-group"
export AZURE_LOCATION="your-location"  # e.g., "eastus"
```

## Testing Options

### Option 1: Automatic (Recommended)
```bash
# From repo root (loads .env automatically)
python agents/core_agent/test_env_prep_vm.py

# Or from agents/core_agent directory
cd agents/core_agent
python test_env_prep_vm.py
```
- Creates VM automatically
- Always destroys VM after test
- No VM name needed
- Automatically loads .env file if run from repo root

### Option 2: Use Existing VM
```bash
# Test and keep VM
python agents/core_agent/test_env_prep_vm.py --vm-name existing-vm-name

# Test and destroy VM
python agents/core_agent/test_env_prep_vm.py --vm-name existing-vm-name --cleanup
```

## Verifying Cleanup

After the test completes, you should see:
```
================================================================================
Cleaning up VM...
================================================================================
✓ VM test-env-prep-abc12345 and associated resources deleted successfully
```

You can also verify in Azure Portal:
1. Go to your Resource Group
2. Check that the VM is gone
3. Check that associated resources (disks, NICs, IPs) are gone

## Troubleshooting

### VM Not Deleted?

If cleanup fails, you'll see an error message. Common causes:
- Azure permissions issue
- VM already being deleted
- Network timeout

**Manual cleanup:**
```bash
# Use Azure CLI
az vm delete --name <vm-name> --resource-group <resource-group> --yes

# Or use the Python script
python -c "from hal.utils.azure_utils import VirtualMachineManager; vm = VirtualMachineManager(); vm.delete_vm('<vm-name>')"
```

### Test Fails Early?

Even if the test fails before completion, cleanup will still run because:
1. The `finally` block always executes
2. Exception handlers catch errors and trigger cleanup
3. Keyboard interrupt handler catches Ctrl+C

## Expected Output

```
================================================================================
VM Environment Prep Test
================================================================================
No VM name provided - creating a new VM for testing...
Creating VM: test-env-prep-abc12345
This may take 2-5 minutes...
✓ VM test-env-prep-abc12345 created successfully
VM created: test-env-prep-abc12345
Username: agent
Cleanup VM: Yes (VM will be destroyed)

[... test runs ...]

================================================================================
Cleaning up VM...
================================================================================
✓ VM test-env-prep-abc12345 and associated resources deleted successfully
```

## Time Estimates

- VM creation: 2-5 minutes
- VM setup (conda, packages): 3-10 minutes
- Environment prep test: 1-3 minutes
- **Total: ~6-18 minutes**

The VM will be destroyed automatically at the end, regardless of success or failure.

