/**
 * @name yuleOSH C/C++ Buffer Overflow Detection
 * @description 检测嵌入式 C 代码中的缓冲区溢出风险
 * @kind problem
 * @id yuleosh/cpp/buffer-overflow
 * @security-severity 9.0
 * @precision high
 * @tags security
 *   external/cwe/cwe-121
 *   external/cwe/cwe-120
 *   automotive
 */

import cpp

/**
 * 不安全的字符串操作函数
 */
from FunctionCall call
where
  call.getTarget().getName() in [
    "strcpy", "strcat", "sprintf", "vsprintf",
    "gets", "scanf", "sscanf"
  ]
select call,
  "不安全函数 " + call.getTarget().getName() + "() — 无边界检查，" +
  "存在缓冲区溢出风险。使用 snprintf/strncpy/fgets 替代。"
