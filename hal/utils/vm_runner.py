import os
import json
import asyncio
import time
import tempfile
import shutil
import uuid
from typing import Dict, Any, Optional, List
from .azure_utils import VirtualMachineManager
from ..benchmarks.base_benchmark import BaseBenchmark
import traceback
from rich.progress import Progress, TaskID

class VMRunner:
    """Handles running agents on Azure VMs"""
    
    def __init__(self, log_dir: str, max_concurrent: int = 1, benchmark: Optional[BaseBenchmark] = None):
        self.max_concurrent = max_concurrent
        self.log_dir = log_dir
        self.vm_manager = VirtualMachineManager()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._file_lock = asyncio.Lock()
        self._active_vms: List[str] = []
        self.benchmark = benchmark
        
    async def fetch_agent_logs(self, vm_name, username, ssh_private_key_path, task_id):
        """Fetch the latest agent trace log from a VM and store it locally."""
        try:
            result = await asyncio.to_thread(
                self.vm_manager.get_agent_trace,
                vm_name=vm_name,
                username=username,
                ssh_private_key_path=ssh_private_key_path
            )
            
            if result and self.log_dir:
                trace_dir = os.path.join(self.log_dir, "agent_logs")
                os.makedirs(trace_dir, exist_ok=True)
                
                # Write/update the trace file
                trace_path = os.path.join(trace_dir, f"{task_id}_log.log")
                with open(trace_path, "w") as f:
                    f.write(result)
                
                # Also write to a combined trace file
                combined_path = os.path.join(trace_dir, "combined_logs.log")
                with open(combined_path, "a") as f:
                    f.write(f"\n=== {task_id} @ {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                    f.write(result)
                    f.write("\n")
                
        except Exception as e:
            print(f"Error fetching logs for {task_id}: {e}")

    async def run_agent(self,
                       dataset: Dict[str, Any],
                       agent_function: str, 
                       agent_dir: str,
                       agent_args: Dict[str, Any],
                       run_id: str,
                       benchmark: Optional[BaseBenchmark] = None,
                       progress: Optional[Progress] = None,
                       task: Optional[TaskID] = None,
                       timeout: int = 7200) -> Dict[str, Any]:
        """Run agent on all tasks using Azure VMs"""
        self.benchmark = benchmark
        results = {}
        vm_names = []
        
        async def process_task(task_id: str, input_data: Any) -> Optional[Dict]:
            # Create unique VM name
            vm_name = f"agent-{benchmark.benchmark_name}-{uuid.uuid4()}"[:32].lower().replace("_", "-")
            vm_names.append(vm_name)
            
            try:
                # Check if the task requires GPU
                gpu_required = False
                if self.benchmark and hasattr(self.benchmark, 'benchmark'):
                    task_benchmark = self.benchmark.benchmark.get(task_id, {})
                    gpu_required = task_benchmark.get('gpu', False)
                
                # Create VM based on GPU requirement
                print(f"Creating {'GPU ' if gpu_required else ''}VM {vm_name} for task {task_id}")
                if gpu_required:
                    vm = await asyncio.to_thread(
                        self.vm_manager.create_gpu_vm,
                        vm_name=vm_name,
                        username="agent",
                        ssh_public_key_path=os.getenv("SSH_PUBLIC_KEY_PATH"),
                        network_security_group_name=os.getenv("NETWORK_SECURITY_GROUP_NAME")
                    )
                else:
                    vm = await asyncio.to_thread(
                        self.vm_manager.create_vm,
                        vm_name=vm_name,
                        username="agent",
                        ssh_public_key_path=os.getenv("SSH_PUBLIC_KEY_PATH"),
                        network_security_group_name=os.getenv("NETWORK_SECURITY_GROUP_NAME")
                    )

                # Create temp directory with all necessary files
                temp_dir = tempfile.mkdtemp()
                try:
                    # Create input and args files
                    input_file = os.path.join(temp_dir, 'input.json')
                    args_file = os.path.join(temp_dir, 'agent_args.json')
                    
                    with open(input_file, 'w') as f:
                        json.dump({task_id: input_data}, f)
                    with open(args_file, 'w') as f:
                        json.dump(agent_args, f)

                    # Copy task-specific files if they exist in input_data
                    if isinstance(input_data, dict) and 'files' in input_data:
                        for dest_path, src_path in input_data['files'].items():
                            # Remove 'root' prefix and leading slash if present
                            dest_path = dest_path.replace('/root/', '').lstrip('/')
                            
                            # Create destination directory structure in temp_dir
                            dest_full_path = os.path.join(temp_dir, dest_path)
                            os.makedirs(os.path.dirname(dest_full_path), exist_ok=True)
                            
                            # Copy the file
                            try:
                                if os.path.isdir(src_path):
                                    shutil.copytree(src_path, dest_full_path, dirs_exist_ok=True)
                                else:
                                    shutil.copy2(src_path, dest_full_path)
                            except Exception as e:
                                print(f"Warning: Failed to copy task file {src_path} to {dest_full_path}: {e}")

                    # Copy setup script if it exists
                    if self.benchmark and self.benchmark.setup_script:
                        setup_script_src = os.path.join(self.benchmark.setup_script)
                        if os.path.exists(setup_script_src):
                            setup_script_dest = os.path.join(temp_dir, 'setup_script.sh')
                            shutil.copy2(setup_script_src, setup_script_dest)
                            os.chmod(setup_script_dest, 0o755)

                    # Copy all files to VM
                    print(f"Copying files to VM {vm_name}")
                    await asyncio.to_thread(
                        self.vm_manager.copy_files_to_vm,
                        source_directory=temp_dir,
                        vm_name=vm_name,
                        username="agent", 
                        ssh_private_key_path=os.getenv("SSH_PRIVATE_KEY_PATH")
                    )
                    await asyncio.to_thread(
                        self.vm_manager.copy_files_to_vm,
                        source_directory=agent_dir,
                        vm_name=vm_name,
                        username="agent",
                        ssh_private_key_path=os.getenv("SSH_PRIVATE_KEY_PATH")
                    )

                finally:
                    shutil.rmtree(temp_dir)

                # Run agent on VM
                await asyncio.to_thread(
                    self.vm_manager.run_agent_on_vm,
                    agent_function=agent_function,
                    vm_name=vm_name,
                    task_id=task_id,
                    input_data=input_data,
                    agent_args=agent_args,
                    agent_dir="/home/agent",
                    run_id=run_id,
                    username="agent",
                    log_dir=self.log_dir,
                    ssh_private_key_path=os.getenv("SSH_PRIVATE_KEY_PATH"),
                    benchmark=benchmark
                )

                # Wait for completion or timeout
                start_time = time.time()
                result = None
                
                while time.time() - start_time < timeout:
                    try:
                        print(f"Checking task completion on VM {vm_name}")
                        # Fetch and store trace logs
                        await self.fetch_agent_logs(
                            vm_name=vm_name,
                            username="agent",
                            ssh_private_key_path=os.getenv("SSH_PRIVATE_KEY_PATH"),
                            task_id=task_id,
                        )
                        
                        result = await asyncio.to_thread(
                            self.vm_manager.check_task_completion,
                            vm_name=vm_name,
                            username="agent",
                            ssh_private_key_path=os.getenv("SSH_PRIVATE_KEY_PATH")
                        )
                        if result is not None:
                            print(f"Task {task_id} completed on VM {vm_name}")
                            break
                    except Exception as e:
                        print(f"Error checking task completion on {vm_name}: {e}")
                    await asyncio.sleep(30)  # Check every 30 seconds

                if result is None:
                    print(f"Task {task_id} timed out after {timeout} seconds")
                    result_dict = {task_id: f"TIMEOUT after {timeout} seconds"}
                    # Write timeout to submissions file immediately (crash-safe)
                    if self.log_dir:
                        raw_submissions_path = os.path.join(self.log_dir, f"{run_id}_RAW_SUBMISSIONS.jsonl")
                        async with self._file_lock:
                            await asyncio.to_thread(
                                self._append_to_submissions_file,
                                raw_submissions_path,
                                result_dict
                            )
                    return result_dict

                # Copy results back
                if self.log_dir:
                    try:
                        print(f"Copying results from VM {vm_name} to local directory")
                        dest_dir = os.path.join(self.log_dir, f"{task_id}")
                        os.makedirs(dest_dir, exist_ok=True)
                        await asyncio.to_thread(
                            self.vm_manager.copy_files_from_vm,
                            vm_name=vm_name,
                            username="agent",
                            ssh_private_key_path=os.getenv("SSH_PRIVATE_KEY_PATH"),
                            destination_directory=dest_dir
                        )
                    except Exception as copy_error:
                        # VM might have been deleted already, but result is still valid
                        print(f"Warning: Could not copy files from VM {vm_name}: {copy_error}")
                        print(f"Task {task_id} completed successfully, but log files could not be copied")
                    
                    # Write result to RAW_SUBMISSIONS.jsonl immediately (crash-safe)
                    # result from check_task_completion is already {task_id: response}, use it directly
                    # Check if result is already wrapped with task_id to avoid double wrapping
                    if isinstance(result, dict) and task_id in result and len(result) == 1:
                        # Already wrapped correctly, use as-is
                        result_dict = result
                    else:
                        # Not wrapped, wrap it
                        result_dict = {task_id: result}
                    raw_submissions_path = os.path.join(self.log_dir, f"{run_id}_RAW_SUBMISSIONS.jsonl")
                    async with self._file_lock:
                        await asyncio.to_thread(
                            self._append_to_submissions_file,
                            raw_submissions_path,
                            result_dict
                        )

                # Return in the same format as result_dict (already wrapped correctly)
                return result_dict

            except Exception as e:
                print(f"Error processing task {task_id} on VM {vm_name}: {e}")
                traceback.print_exc()
                error_result = {task_id: f"ERROR: {str(e)}"}
                # Write error to submissions file immediately (crash-safe)
                if self.log_dir:
                    raw_submissions_path = os.path.join(self.log_dir, f"{run_id}_RAW_SUBMISSIONS.jsonl")
                    try:
                        async with self._file_lock:
                            await asyncio.to_thread(
                                self._append_to_submissions_file,
                                raw_submissions_path,
                                error_result
                            )
                    except Exception as write_error:
                        print(f"Warning: Failed to write error result to submissions file: {write_error}")
                return error_result
            
            finally:
                # Cleanup VM
                try:
                    print(f"Deleting VM {vm_name}")
                    await asyncio.to_thread(self.vm_manager.delete_vm, vm_name)
                    if progress and task is not None:
                        progress.update(task, advance=1)
                except Exception as e:
                    print(f"Error deleting VM {vm_name}: {e}")

        # Run tasks in parallel with semaphore to limit concurrency
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def run_with_semaphore(task_id, input_data):
            async with semaphore:
                return await process_task(task_id, input_data)

        # Create tasks for all inputs
        tasks = [run_with_semaphore(task_id, input_data) 
                 for task_id, input_data in dataset.items()]
        
        # Run all tasks and gather results
        results = await asyncio.gather(*tasks)
        
        # Merge results
        merged_results = {}
        for result in results:
            if result:
                merged_results.update(result)

        # Note: Results are already written incrementally above, so we don't need to write again here
        # This ensures crash-safety - if the process crashes, completed tasks are already saved
        return merged_results
    
    def _append_to_submissions_file(self, file_path: str, result: Dict[str, Any]):
        """Thread-safe helper to append a result to RAW_SUBMISSIONS.jsonl"""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "a") as f:
            json.dump(result, f)
            f.write('\n')
            f.flush()  # Ensure data is written to disk immediately
            os.fsync(f.fileno())  # Force OS to write to disk (crash-safe)
