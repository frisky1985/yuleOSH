# 发布计划（SPL.2）

## 发布范围

- 发布版本：`unversioned`。
- 发布会话：`run-20261110-233122`。
- 范围：本轮流水线产出的全部受控工作产物。

## 发布准则

- 所有硬门禁通过（`worst_gate_status = passed`）方可批准发布。
- 发布清单中的每个文件必须有 SHA256 摘要，摘要不符即拒绝发布。
- 未验证门禁（not-run / stale / skipped）不得被表述为已通过。
- 批准状态只能由人修改，流水线默认「待批准」。

## 发布清单

- 门禁快照：不可用，worst = `not-run`。
- 发布产物：66 个。

| 产物键 | 路径 | SHA256 |
|:---|:---|:---|
| acq1-preparation | docs/acquisition-plan.md | `fff49b6fde0c4173b39dc4ee40d2a648f87672678f596beeda2d4275b6525440` |
| acq2-review | docs/supplier-selection.md | `39cfaf2b1dfce1c50eb262556420283ade26f52bc3d867271f8fa214034ffa4d` |
| acq3-contract | docs/contract-agreement.md | `f02ff9971ec72eef8fbb91252e6dbde41f613da7db1a0bb5eaf5660e8f13ad47` |
| acq4-monitoring | docs/supplier-monitoring-report.md | `f56071a1b9a37c6842b5ce8f98fe8cb46ca10597a9ab71f6d22928c015ecd5f1` |
| arch-review | .osh/sessions/189cb171e97e/arch-review.json | `c89e8ffd0c2c78d4d0ff01f4db59da565ee848edc66a27a09efa61448a11029f` |
| architecture | .osh/sessions/189cb171e97e/architecture.md | `6335cbbc713eb3c337163734606bec74e4afdeec5688cddc17287c9eb960cead` |
| c-unit-test | .osh/sessions/189cb171e97e/c-unit-test.json | `9628a6889177b61cabc7638c384241d28c88a2025696c69a3e7970d41d0f6db8` |
| claude-review | .osh/sessions/189cb171e97e/claude-review.json | `03c41791346917b42c2caf52c29e0e8f442beebd58df5e74327b9a4c36dc275f` |
| code-review | .osh/sessions/189cb171e97e/code-review-unified.json | `5547d0700a7410cf6861837c31cdf6869577ab6b9bd6261a8bc680e710e9b06a` |
| codegen-deploy | .yuleosh/reports/codegen-deploy.json | `0251331603a94476ab84dc304f2930841e5b3f2eb8c6297a16760223d69ef074` |
| coverage-review | .osh/sessions/189cb171e97e/coverage-review.json | `58adc547da46dc874482ccca4229a910ed411cd2b62ffa7a09d806cebf6b03ce` |
| development | .osh/sessions/189cb171e97e/development-plan.md | `bd0f51a3a46d1f4a89d617723a75846985f61dee6d3efc82fa9b0d77d2f2323b` |
| development-review | .osh/sessions/189cb171e97e/development-review.json | `4f14b7b3dee74f7dbb9a511fa49d9fb155021290e41e909fd4b606d5826f477b` |
| fault-injection | .osh/sessions/189cb171e97e/fault-injection-report.md | `a72eaa33ec5e9414e4665aeac1607895ae8821739e6af5e43bd5e2903050b971` |
| hwe1-requirements | docs/hw-requirements.md | `7f9f1e88a44be8b01f5fad61f4ce909a1a45c533d8eeaeb2034b3ffae5798a92` |
| hwe2-design | docs/hw-design.md | `11b0f63d1e3f0ccb929300fdc09e28b83a3fa598f8f1fb12049210bb95916564` |
| hwe3-implementation | docs/hw-implementation-report.md | `131f5aa260ec27e1865e6b55dd0f87d3400e07097c79d66a622dbe95c23eca9a` |
| hwe4-review | docs/hw-verification-report.md | `3beae3364db13cbec9cc0d99226cf3a2d65b892ca2beb604bd282d5f5ad13dda` |
| integration-test | .osh/sessions/189cb171e97e/integration-test.json | `23a462c425a1a0e7e385d63fda8b7c8021951b4eadb0e32bb771222ced9559d7` |
| internal-code-review | .osh/sessions/189cb171e97e/internal-code-review.json | `af2c0d9f418e36e20a5eb1986c8e875dc06bfcf605028ecb0b0da0d7d6640110` |
| man1-charter | docs/project-charter.md | `27f0e84c5f8dec7d5dba81329f4ce49cddb85902f376b2abfdc10ec53f9a1aca` |
| man2-requirements | docs/requirements-baseline.md | `0e63b15ba051ef7a239f3a1618c0bf71b7fd8f202b723145c97d48a6b44ff571` |
| man3-project | docs/project-plan.md | `68e473e45483d35521c87df68371acbfd6b606ccd625af2f2c65381fcb5c760a` |
| man4-quality | docs/quality-management.md | `1941b8f47107fd15a6a27d3781d1ba0bbbe811e988e45d4f4727299c32b3dc93` |
| measurement | docs/measurement-report.md | `b446315e211cb47f5c00826664a7f0ad7479394c78d778ca45bb21ce28d0de24` |
| merge-gate | .osh/sessions/189cb171e97e/merge-gate-report.json | `7d293c969f6f97c00aec93f5546da946dbd63cdc1071fb952cc6cf51c3d3ee0d` |
| misra-review | .osh/sessions/189cb171e97e/misra-review.json | `2f3f19aa68580516cc64c4b7a52f1551de093730191c1e673c02d31d03d458e4` |
| mle1-requirements | docs/ml-requirements.md | `edcf23a0fd8f76b1ce18db3ad1e20007854defd8e88a38fb55538b1d5333d5b8` |
| mle2-approach | docs/ml-approach.md | `5dc89daf9ee5d97852b9ee49ce05160d690a88e5c515d1ddc2aa424eff2233fb` |
| mle3-review | docs/ml-training-report.md | `42c1c3e7b7539718498d7fa69859397e4163d7929b1ce5d9bac437dff695bc39` |
| mle4-evaluation | docs/ml-evaluation-report.md | `198dab074983e8ac9362e82ee0d87cdbf5039e04c581840d550fdfcc12b0eb2d` |
| pim1-establishment | docs/process-definition.md | `8b88c8376ec47034968d1c3896bef09f53b19a9ba30f17547387fd27e62cb683` |
| pim2-assessment | docs/process-assessment.md | `656b1714885d93adb6e390f1cea4583a73eae9896b798395750114c05e9c2698` |
| pim3-improvement | docs/process-improvement-report.md | `bf30b4ecdfc493b2452157522cd50666c75cd7226b7fe32ca4e468ed71183714` |
| prd | .osh/sessions/189cb171e97e/prd.md | `fadf3a188ed9d64c85058b5cc8a9c2756fe63f0b0f9c17587f158893232a731a` |
| prd-review | .osh/sessions/189cb171e97e/prd-review.json | `7512fdb27a7bdce3f01baa9b776e18b66057f50fc7b593a94f72a02160dec517` |
| qemu-verify | .osh/sessions/189cb171e97e/qemu-verify.json | `be274909e3b0ac8006483be79bbb6d0247541c72f9fc0d671031280cc03cb997` |
| reu1-assets | docs/reuse-asset-library.md | `257ce84650291088a4c98a8c17089af2b211dd243c7d74796b2634a1145dfa00` |
| reu2-reuse | docs/reuse-report.md | `a4c2d40f5faf127e5dfcd7868b862bd6a7616d98b58a42c6455dd7bd0c63ae90` |
| review-critical-safety | .osh/sessions/189cb171e97e/critical-safety-report.json | `06ce2dda699864856ad24a0084a3c1df435207c450831e872c14e00aa2b7acee` |
| risk-assessment | docs/risk-report.md | `ef9383ac4b73731e8179a94d4502f8742d6c235245e4e589d955e0cbca0779f3` |
| self-test | .osh/sessions/189cb171e97e/self-test-report.md | `e2e217c28e32fe7422cdb556b48547067d363ca441dbbfe4ee6a71cfbaeb6976` |
| spec-check | .osh/sessions/189cb171e97e/spec-check.json | `086237c853e91da9e51c66be3a07d7eb0fd985deda56c6b2a381c4ecd3a01de5` |
| spl1-review | docs/tender-plan.md | `1c9423b27bc3625127f7a9fbe2cae119e86d471acd58fdddcac3d51f363bc5c7` |
| sup1-quality | docs/qa-plan.md | `fccf0195d702c37253f57b4fdaee2f0b54f4822fb3df0cbaac7ce0dfa81597fb` |
| sup10-change | docs/change-requests.md | `5732d4ffd9d435bfd6e0e1fde0657f0eb24a55c7baec24ae964317121bcd5898` |
| sup2-review | docs/verification-plan.md | `384d3706e718277f75ecb7ac2e32810829c4f01b48550ab031286850ef8601a3` |
| sup3-review | docs/product-validation.md | `7a14d73d41a1226054437c849c3ecb4df6eae15449ace3cd914b6abf124ca87b` |
| sup4-joint-review | docs/joint-review-report.md | `d17f4ccfd0f3b1cf82f7f025826ed735eb7ec210bd0a3478b8a5604c9be733d5` |
| sup5-audit | docs/audit-report.md | `c035d51ad93c01e969a9e54b3ff34a6032981bb8229835fcac63f0030d813b21` |
| sup6-evaluation | docs/product-evaluation.md | `3b3151d2dfe3b9fa3e79c4fa09a265b22b57bf9b826d9cd6087367dae31a055f` |
| sup7-documentation | docs/documentation-plan.md | `09a0b44dd8a7a618cfad52716d5bced2e1792de0ef764310164fbf94ae1fe44f` |
| sup8-config | docs/configuration-management.md | `a06d789e4251899347531a6dd9aac2084ed21ea2b6b6be9214111ade0c760950` |
| sup9-problem | docs/known-issues.md | `a494e11bcca0eda612fb83f122ce0ce120091c556a14c625617ee98e18eada9e` |
| super-analysis | .osh/sessions/189cb171e97e/startup-analysis.md | `de1456d6d9b83c8ec3f0dbb096dd9f1bc28afdc5257601139fea4e6e2534ccc4` |
| sys-architecture | docs/system-architecture.md | `6c1eef2e751d03376ff48875f0b698da789f8c0587ac5e1b8d9dd677501b6c20` |
| sys-integration | docs/system-integration.md | `5563ed6f9b65931354702a24f0374cb0fb6ca07f57865139406c45ffc96f1950` |
| sys-req-review | .osh/evidence/sys-review.json | `aa9420377a78dba77a054c7b88d96112d6d3020fa63fdccd494107e0035e27a0` |
| sys-requirements | docs/system-requirements.md | `cfebf57deaa8b135867c57c155e0c40d918ad0009398b14082ac9bc874757cd5` |
| sys-validation | docs/system-validation.md | `8795741ba037d53a7ceba5162651824339d86e634e1dce811642dee833090a85` |
| sys-verification | docs/system-verification.md | `ac64ad0e858966e7ab532b3d28bd8aacf9a45e0d16d27de11d0e2d9fff7a4373` |
| sys_spec_alignment | .osh/sessions/189cb171e97e/sys-spec-alignment.json | `ec6cb0fe718f1d9353ade601d3bc5d1704cf396f7fcd5930013139a4b2c53a81` |
| test-planning | .osh/sessions/189cb171e97e/test-plan.md | `6935781e67da617f24a344f4a8cf48defdcaad2d6e4fe7ab942f178d02208de9` |
| test-qualification | .osh/sessions/189cb171e97e/test-qualification.json | `cc1c7b10ceebf97d1f02cd610453f01220d2fd26fbbd24f1a6543b7a19b9332b` |
| val-review | docs/validation-report.md | `24d67dceef61ad303746109a275572e89b9db33341b3a01895f620d7613a673f` |
| verify-loop | .osh/sessions/189cb171e97e/verify-loop.json | `04f2aa788d824f5404fb6049dde3f2e7dbded13e329f6b9de29334738a75f218` |

## 批准与归档

- 当前批准状态：待批准。
- 批准记录写入 `docs/release-manifest.yaml` 的 `approval_status` 字段。
- 发布包与清单一并归档，供后续审计复核。
