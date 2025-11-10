#!/bin/bash
# Script to test prepare_environment_minimal_plus on a VM via SSH
# 
# Usage:
#   ./test_env_on_vm.sh <vm_name> [username]
#
# Example:
#   ./test_env_on_vm.sh agent-corebench-hard-abc123 agent

set -e

VM_NAME="${1}"
USERNAME="${2:-agent}"
SSH_KEY_PATH="${SSH_PRIVATE_KEY_PATH:-~/.ssh/id_rsa}"

if [ -z "$VM_NAME" ]; then
    echo "Usage: $0 <vm_name> [username]"
    echo "Example: $0 agent-corebench-hard-abc123 agent"
    exit 1
fi

if [ ! -f "$SSH_KEY_PATH" ]; then
    echo "ERROR: SSH private key not found at $SSH_KEY_PATH"
    echo "Set SSH_PRIVATE_KEY_PATH environment variable or ensure key exists"
    exit 1
fi

echo "Testing prepare_environment_minimal_plus on VM: $VM_NAME"
echo "Username: $USERNAME"
echo "SSH Key: $SSH_KEY_PATH"
echo ""

# Get VM IP (you'll need to implement this or pass IP as argument)
# For now, we'll assume you can SSH directly or provide IP
if [ -z "$VM_IP" ]; then
    echo "Please set VM_IP environment variable or modify this script to get IP from Azure"
    echo "Example: export VM_IP=20.123.45.67"
    exit 1
fi

echo "Connecting to $VM_IP..."
echo ""

# Copy test script to VM
echo "Copying test script to VM..."
scp -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no \
    test_env_prep.py \
    "${USERNAME}@${VM_IP}:/home/${USERNAME}/test_env_prep.py"

# Copy main.py and dependencies to VM (if not already there)
echo "Copying agent files to VM..."
scp -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no \
    main.py \
    "${USERNAME}@${VM_IP}:/home/${USERNAME}/main.py" || echo "Note: main.py might already exist"

# Run the test script
echo ""
echo "Running test script on VM..."
echo "=" 
ssh -i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no \
    "${USERNAME}@${VM_IP}" \
    "cd /home/${USERNAME} && python3 test_env_prep.py"

echo ""
echo "Test completed!"
echo ""
echo "To download the report file:"
echo "  scp -i $SSH_KEY_PATH ${USERNAME}@${VM_IP}:/home/${USERNAME}/env_prep_test_report.json ."

