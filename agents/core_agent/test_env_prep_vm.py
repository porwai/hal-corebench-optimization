#!/usr/bin/env python3
"""
Test prepare_environment_minimal_plus on an Azure VM.

This script connects to an EXISTING VM, runs the test, and shows the results.
Optionally destroys the VM after testing.

Usage:
    python test_env_prep_vm.py --vm-name VM_NAME [--username USERNAME] [--ssh-key PATH] [--cleanup]

Options:
    --cleanup    Destroy the VM after the test completes (default: False)
"""

import os
import sys
import argparse
import tempfile
import shutil
import uuid
import time
from pathlib import Path

# Find repo root (where .env file should be)
# Script can be run from repo root or from agents/core_agent directory
script_dir = Path(__file__).parent
repo_root = script_dir.parent.parent  # Go up from agents/core_agent to repo root

# Load .env file from repo root
try:
    from dotenv import load_dotenv
    env_path = repo_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded .env file from: {env_path}")
    else:
        print(f"Warning: .env file not found at {env_path}")
        print("Make sure your .env file is in the repo root directory")
except ImportError:
    print("Warning: python-dotenv not installed. Install with: pip install python-dotenv")
    print("Environment variables must be set manually or via export")

# Add hal to path
sys.path.insert(0, str(repo_root))

try:
    from hal.utils.azure_utils import VirtualMachineManager
    import paramiko
except ImportError as e:
    print(f"ERROR: Failed to import required modules: {e}")
    print("Make sure you have:")
    print("  1. Set up Azure credentials (AZURE_SUBSCRIPTION_ID, etc.) in .env file")
    print("  2. Installed required packages: pip install -e .[azure]")
    sys.exit(1)


def get_vm_ip(vm_manager, vm_name):
    """Get the public IP address of a VM."""
    try:
        public_ip = vm_manager.network_client.public_ip_addresses.get(
            vm_manager.resource_group_name, f"{vm_name}-public-ip"
        )
        return public_ip.ip_address
    except Exception as e:
        print(f"Warning: Could not get VM IP: {e}")
        return None


def wait_for_vm_ready(vm_ip, username, ssh_private_key, max_attempts=30, delay=10):
    """Wait for VM to be ready for SSH connections."""
    print(f"Waiting for VM to be ready (this may take a few minutes)...")
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    for attempt in range(max_attempts):
        try:
            ssh_client.connect(hostname=vm_ip, username=username, pkey=ssh_private_key, timeout=10)
            print(f"✓ VM is ready after {attempt * delay} seconds")
            return ssh_client  # Return the connected client
        except Exception as e:
            if attempt < max_attempts - 1:
                print(f"  Attempt {attempt + 1}/{max_attempts}: VM not ready yet, waiting {delay}s...")
                time.sleep(delay)
            else:
                print(f"✗ VM did not become ready after {max_attempts * delay} seconds")
                ssh_client.close()
                return None
    return None


def create_test_vm(vm_manager, username="agent"):
    """Create a VM for testing."""
    # Generate a unique VM name
    vm_name = f"test-env-prep-{uuid.uuid4().hex[:8]}"
    
    print(f"Creating VM: {vm_name}")
    print("This may take 2-5 minutes...")
    
    # Get required environment variables
    ssh_public_key_path = os.getenv("SSH_PUBLIC_KEY_PATH")
    if not ssh_public_key_path:
        print("ERROR: SSH_PUBLIC_KEY_PATH not set")
        return None
    
    network_security_group_name = os.getenv("NETWORK_SECURITY_GROUP_NAME")
    if not network_security_group_name:
        print("ERROR: NETWORK_SECURITY_GROUP_NAME not set")
        return None
    
    try:
        # Create the VM
        vm = vm_manager.create_vm(
            vm_name=vm_name,
            username=username,
            ssh_public_key_path=ssh_public_key_path,
            network_security_group_name=network_security_group_name,
            vm_size="Standard_E2as_v5"  # Standard size for testing
        )
        print(f"✓ VM {vm_name} created successfully")
        return vm_name
    except Exception as e:
        print(f"✗ Failed to create VM: {e}")
        import traceback
        traceback.print_exc()
        return None


def run_test_on_vm(vm_name, username="agent", ssh_private_key_path=None, cleanup=False, vm_created=False):
    """Run the environment prep test on a VM.
    
    Args:
        vm_name: Name of the VM to test on
        username: SSH username
        ssh_private_key_path: Path to SSH private key
        cleanup: If True, destroy the VM after testing
        vm_created: If True, this VM was just created and we should wait for it to be ready
    """
    if ssh_private_key_path is None:
        ssh_private_key_path = os.getenv("SSH_PRIVATE_KEY_PATH")
        if not ssh_private_key_path:
            print("ERROR: SSH_PRIVATE_KEY_PATH not set")
            return None
    
    vm_manager = VirtualMachineManager()
    vm_ip = get_vm_ip(vm_manager, vm_name)
    
    if not vm_ip:
        print(f"ERROR: Could not get IP for VM {vm_name}")
        return None
    
    print(f"VM IP: {vm_ip}")
    
    # Load SSH private key
    ssh_private_key = paramiko.RSAKey.from_private_key_file(ssh_private_key_path)
    
    # If VM was just created, wait for it to be ready and set it up
    if vm_created:
        print(f"Connecting to newly created VM {vm_name}...")
        ssh_client = wait_for_vm_ready(vm_ip, username, ssh_private_key, max_attempts=30, delay=10)
        if not ssh_client:
            print("ERROR: VM did not become ready in time")
            return None
        
        # Step 1: Copy agent files to VM (setup_vm.sh needs requirements.txt)
        # Use script_dir which is always agents/core_agent, regardless of where script is run from
        agent_dir = script_dir
        print("=" * 80)
        print("Step 1: Copying agent files to VM")
        print("=" * 80)
        print(f"Copying agent directory from: {agent_dir}")
        print("(including requirements.txt) to VM...")
        try:
            vm_manager.copy_files_to_vm(
                source_directory=str(agent_dir),
                vm_name=vm_name,
                username=username,
                ssh_private_key_path=ssh_private_key_path
            )
            print("✓ Agent files copied")
        except Exception as e:
            print(f"✗ Failed to copy agent files: {e}")
            return None
        
        # Step 2: General VM setup (setup_vm.sh) - installs conda, Python environment, etc.
        # This is the same setup used for ALL benchmarks
        print()
        print("=" * 80)
        print("Step 2: General VM Setup (setup_vm.sh)")
        print("=" * 80)
        print("This installs Miniconda, creates conda environment, and installs Python packages.")
        print("This is the same setup used for all benchmarks.")
        try:
            # Create a temp directory for logs
            import tempfile
            temp_log_dir = tempfile.mkdtemp(prefix="vm_test_")
            
            vm_manager.setup_vm_environment(
                vm_name=vm_name,
                username=username,
                ssh_private_key_path=ssh_private_key_path,
                agent_dir=str(agent_dir),  # Already copied above, but needed for logging
                log_dir=temp_log_dir,
                benchmark=None,  # Not needed for general setup
                task_id="test"
            )
            print("✓ General VM setup (setup_vm.sh) completed")
            # Clean up temp log dir
            shutil.rmtree(temp_log_dir, ignore_errors=True)
        except Exception as e:
            print(f"✗ General VM setup failed: {e}")
            print("This is required - cannot continue without conda environment")
            return None
        
        # Reconnect after setup (setup may have restarted services)
        ssh_client.close()
        time.sleep(5)  # Brief wait for services to stabilize
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh_client.connect(hostname=vm_ip, username=username, pkey=ssh_private_key, timeout=30)
        except Exception as e:
            print(f"Warning: Reconnection after setup failed: {e}")
            # Continue anyway - might still work
        
        print()
        print("=" * 80)
        print("Step 3: CORE-bench Specific Setup (prepare_environment_minimal_plus)")
        print("=" * 80)
        print("This will test the CORE-bench specific environment preparation:")
        print("  - Installing R, LaTeX, graphics libraries")
        print("  - Setting up symlinks (/data, /code, /results)")
        print("  - Configuring R profile")
        print("  - Installing R packages")
        print("This is ONLY for CORE-bench, not used by other benchmarks.")
        print()
    else:
        # Try to connect (VM should already be ready)
        print(f"Connecting to existing VM {vm_name}...")
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh_client.connect(hostname=vm_ip, username=username, pkey=ssh_private_key, timeout=30)
        except Exception as e:
            print(f"ERROR: Failed to connect to VM: {e}")
            return None
    
    # Create SFTP client
    sftp_client = ssh_client.open_sftp()
    
    try:
        # Copy test script
        # Use script_dir which is always agents/core_agent, regardless of where script is run from
        agent_dir = script_dir
        test_script = agent_dir / "test_env_prep.py"
        main_script = agent_dir / "main.py"
        
        print("Copying test files to VM...")
        sftp_client.put(str(test_script), f"/home/{username}/test_env_prep.py")
        sftp_client.put(str(main_script), f"/home/{username}/main.py")
        
        # Make test script executable
        ssh_client.exec_command(f"chmod +x /home/{username}/test_env_prep.py")
        
        # Run the test in the conda environment (where all packages are installed)
        print("Running test on VM (in conda environment)...")
        print("=" * 80)
        # Use conda run to execute in the agent_env environment (works in non-interactive shells)
        # Use bash -c to ensure proper shell execution and command chaining
        stdin, stdout, stderr = ssh_client.exec_command(
            f"bash -c 'cd /home/{username} && "
            f"source /home/{username}/init_conda.sh && "
            f"/home/{username}/miniconda3/bin/conda run -n agent_env python test_env_prep.py'"
        )
        
        # Print output in real-time
        output_lines = []
        for line in stdout:
            print(line.rstrip())
            output_lines.append(line)
        
        # Check for errors
        error_output = stderr.read().decode()
        if error_output:
            print("\nSTDERR:")
            print(error_output)
        
        exit_status = stdout.channel.recv_exit_status()
        
        print("=" * 80)
        print(f"\nTest completed with exit status: {exit_status}")
        
        # Try to download the report
        try:
            report_remote = f"/home/{username}/env_prep_test_report.json"
            report_local = f"env_prep_test_report_{vm_name}.json"
            sftp_client.get(report_remote, report_local)
            print(f"Report downloaded to: {report_local}")
        except Exception as e:
            print(f"Note: Could not download report: {e}")
        
        return {
            "exit_status": exit_status,
            "output": "".join(output_lines),
            "errors": error_output
        }
        
    finally:
        sftp_client.close()
        ssh_client.close()
        
        # Cleanup VM if requested (after closing SSH connections)
        if cleanup:
            try:
                print("\n" + "=" * 80)
                print("Cleaning up VM...")
                print("=" * 80)
                vm_manager.delete_vm(vm_name)
                print(f"✓ VM {vm_name} and associated resources deleted successfully")
            except Exception as e:
                print(f"✗ Error deleting VM {vm_name}: {e}")
                import traceback
                traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(
        description="Test prepare_environment_minimal_plus on a VM",
        epilog="""
If --vm-name is not provided, a new VM will be created automatically and destroyed after testing.
If --vm-name is provided, an existing VM will be used. Use --cleanup to destroy it after testing.
        """
    )
    parser.add_argument("--vm-name", help="Name of an EXISTING VM to test on (if not provided, a new VM will be created)")
    parser.add_argument("--username", default="agent", help="SSH username (default: agent)")
    parser.add_argument("--ssh-key", help="Path to SSH private key (default: from SSH_PRIVATE_KEY_PATH env var)")
    parser.add_argument("--cleanup", action="store_true", help="Destroy the VM after the test completes (always True if VM is auto-created)")
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("VM Environment Prep Test")
    print("=" * 80)
    
    vm_manager = VirtualMachineManager()
    vm_name = args.vm_name
    vm_created = False
    
    # Create VM if not provided
    if not vm_name:
        print("No VM name provided - creating a new VM for testing...")
        vm_name = create_test_vm(vm_manager, username=args.username)
        if not vm_name:
            print("Failed to create VM")
            return 1
        vm_created = True
        cleanup = True  # Always cleanup if we created it
        print(f"VM created: {vm_name}")
    else:
        cleanup = args.cleanup
        print(f"Using existing VM: {vm_name}")
    
    print(f"Username: {args.username}")
    print(f"Cleanup VM: {'Yes (VM will be destroyed)' if cleanup else 'No (VM will remain)'}")
    print()
    
    # Safety: ensure cleanup happens even if test fails early
    try:
        result = run_test_on_vm(
            vm_name,
            username=args.username,
            ssh_private_key_path=args.ssh_key,
            cleanup=cleanup,
            vm_created=vm_created
        )
        
        if result:
            if result["exit_status"] == 0:
                print("\n✓ Test completed successfully!")
                return 0
            else:
                print("\n✗ Test completed with errors")
                return 1
        else:
            print("\n✗ Failed to run test")
            return 1
    except KeyboardInterrupt:
        print("\n\n⚠ Test interrupted by user")
        if cleanup:
            print("Cleaning up VM due to interruption...")
            try:
                vm_manager.delete_vm(vm_name)
                print(f"✓ VM {vm_name} deleted")
            except Exception as e:
                print(f"✗ Error deleting VM: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        if cleanup:
            print("Cleaning up VM due to error...")
            try:
                vm_manager.delete_vm(vm_name)
                print(f"✓ VM {vm_name} deleted")
            except Exception as cleanup_error:
                print(f"✗ Error deleting VM: {cleanup_error}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

