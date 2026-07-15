/**
 * @name yuleOSH Sensitive Data Leak Detection
 * @description 检测敏感信息（密钥、密码）泄漏到日志或输出的路径
 * @kind path-problem
 * @id yuleosh/python/sensitive-leak
 * @security-severity 7.5
 * @precision high
 * @tags security
 *   external/cwe/cwe-532
 */

import python
import semmle.python.dataflow.new.DataFlow
import semmle.python.dataflow.new.TaintTracking

/**
 * 敏感信息源：环境变量、配置、API密钥变量
 */
class SensitiveSource extends DataFlow::Node {
  SensitiveSource() {
    exists(string varName |
      this.(DataFlow::LocalSourceNode).asExpr().(Name).getId().regexpMatch("(?i).*(secret|token|password|api_key|apikey|credential|private_key).*")
    )
    or
    this.(DataFlow::CallNode).getFunction().(DataFlow::ValueNode).asExpr().(Name).getId() = "getenv" or
    (
      this.(DataFlow::CallNode).getFunction().(DataFlow::ValueNode).asExpr().(Name).getId() = "get" and
      this.(DataFlow::CallNode).getArg(0).(DataFlow::ExprNode).asExpr().(StrConst).getText().regexpMatch("(?i).*(secret|token|password|key).*")
    )
  }
}

/**
 * 泄露汇点：日志输出
 */
class LeakSink extends DataFlow::Node {
  LeakSink() {
    exists(CallNode call |
      call.(FunctionCall).getFunc().(Name).getId() in ["print", "log"] or
      call.(FunctionCall).getFunc().(Attribute).getId() in [
        "logging.info", "logging.debug", "logging.warning",
        "logger.info", "logger.debug",
        "app.logger.info", "app.logger.debug"
      ] and
      this = call.getArg(0)
    )
  }
}

class SensitiveLeakConfig extends TaintTracking::Configuration {
  SensitiveLeakConfig() { this = "SensitiveLeakConfig" }

  override predicate isSource(DataFlow::Node source) {
    source instanceof SensitiveSource
  }

  override predicate isSink(DataFlow::Node sink) {
    sink instanceof LeakSink
  }
}

from DataFlow::PathNode source, DataFlow::PathNode sink, SensitiveLeakConfig config
where config.hasFlowPath(source, sink)
select sink.getNode(), source, sink,
  "敏感数据泄漏路径：" + source.toString() + " → " + sink.toString()
