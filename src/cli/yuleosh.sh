#!/usr/bin/env bash
# OSH Platform CLI — 嵌入式开发全流程平台
set -euo pipefail

OSH_HOME="${OSH_HOME:-$(cd "$(dirname "$0")/../.." && pwd)}"

cmd_spec_validate() {
  local file="$1"
  if [ ! -f "$file" ]; then
    echo "❌ File not found: $file"
    exit 1
  fi
  echo "📋 Validating spec: $file"
  python3 "$OSH_HOME/src/spec/validate.py" "$file"
}

cmd_spec_diff() {
  local old="$1" new="$2"
  python3 "$OSH_HOME/src/spec/diff.py" "$old" "$new"
}

cmd_pipeline_run() {
  local spec="$1"
  echo "🚀 Running pipeline with spec: $spec"
  python3 "$OSH_HOME/src/pipeline/run.py" "$spec"
}

cmd_pipeline_status() {
  python3 "$OSH_HOME/src/pipeline/run.py" status "${1:-}"
}

cmd_review_auto() {
  echo "🔍 Running auto-review"
  python3 "$OSH_HOME/src/review/run.py" auto
}

cmd_review_task() {
  local task="$1" kind="${2:-feature}"
  echo "🔍 Reviewing task: $task [$kind]"
  python3 "$OSH_HOME/src/review/run.py" task "$task" "$kind"
}

cmd_ci_run() {
  local layer="$1"
  echo "🔬 Running CI Layer $layer"
  python3 "$OSH_HOME/src/ci/run.py" "$layer"
}

cmd_evidence_pack() {
  echo "📦 Generating compliance evidence pack"
  python3 "$OSH_HOME/src/evidence/pack.py"
}

cmd_init() {
  local dir="${1:-.}"
  mkdir -p "$dir/specs" "$dir/tasks" "$dir/src" "$dir/docs" "$dir/evidence"
  echo "✅ Initialized OSH project at $dir"
}

case "${1:-help}" in
  init) cmd_init "${2:-}";;
  spec)
    shift
    case "${1:-}" in
      validate) shift; cmd_spec_validate "$1";;
      diff) shift; cmd_spec_diff "$1" "$2";;
      *) echo "Usage: osh-cli spec validate|diff"; exit 1;;
    esac
    ;;
  pipeline)
    shift
    case "${1:-}" in
      run) shift; cmd_pipeline_run "$1";;
      status) shift; cmd_pipeline_status "$@";;
      *) echo "Usage: osh-cli pipeline run|status"; exit 1;;
    esac
    ;;
  review)
    shift
    case "${1:-}" in
      auto) cmd_review_auto;;
      task) shift; cmd_review_task "$1" "${2:-}";;
      *) echo "Usage: osh-cli review auto|task"; exit 1;;
    esac
    ;;
  ci)
    shift
    case "${1:-}" in
      run) shift; cmd_ci_run "$1";;
      *) echo "Usage: osh-cli ci run <layer>"; exit 1;;
    esac
    ;;
  evidence) shift; cmd_evidence_pack "$@";;
  help|--help|-h)
    echo "OSH Platform CLI"
    echo "Usage:"
    echo "  osh-cli init [dir]              — Initialize project"
    echo "  osh-cli spec validate <file>    — Validate OpenSpec"
    echo "  osh-cli spec diff <o> <n>       — Diff specs"
    echo "  osh-cli pipeline run <spec>     — Run full pipeline"
    echo "  osh-cli pipeline status         — Pipeline status"
    echo "  osh-cli review auto             — Auto-review changes"
    echo "  osh-cli review task <name> [kind] — Review specific task"
    echo "  osh-cli ci run <layer>          — Run CI layer (1/2/3)"
    echo "  osh-cli evidence pack           — Generate compliance pack"
    ;;
  *) echo "Unknown command: $1"; exit 1;;
esac
