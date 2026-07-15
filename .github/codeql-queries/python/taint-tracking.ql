/**
 * @name yuleOSH Taint Tracking (Python)
 * @description 深度数据流分析：跟踪用户输入到敏感 sink
 * @kind path-problem
 * @id yuleosh/python/taint-tracking
 * @security-severity 8.0
 * @precision high
 * @tags security
 *   external/cwe/cwe-089
 *   external/cwe/cwe-078
 *   external/cwe/cwe-022
 */

import python
import semmle.python.dataflow.new.DataFlow
import semmle.python.dataflow.new.TaintTracking
import semmle.python.dataflow.new.RemoteFlowSources

/**
 * 自定义 taint 源：所有远程用户输入
 */
class UserInputSource extends RemoteFlowSource {
  UserInputSource() { this instanceof RemoteFlowSource }
  override string getSourceType() { result = "UserInput" }
}

/**
 * 自定义 taint 汇点（sink）
 */
class DangerousSink extends DataFlow::Node {
  DangerousSink() {
    // SQL 执行
    exists(CallNode call |
      call =
        any(FunctionCall fc |
          fc.getFunc().(Attribute).getName() = "execute" or
          fc.getFunc().(Attribute).getName() = "executemany" or
          fc.getFunc().(Attribute).getName() = "run"
        ) and
      this = call.getArg(0)
    )
    or
    // Shell 命令
    exists(CallNode call |
      call =
        any(FunctionCall fc |
          fc.getFunc().(Name).getId() = "system" or
          fc.getFunc().(Name).getId() = "popen" or
          fc.getFunc().(Attribute).getId() = "os.system" or
          fc.getFunc().(Attribute).getId() = "subprocess.call" or
          fc.getFunc().(Attribute).getId() = "subprocess.Popen" or
          fc.getFunc().(Attribute).getId() = "subprocess.run"
        ) and
      this = call.getArg(0)
    )
    or
    // 文件路径（路径遍历）
    exists(CallNode call |
      call.(FunctionCall).getFunc().(Name).getId() = "open" and
      this = call.getArg(0)
    )
    or
    // eval/exec
    exists(CallNode call |
      call.(FunctionCall).getFunc().(Name).getId() = "eval" or
      call.(FunctionCall).getFunc().(Name).getId() = "exec"
    )
  }
}

class UserInputTaintConfig extends TaintTracking::Configuration {
  UserInputTaintConfig() { this = "UserInputTaintConfig" }

  override predicate isSource(DataFlow::Node source) {
    source instanceof UserInputSource
  }

  override predicate isSink(DataFlow::Node sink) {
    sink instanceof DangerousSink
  }

  override predicate isSanitizer(DataFlow::Node node) {
    // 安全函数清洗
    exists(string sanitizerFunc |
      sanitizerFunc in [
        "sanitize_sql_input", "escape_string", "shlex.quote",
        "shlex.split", "os.path.basename", "os.path.normpath",
        "os.path.abspath", "os.path.realpath"
      ] and
      node.(DataFlow::CallNode).getFunction().(DataFlow::ValueNode).asExpr().(Name).getId() = sanitizerFunc
    )
  }
}

from DataFlow::PathNode source, DataFlow::PathNode sink, UserInputTaintConfig config
where config.hasFlowPath(source, sink)
select sink.getNode(), source, sink,
  "数据流路径检测：用户输入 " + source.toString() + " 流向危险 sink " + sink.toString()
