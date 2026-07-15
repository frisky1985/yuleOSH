/**
 * @name yuleOSH C/C++ Memory Safety
 * @description 嵌入式代码内存安全问题检测（double-free, use-after-free, null-deref）
 * @kind problem
 * @id yuleosh/cpp/memory-safety
 * @security-severity 8.5
 * @precision medium
 * @tags security
 *   external/cwe/cwe-415
 *   external/cwe/cwe-416
 *   external/cwe/cwe-476
 *   automotive
 */

import cpp

/**
 * 缺少 NULL 检查的 malloc
 */
from FunctionCall call
where
  call.getTarget().getName() = "malloc" and
  not exists(IfStmt ifStmt |
    ifStmt.getCondition().getAChild*() = call and
    ifStmt.getCondition().toString() = call.toString() + " == NULL" or
    ifStmt.getCondition().toString() = "!" + call.toString()
  )
select call,
  "malloc() 缺少 NULL 返回值检查，可能导致空指针解引用"
