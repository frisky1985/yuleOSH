#!/usr/bin/env bash
# OSH Platform CLI — 嵌入式开发全流程平台
set -euo pipefail

cmd_spec_validate() {
  local file="$1"
  if [ ! -f "$file" ]; then
    echo "❌ File not found: $file"
    exit 1
  fi
  echo "📋 Validating spec: $file"
  python3 -m yuleosh.spec.validate "$file"
}

cmd_spec_diff() {
  local old="$1" new="$2"
  python3 -m yuleosh.spec.diff "$old" "$new"
}

cmd_pipeline_run() {
  local spec="$1"
  echo "🚀 Running pipeline with spec: $spec"
  python3 -m yuleosh.pipeline.run "$spec"
}

cmd_pipeline_status() {
  python3 -m yuleosh.pipeline.run status "${1:-}"
}

cmd_review_auto() {
  echo "🔍 Running auto-review"
  python3 -m yuleosh.review.run auto
}

cmd_review_task() {
  local task="$1" kind="${2:-feature}"
  echo "🔍 Reviewing task: $task [$kind]"
  python3 -m yuleosh.review.run task "$task" "$kind"
}

cmd_ci_run() {
  local layer="$1"
  echo "🔬 Running CI Layer $layer"
  python3 -m yuleosh.ci.run "$layer"
}

cmd_evidence_pack() {
  echo "📦 Generating compliance evidence pack"
  python3 -m yuleosh.evidence.pack
}

cmd_init() {
  local dir="${1:-.}"
  mkdir -p "$dir/specs" "$dir/tasks" "$dir/src" "$dir/docs" "$dir/evidence"
  echo "✅ Initialized OSH project at $dir"
}

cmd_template_init() {
  local project_name="$1"
  shift
  local from_flag=""
  if [ -z "$project_name" ]; then
    echo "❌ Usage: osh-cli template init <project-name> [--from <template-dir>]"
    exit 1
  fi
  if [ "$1" = "--from" ] && [ -n "$2" ]; then
    from_flag="--from $2"
    shift 2
  fi
  echo "📦 Creating new project from starter template: $project_name"
  python3 -m yuleosh.cli.template init "$project_name" $from_flag
}

cmd_stats() {
  local json_flag=""
  for arg in "$@"; do
    if [ "$arg" = "--json" ]; then
      json_flag="--json"
    fi
  done
  python3 -m yuleosh.cli.stats $json_flag
}

cmd_ui_start() {
  echo "🌐 Starting yuleOSH Dashboard..."
  python3 -m yuleosh.ui.server
}

_show_examples() {
  echo ""
  echo "📖 yuleOSH — Usage Examples"
  echo "══════════════════════════════════════════════"
  echo ""
  echo "🧰 Getting Started"
  echo "  osh-cli init my-project"
  echo "  cd my-project"
  echo ""
  echo "  osh-cli template init my-embedded-app"
  echo "  cd my-embedded-app"
  echo ""
  echo "📋 Spec Management"
  echo "  # Validate your requirements spec"
  echo "  osh-cli spec validate docs/spec.md"
  echo ""
  echo "  # Track requirement changes across versions"
  echo "  osh-cli spec diff docs/spec.md docs/spec-v2.md"
  echo ""
  echo "🚀 Agent Pipeline"
  echo "  # Full 9-step pipeline: 小明 → Hermes → Claude"
  echo "  osh-cli pipeline run docs/spec.md"
  echo ""
  echo "  # Check session status"
  echo "  osh-cli pipeline status"
  echo ""
  echo "🔬 CI/CD Pipeline"
  echo "  osh-cli ci run 1    # Dev Verification (unit tests, coverage)"
  echo "  osh-cli ci run 2    # Integration Verification (cross-compile, static analysis)"
  echo "  osh-cli ci run 3    # System Verification (E2E, evidence pack)"
  echo ""
  echo "📝 Code Review"
  echo "  osh-cli review auto                       # Auto-review changes"
  echo "  osh-cli review task add-temp-sensor feature  # Feature review (4 agents)"
  echo "  osh-cli review task fix-bug bugfix           # Quick bugfix review (2 agents)"
  echo ""
  echo "📦 Compliance"
  echo "  osh-cli evidence pack                     # ASPICE compliance pack"
  echo ""
  echo "🌐 Dashboard"
  echo "  osh-cli ui start                          # Launch http://localhost:8080"
  echo ""
  echo "📊 Statistics"
  echo "  osh-cli stats"
  echo "  osh-cli stats --json"
  echo ""
  echo "📌 End-to-End Workflow"
  echo "  1. osh-cli template init my-sensor-project"
  echo "  2. cd my-sensor-project && osh-cli spec validate docs/spec.md"
  echo "  3. osh-cli ci run 1"
  echo "  4. osh-cli pipeline run docs/spec.md"
  echo "  5. osh-cli review auto"
  echo "  6. osh-cli evidence pack"
  echo "  7. osh-cli ui start"
  echo ""
  echo "📖 Full docs: docs/USAGE.md"
  echo ""
}

case "${1:-help}" in
  init) cmd_init "${2:-}";;
  template)
    shift
    case "${1:-}" in
      init) shift; cmd_template_init "$@";;
      *) echo "Usage: osh-cli template init <project-name> [--from <template-dir>]"; exit 1;;
    esac
    ;;
  stats) shift; cmd_stats "$@";;
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
  ui) shift; cmd_ui_start "$@";;
  help|--help|-h)
    cmd="${2:-}"
    if [ "$cmd" = "--examples" ]; then
      _show_examples
    else
      echo "OSH Platform CLI — 嵌入式开发全流程平台"
      echo "Usage: osh-cli <command> [options]"
      echo ""
      echo "Commands:"
      echo "  init [dir]                    — Initialize project structure"
      echo "  template init <name>          — Create project from starter template"
      echo "  stats [--json]                — Show project statistics"
      echo "  spec validate <file>          — Validate OpenSpec (SHALL/SHOULD/MAY + GIVEN/WHEN/THEN)"
      echo "  spec diff <old> <new>         — Compare two OpenSpec files"
      echo "  pipeline run <spec>           — Run full 9-step Agent pipeline"
      echo "  pipeline status [name]        — Show pipeline session status"
      echo "  review auto                   — Auto-review all changed files"
      echo "  review task <name> [kind]     — Review specific task (feature|bugfix|refactor|docs|config)"
      echo "  ci run <layer>                — Run CI layer (1=Dev|2=Integration|3=System)"
      echo "  evidence pack                 — Generate ASPICE compliance evidence pack"
      echo "  ui start                      — Launch Dashboard at http://localhost:8080"
      echo "  help [--examples]             — Show this help, or usage examples"
      echo ""
      echo "Run 'osh-cli help --examples' for real usage examples."
    fi
    ;;
  --examples)
    _show_examples
    ;;
  *) echo "Unknown command: $1"
     echo "Run 'osh-cli help' for usage."
     exit 1;;
esac
