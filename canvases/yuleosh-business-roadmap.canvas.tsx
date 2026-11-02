import {
  Stack,
  Grid,
  Row,
  H1,
  H2,
  H3,
  Text,
  Card,
  CardHeader,
  CardBody,
  Stat,
  Tag,
  Pill,
  Divider,
  Table,
  Timeline,
  MetricsGrid,
  Callout,
  Progress,
} from 'qoder/canvas';

export default function YuleOSHBusinessRoadmap() {
  return (
    <Stack gap={24} style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>
      {/* Header */}
      <Stack gap={8}>
        <H1>yuleOSH 商业落地路线图</H1>
        <Text tone="secondary">
          本地大模型 + RAG + LoRA 驱动的 ASPICE/V-Model 自动化开发平台商业化规划
        </Text>
        <Row gap={8} style={{ marginTop: 8 }}>
          <Pill tone="info">v1.0</Pill>
          <Pill tone="neutral">2026-10</Pill>
          <Pill tone="success">18 个月规划</Pill>
        </Row>
      </Stack>

      <Divider />

      {/* Core Metrics */}
      <MetricsGrid
        variant="card"
        columns={4}
        items={[
          { label: '目标 ARR', value: '500-1000万', tone: 'success', description: 'Month 18' },
          { label: '种子客户', value: '2-3 家', tone: 'info', description: '汽车零部件企业' },
          { label: '代码生成成功率', value: '>85%', tone: 'success', description: '本地模型' },
          { label: '部署周期', value: '<1 周', description: '企业级交付' },
        ]}
      />

      <Divider />

      {/* Strategic Flywheel */}
      <Card>
        <CardHeader>
          <H2>商业飞轮 — 核心护城河</H2>
        </CardHeader>
        <CardBody>
          <Stack gap={12}>
            <Text tone="secondary">
              yuleOSH 的价值不在 LLM 调用本身，在于 pipeline 编排 + 合规审计 + 领域知识积累。
              企业自建本地模型反而加深对 yuleOSH 的依赖。
            </Text>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              padding: '16px 0',
              flexWrap: 'wrap',
            }}>
              {[
                { text: '企业使用 yuleOSH', tone: 'info' as const },
                { text: '产生训练数据', tone: 'success' as const },
                { text: '本地模型更准', tone: 'success' as const },
                { text: '更多企业采用', tone: 'info' as const },
              ].map((item, i) => (
                <Row key={i} gap={8} style={{ alignItems: 'center' }}>
                  <Pill tone={item.tone}>{item.text}</Pill>
                  {i < 3 && <Text tone="tertiary">→</Text>}
                </Row>
              ))}
            </div>
            <Callout tone="info">
              即使企业自己训练模型，仍然需要 yuleOSH 的 30 步 pipeline、G0-G10 门禁、
              ISO 26262 / ASPICE 审计轨迹 — 这些是无法自建的合规资产。
            </Callout>
          </Stack>
        </CardBody>
      </Card>

      <Divider />

      {/* Roadmap Timeline */}
      <H2>分阶段实施路线</H2>

      {/* Phase 1 */}
      <Card>
        <CardHeader>
          <Row gap={12} style={{ alignItems: 'center', width: '100%' }}>
            <Tag tone="info">Phase 1</Tag>
            <H3 style={{ margin: 0 }}>技术基座</H3>
            <Text tone="tertiary" size="small">Month 1-3</Text>
          </Row>
        </CardHeader>
        <CardBody>
          <Grid columns={2} gap={12}>
            <Stack gap={8}>
              <Text weight="semibold">RAG 知识库基建</Text>
              <Text size="small" tone="secondary">
                企业代码库向量化 + AUTOSAR/ASPICE 领域知识检索集成到 codegen prompt
              </Text>
              <Progress value={0} max={100} />
            </Stack>
            <Stack gap={8}>
              <Text weight="semibold">LoRA 格式微调</Text>
              <Text size="small" tone="secondary">
                用 yuleOSH 历史产物训练模型格式遵从（### FILE: 标记、CMakeLists 结构）
              </Text>
              <Progress value={0} max={100} />
            </Stack>
            <Stack gap={8}>
              <Text weight="semibold">基座模型评估</Text>
              <Text size="small" tone="secondary">
                Qwen2.5-Coder 32B / DeepSeek-Coder 本地部署性能测试
              </Text>
              <Progress value={0} max={100} />
            </Stack>
            <Stack gap={8}>
              <Text weight="semibold">硬件方案</Text>
              <Text size="small" tone="secondary">
                单卡 A100/4090 推理节点，量化部署（Q4_K_M ~20GB）
              </Text>
              <Progress value={0} max={100} />
            </Stack>
          </Grid>
        </CardBody>
      </Card>

      {/* Phase 2 */}
      <Card>
        <CardHeader>
          <Row gap={12} style={{ alignItems: 'center', width: '100%' }}>
            <Tag tone="success">Phase 2</Tag>
            <H3 style={{ margin: 0 }}>产品化</H3>
            <Text tone="tertiary" size="small">Month 4-6</Text>
          </Row>
        </CardHeader>
        <CardBody>
          <Grid columns={2} gap={12}>
            <Stack gap={8}>
              <Text weight="semibold">Enterprise Edition 封装</Text>
              <Text size="small" tone="secondary">
                本地部署一键安装（Docker + Ollama + RAG），企业知识库管理 UI
              </Text>
            </Stack>
            <Stack gap={8}>
              <Text weight="semibold">多模型适配层</Text>
              <Text size="small" tone="secondary">
                本地 Ollama / DeepSeek API / OpenAI API 可切换，按企业需求灵活配置
              </Text>
            </Stack>
            <Stack gap={8}>
              <Text weight="semibold">知识库管理 UI</Text>
              <Text size="small" tone="secondary">
                上传代码库、配置 AUTOSAR 版本、管理向量化索引
              </Text>
            </Stack>
            <Stack gap={8}>
              <Text weight="semibold">部署自动化</Text>
              <Text size="small" tone="secondary">
                Ansible playbook + Docker Compose，30 分钟完成企业内网部署
              </Text>
            </Stack>
          </Grid>
        </CardBody>
      </Card>

      {/* Phase 3 */}
      <Card>
        <CardHeader>
          <Row gap={12} style={{ alignItems: 'center', width: '100%' }}>
            <Tag tone="warning">Phase 3</Tag>
            <H3 style={{ margin: 0 }}>商业验证</H3>
            <Text tone="tertiary" size="small">Month 7-9</Text>
          </Row>
        </CardHeader>
        <CardBody>
          <Grid columns={2} gap={12}>
            <Stack gap={8}>
              <Text weight="semibold">种子客户 POC</Text>
              <Text size="small" tone="secondary">
                2-3 家汽车零部件企业：车灯控制器、BCM、BMS 等 AUTOSAR 项目
              </Text>
            </Stack>
            <Stack gap={8}>
              <Text weight="semibold">定价验证</Text>
              <Text size="small" tone="secondary">
                一次性部署费（10-15万）+ 年度订阅（15-30万/年）
              </Text>
            </Stack>
            <Stack gap={8}>
              <Text weight="semibold">合规认证</Text>
              <Text size="small" tone="secondary">
                ISO 26262 / ASPICE 审计轨迹功能验证，获取行业认可
              </Text>
            </Stack>
            <Stack gap={8}>
              <Text weight="semibold">案例沉淀</Text>
              <Text size="small" tone="secondary">
                形成可复制的行业解决方案模板和 ROI 计算模型
              </Text>
            </Stack>
          </Grid>
        </CardBody>
      </Card>

      {/* Phase 4 */}
      <Card>
        <CardHeader>
          <Row gap={12} style={{ alignItems: 'center', width: '100%' }}>
            <Tag tone="danger">Phase 4</Tag>
            <H3 style={{ margin: 0 }}>规模扩张</H3>
            <Text tone="tertiary" size="small">Month 10-18</Text>
          </Row>
        </CardHeader>
        <CardBody>
          <Grid columns={2} gap={12}>
            <Stack gap={8}>
              <Text weight="semibold">行业解决方案包</Text>
              <Text size="small" tone="secondary">
                AUTOSAR Classic / Adaptive / ROS2 预配置模板
              </Text>
            </Stack>
            <Stack gap={8}>
              <Text weight="semibold">渠道合作</Text>
              <Text size="small" tone="secondary">
                与 Tier-1 系统集成商（Vector、ETAS）合作分销
              </Text>
            </Stack>
            <Stack gap={8}>
              <Text weight="semibold">联邦学习生态</Text>
              <Text size="small" tone="secondary">
                企业间脱敏数据共享，联合训练更强的行业模型
              </Text>
            </Stack>
            <Stack gap={8}>
              <Text weight="semibold">目标 ARR</Text>
              <Text size="small" tone="secondary">
                500-1000 万，10-20 家企业客户
              </Text>
            </Stack>
          </Grid>
        </CardBody>
      </Card>

      <Divider />

      {/* Revenue Model */}
      <H2>商业模式 — 三级定价</H2>
      <Table
        headers={['层级', '目标客户', '核心能力', '定价', '毛利率']}
        rows={[
          [
            'Community',
            '个人开发者 / 高校',
            '开源 pipeline + 云端 LLM 按量计费',
            '免费',
            'N/A',
          ],
          [
            'Enterprise',
            '汽车零部件企业',
            '本地部署 + RAG + LoRA + 合规审计',
            '¥15-30万/年',
            '~75%',
          ],
          [
            'Platform',
            'OEM / Tier-1',
            '多团队 + 联邦学习 + 定制模型训练',
            '¥50-100万/年',
            '~85%',
          ],
        ]}
        columnRoles={['text', 'text', 'text', 'numeric', 'numeric']}
      />

      <Divider />

      {/* Technical Architecture */}
      <H2>技术架构 — 三层模型</H2>
      <Card>
        <CardBody>
          <Grid columns={3} gap={16}>
            <Stack gap={8} style={{ textAlign: 'center', padding: 16 }}>
              <Tag tone="info">Layer 1</Tag>
              <Text weight="semibold">RAG 知识层</Text>
              <Text size="small" tone="secondary">
                解决「不知道 API 签名」
              </Text>
              <Divider />
              <Text size="small">
                企业代码库 + AUTOSAR 头文件 + 历史 pipeline 产物向量化检索
              </Text>
            </Stack>
            <Stack gap={8} style={{ textAlign: 'center', padding: 16 }}>
              <Tag tone="success">Layer 2</Tag>
              <Text weight="semibold">LoRA 格式层</Text>
              <Text size="small" tone="secondary">
                解决「不会按格式输出」
              </Text>
              <Divider />
              <Text size="small">
                yuleOSH 产物格式标记训练，~1000 条数据即可，14B 模型够用
              </Text>
            </Stack>
            <Stack gap={8} style={{ textAlign: 'center', padding: 16 }}>
              <Tag tone="warning">Layer 3</Tag>
              <Text weight="semibold">基座推理层</Text>
              <Text size="small" tone="secondary">
                解决「推理能力不足」
              </Text>
              <Divider />
              <Text size="small">
                Qwen2.5-Coder 32B+ 量化部署，单卡 4090 可跑
              </Text>
            </Stack>
          </Grid>
        </CardBody>
      </Card>

      <Divider />

      {/* Key Risks */}
      <H2>关键风险与应对</H2>
      <Table
        headers={['风险', '影响', '概率', '应对策略']}
        rows={[
          ['本地模型能力不足', '代码生成成功率低于 85%', '中', 'RAG 补偿 + 基座升级到 32B+'],
          ['企业数据安全风险', '客户不愿共享数据训练', '高', '联邦学习 + 完全本地化部署'],
          ['大厂竞争', 'Vector/ETAS 推出类似工具', '中', '深耕 ASPICE 合规 + 本地化优势'],
          ['开源社区分流', 'Community 用户不转化', '低', 'Enterprise 功能差异化（合规审计）'],
        ]}
        rowTone={['warning', 'warning', undefined, undefined]}
      />

      <Divider />

      {/* Next Steps */}
      <Callout tone="success">
        <Stack gap={8}>
          <Text weight="semibold">下一步行动</Text>
          <Text size="small">
            1. 完成 P0 RAG 基建（2-3 周）：代码库向量化 + 检索集成到 codegen prompt
          </Text>
          <Text size="small">
            2. 收集 LoRA 训练数据（1-2 周）：从 yuleOSH 历史 pipeline 产物提取格式训练对
          </Text>
          <Text size="small">
            3. 评估 32B 模型本地部署（1 周）：4090/A100 推理性能 + 量化精度测试
          </Text>
          <Text size="small">
            4. 联系种子客户（并行）：2-3 家汽车零部件企业 POC 意向沟通
          </Text>
        </Stack>
      </Callout>

      <Text tone="tertiary" size="small" style={{ textAlign: 'center', paddingTop: 8 }}>
        yuleOSH 商业落地路线图 v1.0 — 上海御勒电子科技有限公司
      </Text>
    </Stack>
  );
}
