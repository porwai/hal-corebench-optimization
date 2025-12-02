#!/usr/bin/env bash
set -euo pipefail

########################################
# 1) CORE-Agent-Optimized (Claude Sonnet 4.5)
########################################
WANDB_PROJECT=CORE-Agent-Optimized-Claude-Sonnet-4.5 hal-eval --benchmark corebench_hard \
  --agent_dir agents/core_agent_optimized \
  --agent_function main.run \
  --agent_name "CORE-Agent-Optimized (Claude Sonnet 4.5)" \
  -A model_name="anthropic/claude-sonnet-4-5" \
  --vm \
  --max_concurrent 45 \
  --upload &

########################################
# 2) CORE-Agent-Optimized (Claude Sonnet 4)
########################################
WANDB_PROJECT=CORE-Agent-Optimized-claude-sonnet-4 hal-eval --benchmark corebench_hard \
  --agent_dir agents/core_agent_optimized \
  --agent_function main.run \
  --agent_name "CORE-Agent-Optimized (Claude Sonnet 4)" \
  -A model_name="anthropic/claude-sonnet-4-20250514" \
  --vm \
  --max_concurrent 45 \
  --upload &

########################################
# 3) CORE-Agent-Optimized (GPT-5 Medium)
########################################
WANDB_PROJECT=CORE-Agent-Optimized-gpt-5-medium hal-eval --benchmark corebench_hard \
  --agent_dir agents/core_agent_optimized \
  --agent_function main.run \
  --agent_name "CORE-Agent-Optimized (GPT-5 Medium)" \
  -A model_name="openai/gpt-5-2025-08-07" \
  -A reasoning_effort="medium" \
  --vm \
  --max_concurrent 45 \
  --upload &

########################################
# 4) CORE-Agent-Optimized (Claude Sonnet 3.7)
########################################
WANDB_PROJECT=CORE-Agent-Optimized-Claude-Sonnet-3.7 hal-eval --benchmark corebench_hard \
  --agent_dir agents/core_agent_optimized \
  --agent_function main.run \
  --agent_name "CORE-Agent-Optimized (Claude Sonnet 3.7)" \
  -A model_name="anthropic/claude-3.7-sonnet" \
  --vm \
  --max_concurrent 45 \
  --upload &

########################################
# 5) CORE-Agent-Optimized (Claude Opus 4.1)
########################################
WANDB_PROJECT=CORE-Agent-Optimized-Claude-Opus-4.1 hal-eval --benchmark corebench_hard \
  --agent_dir agents/core_agent_optimized \
  --agent_function main.run \
  --agent_name "CORE-Agent-Optimized (Claude Opus 4.1)" \
  -A model_name="anthropic/claude-opus-4-1-20250805" \
  --vm \
  --max_concurrent 45 \
  --upload &

########################################
# 6) CORE-Agent-Optimized (Claude Opus 4.5)
########################################
WANDB_PROJECT=CORE-Agent-Optimized-Claude-Opus-4.5 hal-eval --benchmark corebench_hard \
  --agent_dir agents/core_agent_optimized \
  --agent_function main.run \
  --agent_name "CORE-Agent-Optimized (Claude Opus 4.5)" \
  -A model_name="anthropic/claude-opus-4-5-20251101" \
  --vm \
  --max_concurrent 45 \
  --upload &

wait


