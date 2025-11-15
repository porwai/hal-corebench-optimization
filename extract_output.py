import json
import os
from pathlib import Path

results_dir = Path("results/corebench_hard/corebench_hard_r_optimized_gpt5medium_all45")
submissions_file = results_dir / "corebench_hard_r_optimized_gpt5medium_all45_RAW_SUBMISSIONS.jsonl"

with open(submissions_file, 'w') as f:
    for capsule_dir in sorted(results_dir.glob("capsule-*/")):
        task_id = capsule_dir.name
        output_file = capsule_dir / "output.json"
        if output_file.exists():
            with open(output_file, 'r') as of:
                content = json.load(of)
                # Extract the inner dictionary - output.json has {task_id: {answers}}
                # We need just {answers}
                if task_id in content:
                    answers = content[task_id]
                else:
                    # Fallback: if structure is different, use the whole content
                    answers = content
            json.dump({task_id: answers}, f)
            f.write('\n')
            print(f"Added {task_id}")

print(f"\nCreated {submissions_file}")