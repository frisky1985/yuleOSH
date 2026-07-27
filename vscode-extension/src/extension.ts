import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { exec } from 'child_process';
import { promisify } from 'util';
import { PipelineManager } from './pipeline';
import { PipelineTreeDataProvider, ReviewsTreeDataProvider, ActionsTreeDataProvider } from './treeView';
import { StatusBarManager } from './status';

const execAsync = promisify(exec);

let pipelineManager: PipelineManager;
let statusBarManager: StatusBarManager;
let misraDiagnosticCollection: vscode.DiagnosticCollection;

// ── MISRA Report Diagnostics ──────────────────────────────────────────

function loadMisraReport(workspaceRoot: string): any | null {
  const reportPath = path.join(workspaceRoot, '.yuleosh', 'reports', 'misra-report.json');
  try {
    if (fs.existsSync(reportPath)) {
      const content = fs.readFileSync(reportPath, 'utf-8');
      return JSON.parse(content);
    }
  } catch (err) {
    console.error('Failed to load MISRA report:', err);
  }
  return null;
}

/** Count MISRA violations by severity */
function countMisraViolations(workspaceRoot: string): { total: number; errors: number; warnings: number } {
  const report = loadMisraReport(workspaceRoot);
  if (!report) return { total: 0, errors: 0, warnings: 0 };

  const violations: any[] = report.violations_raw || [];
  const errors = violations.filter((v: any) => v.severity === 'error').length;
  const warnings = violations.filter((v: any) => v.severity === 'warning' || v.severity !== 'error').length;
  return { total: violations.length, errors, warnings };
}

function updateMisraDiagnostics(workspaceRoot: string): void {
  const report = loadMisraReport(workspaceRoot);
  if (!report) {
    console.log('No MISRA report found; clearing diagnostics');
    misraDiagnosticCollection.clear();
    return;
  }

  const violations: any[] = report.violations_raw || [];
  if (violations.length === 0) {
    misraDiagnosticCollection.clear();
    return;
  }

  // Group diagnostics by file
  const fileDiagnostics = new Map<string, vscode.Diagnostic[]>();

  for (const v of violations) {
    const filePath = v.file || '';
    const absPath = path.isAbsolute(filePath)
      ? filePath
      : path.join(workspaceRoot, filePath);

    const line = Math.max(0, (v.line || 1) - 1);
    const col = Math.max(0, (v.col || 0) - 1);
    const range = new vscode.Range(line, col, line, col + 1);

    const ruleId = v.rule_id || 'unknown';
    const message = `[${ruleId}] ${v.message || 'MISRA violation'}`;

    const severityMap: Record<string, vscode.DiagnosticSeverity> = {
      'error': vscode.DiagnosticSeverity.Error,
      'warning': vscode.DiagnosticSeverity.Warning,
      'style': vscode.DiagnosticSeverity.Information,
      'information': vscode.DiagnosticSeverity.Information,
      'performance': vscode.DiagnosticSeverity.Warning,
    };
    const severity = severityMap[v.severity] ?? vscode.DiagnosticSeverity.Warning;

    const diagnostic = new vscode.Diagnostic(range, message, severity);
    diagnostic.source = 'yuleOSH MISRA';
    diagnostic.code = ruleId;
    diagnostic.tags = severity === vscode.DiagnosticSeverity.Error
      ? [vscode.DiagnosticTag.Unnecessary]
      : [];

    diagnostic.relatedInformation = [
      new vscode.DiagnosticRelatedInformation(
        new vscode.Location(vscode.Uri.file(absPath), range),
        `Rule: ${ruleId} | Line: ${v.line}`
      ),
    ];

    if (!fileDiagnostics.has(absPath)) {
      fileDiagnostics.set(absPath, []);
    }
    fileDiagnostics.get(absPath)!.push(diagnostic);
  }

  // Apply to collection
  misraDiagnosticCollection.clear();
  for (const [filePath, diags] of fileDiagnostics) {
    const uri = vscode.Uri.file(filePath);
    misraDiagnosticCollection.set(uri, diags);
  }

  // Update status bar with violation count
  if (statusBarManager) {
    statusBarManager.setMisraCount(violations.length, violations.filter((v: any) => v.severity === 'error').length);
  }

  const diagCount = violations.length;
  vscode.window.showInformationMessage(
    `yuleOSH: ${diagCount} MISRA violation(s) loaded in Problems panel`,
    'Open Report'
  ).then(selection => {
    if (selection === 'Open Report') {
      const reportUri = vscode.Uri.file(
        path.join(workspaceRoot, '.yuleosh', 'reports', 'misra-report.md')
      );
      vscode.commands.executeCommand('markdown.showPreview', reportUri);
    }
  });
}

// ── Code Action Provider for MISRA ────────────────────────────────────

class MisraCodeActionProvider implements vscode.CodeActionProvider {
  public static readonly providedCodeActionKinds = [
    vscode.CodeActionKind.QuickFix,
  ];

  provideCodeActions(
    document: vscode.TextDocument,
    range: vscode.Range,
    context: vscode.CodeActionContext,
    _token: vscode.CancellationToken
  ): vscode.CodeAction[] {
    const actions: vscode.CodeAction[] = [];

    for (const diag of context.diagnostics) {
      if (diag.source === 'yuleOSH MISRA') {
        const ruleId = diag.code as string || 'unknown';

        // Code Action: View MISRA rule details
        const viewRule = new vscode.CodeAction(
          `查看 MISRA 规则详情 (${ruleId})`,
          vscode.CodeActionKind.QuickFix
        );
        viewRule.command = {
          command: 'yuleosh.showMisraRuleDetail',
          title: 'Show MISRA Rule Detail',
          arguments: [ruleId],
        };
        viewRule.diagnostics = [diag];
        actions.push(viewRule);

        // Code Action: Open rule documentation
        const openDoc = new vscode.CodeAction(
          `打开 MISRA ${ruleId} 文档`,
          vscode.CodeActionKind.QuickFix
        );
        openDoc.command = {
          command: 'yuleosh.openMisraDoc',
          title: 'Open MISRA Documentation',
          arguments: [ruleId],
        };
        openDoc.diagnostics = [diag];
        actions.push(openDoc);
      }
    }

    return actions;
  }
}

// ── Evidence WebView Panel ────────────────────────────────────────────

class EvidencePanel {
  public static currentPanel: EvidencePanel | undefined;
  private readonly _panel: vscode.WebviewPanel;
  private _disposables: vscode.Disposable[] = [];

  private constructor(panel: vscode.WebviewPanel, workspaceRoot: string) {
    this._panel = panel;
    this._panel.onDidDispose(() => this.dispose(), null, this._disposables);
    this._panel.webview.html = this._getHtml(workspaceRoot);
    this._panel.webview.onDidReceiveMessage(
      async (message) => {
        switch (message.command) {
          case 'refresh':
            this._panel.webview.html = this._getHtml(workspaceRoot);
            return;
          case 'export':
            await this._exportEvidence(workspaceRoot);
            return;
        }
      },
      null,
      this._disposables
    );
  }

  public static createOrShow(workspaceRoot: string) {
    const column = vscode.window.activeTextEditor
      ? vscode.window.activeTextEditor.viewColumn
      : undefined;

    if (EvidencePanel.currentPanel) {
      EvidencePanel.currentPanel._panel.reveal(column);
      EvidencePanel.currentPanel._panel.webview.html =
        EvidencePanel.currentPanel._getHtml(workspaceRoot);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      'yuleoshEvidence',
      'yuleOSH — Evidence Report',
      column || vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
      }
    );

    EvidencePanel.currentPanel = new EvidencePanel(panel, workspaceRoot);
  }

  public dispose() {
    EvidencePanel.currentPanel = undefined;
    this._panel.dispose();
    while (this._disposables.length) {
      const d = this._disposables.pop();
      if (d) d.dispose();
    }
  }

  private async _exportEvidence(workspaceRoot: string): Promise<void> {
    const reportPath = path.join(workspaceRoot, '.yuleosh', 'reports');
    const files = fs.readdirSync(reportPath).filter(f => f.startsWith('evidence') || f.includes('report'));
    if (files.length === 0) {
      vscode.window.showWarningMessage('No evidence reports found to export.');
      return;
    }

    const uri = await vscode.window.showSaveDialog({
      defaultUri: vscode.Uri.file(path.join(workspaceRoot, 'yuleosh-evidence-export.html')),
      filters: { 'HTML Files': ['html'], 'Text Files': ['txt', 'md'] },
    });
    if (!uri) return;

    // Collect all report files into a single summary
    let exportContent = '<html><head><meta charset="utf-8"><title>yuleOSH Evidence Report</title></head><body>';
    exportContent += '<h1>yuleOSH Evidence Report</h1>';
    exportContent += `<p>Generated: ${new Date().toISOString()}</p>`;
    exportContent += '<hr>';

    for (const file of files) {
      const content = fs.readFileSync(path.join(reportPath, file), 'utf-8');
      exportContent += `<h2>${file}</h2>`;
      exportContent += `<pre>${this._escapeHtml(content)}</pre>`;
      exportContent += '<hr>';
    }

    exportContent += '</body></html>';
    fs.writeFileSync(uri.fsPath, exportContent, 'utf-8');
    vscode.window.showInformationMessage(`Evidence exported to ${uri.fsPath}`);
  }

  private _escapeHtml(text: string): string {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  private _getHtml(workspaceRoot: string): string {
    const reportPath = path.join(workspaceRoot, '.yuleosh', 'reports');
    let reportsHtml = '<p>No evidence reports found.</p>';

    try {
      if (fs.existsSync(reportPath)) {
        const files = fs.readdirSync(reportPath).filter(f =>
          f.endsWith('.md') || f.endsWith('.json') || f.endsWith('.html') || f.endsWith('.txt')
        );
        if (files.length > 0) {
          reportsHtml = '<ul>';
          for (const file of files) {
            const content = fs.readFileSync(path.join(reportPath, file), 'utf-8').substring(0, 2000);
            reportsHtml += `<li><strong>${file}</strong><pre style="white-space:pre-wrap;font-size:12px;">${this._escapeHtml(content.substring(0, 500))}${content.length > 500 ? '...' : ''}</pre></li>`;
          }
          reportsHtml += '</ul>';
        }
      }
    } catch (e) {
      reportsHtml = `<p>Error reading reports: ${e}</p>`;
    }

    // Load KPI summary
    let kpiHtml = '<p>No KPI data found.</p>';
    const kpiPath = path.join(workspaceRoot, '.yuleosh', 'kpi-baseline.json');
    try {
      if (fs.existsSync(kpiPath)) {
        const kpi = JSON.parse(fs.readFileSync(kpiPath, 'utf-8'));
        kpiHtml = '<ul>';
        for (const [key, val] of Object.entries(kpi)) {
          kpiHtml += `<li><strong>${key}:</strong> ${JSON.stringify(val)}</li>`;
        }
        kpiHtml += '</ul>';
      }
    } catch (e) {
      // ignore
    }

    // MISRA summary
    const misraCount = countMisraViolations(workspaceRoot);

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>yuleOSH Evidence</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 16px; color: var(--vscode-editor-foreground); background: var(--vscode-editor-background); }
    h1 { border-bottom: 2px solid var(--vscode-panel-border); padding-bottom: 8px; }
    h2 { color: var(--vscode-textLink-foreground); margin-top: 24px; }
    pre { background: var(--vscode-textBlockQuote-background); padding: 8px; border-radius: 4px; overflow-x: auto; }
    .stats { display: flex; gap: 16px; flex-wrap: wrap; }
    .stat-card { background: var(--vscode-editor-inlineValuesBackground); padding: 12px 20px; border-radius: 8px; text-align: center; min-width: 120px; }
    .stat-card .num { font-size: 28px; font-weight: bold; }
    .stat-card .label { font-size: 12px; opacity: 0.7; }
    .green { color: #4caf50; }
    .red { color: #f44336; }
    .orange { color: #ff9800; }
    button { background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 6px 14px; border-radius: 4px; cursor: pointer; margin-right: 8px; }
    button:hover { background: var(--vscode-button-hoverBackground); }
  </style>
</head>
<body>
  <h1>🔬 yuleOSH — Evidence & KPI Summary</h1>
  <div class="stats">
    <div class="stat-card">
      <div class="num ${misraCount.errors > 0 ? 'red' : 'green'}">${misraCount.total}</div>
      <div class="label">MISRA Violations</div>
    </div>
    <div class="stat-card">
      <div class="num ${misraCount.errors > 0 ? 'red' : 'orange'}">${misraCount.errors}</div>
      <div class="label">Errors</div>
    </div>
    <div class="stat-card">
      <div class="num">${misraCount.warnings}</div>
      <div class="label">Warnings</div>
    </div>
  </div>

  <p>
    <button onclick="refresh()">🔄 Refresh</button>
    <button onclick="exportReport()">📤 Export</button>
  </p>

  <h2>🏗️ KPI Baseline</h2>
  ${kpiHtml}

  <h2>📋 Evidence Reports</h2>
  ${reportsHtml}

  <script>
    const vscode = acquireVsCodeApi();
    function refresh() { vscode.postMessage({ command: 'refresh' }); }
    function exportReport() { vscode.postMessage({ command: 'export' }); }
  </script>
</body>
</html>`;
  }
}

// ── Activation ────────────────────────────────────────────────────────

export function activate(context: vscode.ExtensionContext) {
  console.log('yuleOSH extension activating...');

  // Initialize core manager
  pipelineManager = new PipelineManager();

  // Initialize MISRA diagnostics collection
  misraDiagnosticCollection = vscode.languages.createDiagnosticCollection('yuleosh-misra');
  context.subscriptions.push(misraDiagnosticCollection);

  // Register hover provider for rule details
  const hoverProvider = vscode.languages.registerHoverProvider(
    { scheme: 'file', language: 'c', pattern: '**/*.{c,h,cpp,hpp}' },
    {
      provideHover(document: vscode.TextDocument, position: vscode.Position): vscode.Hover | null {
        const diags = misraDiagnosticCollection.get(document.uri);
        if (!diags) return null;

        for (const diag of diags) {
          if (diag.range.contains(position)) {
            const markdown = new vscode.MarkdownString();
            markdown.appendCodeblock(diag.message, 'text');
            if (diag.code) {
              markdown.appendText(`Rule: ${diag.code}`);
            }
            return new vscode.Hover(markdown);
          }
        }
        return null;
      }
    }
  );
  context.subscriptions.push(hoverProvider);

  // Register Code Action provider for MISRA (VSC-2)
  const misraCodeActionProvider = vscode.languages.registerCodeActionsProvider(
    { scheme: 'file', language: 'c', pattern: '**/*.{c,h,cpp,hpp}' },
    new MisraCodeActionProvider(),
    { providedCodeActionKinds: MisraCodeActionProvider.providedCodeActionKinds }
  );
  context.subscriptions.push(misraCodeActionProvider);

  // --- Register Tree View Providers ---

  const pipelineProvider = new PipelineTreeDataProvider(pipelineManager);
  const reviewsProvider = new ReviewsTreeDataProvider();
  const actionsProvider = new ActionsTreeDataProvider();

  vscode.window.createTreeView('yuleosh.pipelineView', {
    treeDataProvider: pipelineProvider,
  });
  vscode.window.createTreeView('yuleosh.reviewsView', {
    treeDataProvider: reviewsProvider,
  });
  vscode.window.createTreeView('yuleosh.actionsView', {
    treeDataProvider: actionsProvider,
  });

  // --- Register Commands ---

  // VSC-1: yuleosh:check-misra — Run MISRA check via CLI
  const checkMisraCmd = vscode.commands.registerCommand(
    'yuleosh.checkMisra',
    async () => {
      const workspaceFolder = getWorkspaceFolder();
      if (!workspaceFolder) return;

      vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: 'yuleOSH: Running MISRA check...', cancellable: true },
        async (progress, token) => {
          token.onCancellationRequested(() => {
            vscode.window.showWarningMessage('yuleOSH: MISRA check cancelled');
          });
          try {
            progress.report({ increment: 0, message: 'Invoking yuleosh misra...' });
            const { stdout, stderr } = await execAsync(`yuleosh misra "${workspaceFolder}"`, {
              cwd: workspaceFolder,
              timeout: 120000,
            });
            progress.report({ increment: 100 });
            updateMisraDiagnostics(workspaceFolder);
            const counts = countMisraViolations(workspaceFolder);
            if (counts.total === 0) {
              vscode.window.showInformationMessage('✅ yuleOSH: No MISRA violations found!');
            } else {
              vscode.window.showWarningMessage(`⚠️ yuleOSH: ${counts.total} MISRA violation(s) (${counts.errors} errors, ${counts.warnings} warnings)`);
            }
          } catch (err: any) {
            vscode.window.showErrorMessage(`yuleOSH: MISRA check failed: ${err.message}`);
          }
        }
      );
    }
  );

  // VSC-1: yuleosh:run-ci — Run CI pipeline
  const runCiCmd = vscode.commands.registerCommand(
    'yuleosh.runCi',
    async () => {
      const workspaceFolder = getWorkspaceFolder();
      if (!workspaceFolder) return;

      vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: 'yuleOSH: Running CI pipeline...', cancellable: true },
        async (progress, token) => {
          token.onCancellationRequested(() => {
            vscode.window.showWarningMessage('yuleOSH: CI cancelled');
          });
          try {
            progress.report({ increment: 0, message: 'Invoking yuleosh ci...' });
            const { stdout, stderr } = await execAsync(`yuleosh ci run "${workspaceFolder}"`, {
              cwd: workspaceFolder,
              timeout: 300000,
            });
            progress.report({ increment: 100 });
            const output = (stdout + stderr).trim();
            pipelineProvider.refresh();

            // Show result in output channel
            const outputChannel = vscode.window.createOutputChannel('yuleOSH CI');
            outputChannel.clear();
            outputChannel.appendLine('=== yuleOSH CI Run ===');
            outputChannel.appendLine(output);
            outputChannel.show();

            vscode.window.showInformationMessage('✅ yuleOSH: CI pipeline completed');
          } catch (err: any) {
            const outputChannel = vscode.window.createOutputChannel('yuleOSH CI');
            outputChannel.clear();
            outputChannel.appendLine('=== yuleOSH CI Run (Failed) ===');
            outputChannel.appendLine(err.stdout || '');
            outputChannel.appendLine(err.stderr || '');
            outputChannel.appendLine(`Error: ${err.message}`);
            outputChannel.show();
            vscode.window.showErrorMessage(`yuleOSH: CI failed: ${err.message}`);
          }
        }
      );
    }
  );

  // VSC-1: yuleosh:show-dashboard — Show integrated dashboard webview
  const showDashboardCmd = vscode.commands.registerCommand(
    'yuleosh.showDashboard',
    () => {
      const workspaceFolder = getWorkspaceFolder();
      if (!workspaceFolder) return;

      // Open the built-in dashboard HTML if available
      const dashboardPath = path.join(workspaceFolder, 'dashboard.html');
      if (fs.existsSync(dashboardPath)) {
        vscode.commands.executeCommand('markdown.showPreview', vscode.Uri.file(dashboardPath));
      } else {
        const backendUrl = vscode.workspace
          .getConfiguration('yuleosh')
          .get<string>('backendUrl', 'http://localhost:8080');
        vscode.env.openExternal(vscode.Uri.parse(`${backendUrl}/dashboard`));
      }
    }
  );

  // VSC-4: Evidence Report command
  const viewEvidenceCmd = vscode.commands.registerCommand(
    'yuleosh.viewEvidence',
    () => {
      const workspaceFolder = getWorkspaceFolder();
      if (!workspaceFolder) return;
      EvidencePanel.createOrShow(workspaceFolder);
    }
  );

  // MISRA rule detail command
  const showMisraRuleDetailCmd = vscode.commands.registerCommand(
    'yuleosh.showMisraRuleDetail',
    (ruleId: string) => {
      // Try loading MISRA rules YAML for rule description
      const workspaceFolder = getWorkspaceFolder();
      if (!workspaceFolder) return;

      const rulesYamlPath = path.join(workspaceFolder, 'misra-rules.yaml');
      let detail = `Rule: ${ruleId}`;
      if (fs.existsSync(rulesYamlPath)) {
        // Search the YAML for the rule
        try {
          const content = fs.readFileSync(rulesYamlPath, 'utf-8');
          const lines = content.split('\n');
          let found = false;
          let ruleLines: string[] = [];
          for (const line of lines) {
            if (line.includes(ruleId)) {
              found = true;
            }
            if (found) {
              ruleLines.push(line);
              if (line.trim() === '' && ruleLines.length > 1) break;
            }
          }
          if (ruleLines.length > 0) {
            detail = ruleLines.join('\n');
          }
        } catch (e) {
          // ignore
        }
      }

      vscode.window.showInformationMessage(detail, { modal: true });
    }
  );

  // Open MISRA doc command
  const openMisraDocCmd = vscode.commands.registerCommand(
    'yuleosh.openMisraDoc',
    (ruleId: string) => {
      vscode.env.openExternal(
        vscode.Uri.parse(`https://misra.org.uk/rule/${ruleId}`)
      );
    }
  );

  const runPipelineCmd = vscode.commands.registerCommand(
    'yuleosh.runPipeline',
    async () => {
      const workspaceFolder = getWorkspaceFolder();
      if (!workspaceFolder) return;

      vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: 'yuleOSH: Running Pipeline...',
          cancellable: true,
        },
        async (progress, token) => {
          token.onCancellationRequested(() => {
            pipelineManager.cancel();
            vscode.window.showWarningMessage('yuleOSH: Pipeline cancelled');
          });

          progress.report({ increment: 0 });
          try {
            const result = await pipelineManager.runPipeline(workspaceFolder);
            progress.report({ increment: 100 });
            pipelineProvider.refresh();
            statusBarManager.updateStatus(pipelineManager.getStatus());

            // After pipeline run, load MISRA diagnostics
            updateMisraDiagnostics(workspaceFolder);

            if (result.success) {
              vscode.window.showInformationMessage('yuleOSH: Pipeline completed successfully!');
            } else {
              vscode.window.showErrorMessage(`yuleOSH: Pipeline failed: ${result.message}`);
            }
          } catch (err: any) {
            vscode.window.showErrorMessage(`yuleOSH: Pipeline error: ${err.message}`);
          }
        }
      );
    }
  );

  const viewStatusCmd = vscode.commands.registerCommand(
    'yuleosh.viewStatus',
    () => {
      const status = pipelineManager.getStatus();
      const message = status.running
        ? 'yuleOSH: Pipeline is running...'
        : status.success
        ? `yuleOSH: Pipeline passed (last run: ${status.lastRun?.toLocaleString()})`
        : `yuleOSH: Pipeline failed (last run: ${status.lastRun?.toLocaleString()})`;
      vscode.window.showInformationMessage(message, 'View Details').then((selection) => {
        if (selection === 'View Details') {
          vscode.commands.executeCommand('yuleosh.openDashboard');
        }
      });
    }
  );

  const openDashboardCmd = vscode.commands.registerCommand(
    'yuleosh.openDashboard',
    () => {
      const backendUrl = vscode.workspace
        .getConfiguration('yuleosh')
        .get<string>('backendUrl', 'http://localhost:8080');
      vscode.env.openExternal(vscode.Uri.parse(`${backendUrl}/dashboard`));
    }
  );

  const flashDeviceCmd = vscode.commands.registerCommand(
    'yuleosh.flashDevice',
    async () => {
      const workspaceFolder = getWorkspaceFolder();
      if (!workspaceFolder) return;

      const target = vscode.workspace
        .getConfiguration('yuleosh')
        .get<string>('defaultTarget', 'esp32');

      const confirmed = await vscode.window.showWarningMessage(
        `Flash current project to ${target}?`,
        { modal: true },
        'Flash'
      );
      if (confirmed !== 'Flash') return;

      vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: `yuleOSH: Flashing ${target}...`,
        },
        async (progress) => {
          progress.report({ increment: 0 });
          try {
            const result = await pipelineManager.flashDevice(workspaceFolder, target);
            progress.report({ increment: 100 });
            if (result.success) {
              vscode.window.showInformationMessage(`yuleOSH: Successfully flashed ${target}!`);
            } else {
              vscode.window.showErrorMessage(`yuleOSH: Flash failed: ${result.message}`);
            }
          } catch (err: any) {
            vscode.window.showErrorMessage(`yuleOSH: Flash error: ${err.message}`);
          }
        }
      );
    }
  );

  // MISRA load diagnostics command
  const loadMisraDiagCmd = vscode.commands.registerCommand(
    'yuleosh.loadMisraDiagnostics',
    async () => {
      const workspaceFolder = getWorkspaceFolder();
      if (!workspaceFolder) return;

      updateMisraDiagnostics(workspaceFolder);
      vscode.window.showInformationMessage('yuleOSH: MISRA diagnostics refreshed');
    }
  );

  // Reload MISRA report command (from misraProvider)
  const reloadMisraReportCmd = vscode.commands.registerCommand(
    'yuleosh.reloadMisraReport',
    async () => {
      const workspaceFolder = getWorkspaceFolder();
      if (!workspaceFolder) return;
      updateMisraDiagnostics(workspaceFolder);
      const counts = countMisraViolations(workspaceFolder);
      vscode.window.showInformationMessage(
        `MISRA report reloaded: ${counts.total} violation(s) (${counts.errors} errors)`
      );
    }
  );

  // Show MISRA problems command
  const showMisraProblemsCmd = vscode.commands.registerCommand(
    'yuleosh.showMisraProblems',
    () => {
      vscode.commands.executeCommand('workbench.action.problems.focus');
    }
  );

  // VSC-3: View pipeline stage log
  const viewPipelineLogCmd = vscode.commands.registerCommand(
    'yuleosh.viewPipelineLog',
    async (stageName: string) => {
      const workspaceFolder = getWorkspaceFolder();
      if (!workspaceFolder) return;

      const log = pipelineManager.getStageLog(stageName, workspaceFolder);
      const outputChannel = vscode.window.createOutputChannel(`yuleOSH: ${stageName}`);
      outputChannel.clear();
      outputChannel.appendLine(`=== yuleOSH Stage: ${stageName} ===`);
      outputChannel.appendLine(`Timestamp: ${new Date().toISOString()}`);
      outputChannel.appendLine('');
      if (log) {
        outputChannel.appendLine(log);
      } else {
        outputChannel.appendLine('No log available for this stage.');
        outputChannel.appendLine('');
        outputChannel.appendLine('Tip: Run the pipeline first to generate logs.');
      }
      outputChannel.show();
    }
  );

  // VSC-5: Quick command menu (invoked by status bar click)
  const quickCommandCmd = vscode.commands.registerCommand(
    'yuleosh.quickCommand',
    async () => {
      const selection = await vscode.window.showQuickPick([
        { label: '$(play) Run Pipeline', description: 'yuleosh.runPipeline' },
        { label: '$(check) Check MISRA', description: 'yuleosh.checkMisra' },
        { label: '$(tools) Run CI', description: 'yuleosh.runCi' },
        { label: '$(dashboard) Show Dashboard', description: 'yuleosh.showDashboard' },
        { label: '$(file) View Evidence Report', description: 'yuleosh.viewEvidence' },
        { label: '$(circuit-board) Flash Device', description: 'yuleosh.flashDevice' },
        { label: '$(info) View Status', description: 'yuleosh.viewStatus' },
        { label: '$(sync) Reload MISRA Report', description: 'yuleosh.reloadMisraReport' },
      ], {
        placeHolder: 'Select a yuleOSH command',
      });

      if (selection) {
        vscode.commands.executeCommand(selection.description);
      }
    }
  );

  context.subscriptions.push(
    checkMisraCmd,
    runCiCmd,
    showDashboardCmd,
    viewEvidenceCmd,
    showMisraRuleDetailCmd,
    openMisraDocCmd,
    runPipelineCmd,
    viewStatusCmd,
    openDashboardCmd,
    flashDeviceCmd,
    loadMisraDiagCmd,
    reloadMisraReportCmd,
    showMisraProblemsCmd,
    viewPipelineLogCmd,
    quickCommandCmd
  );

  // --- Initialize Status Bar (VSC-5) ---

  statusBarManager = new StatusBarManager(pipelineManager);
  statusBarManager.activate();

  // --- Auto-review on save (VSC-2) — triggers MISRA diagnostics refresh on save ---

  const saveHandler = vscode.workspace.onDidSaveTextDocument(async (doc) => {
    if (doc.uri.scheme !== 'file') return;
    if (!doc.fileName.match(/\.(c|cpp|h|hpp)$/)) return;
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(doc.uri);
    if (!workspaceFolder) return;

    // Auto-load MISRA diagnostics on save
    setTimeout(() => updateMisraDiagnostics(workspaceFolder.uri.fsPath), 500);
  });
  context.subscriptions.push(saveHandler);

  // --- Load existing MISRA report on activation ---
  const workspaceRoot = getWorkspaceFolder();
  if (workspaceRoot) {
    setTimeout(() => updateMisraDiagnostics(workspaceRoot), 1000);
  }

  console.log('yuleOSH extension activated');
}

export function deactivate() {
  console.log('yuleOSH extension deactivating...');
  if (pipelineManager) {
    pipelineManager.dispose();
  }
  if (statusBarManager) {
    statusBarManager.dispose();
  }
}

function getWorkspaceFolder(): string | undefined {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    vscode.window.showErrorMessage('yuleOSH: No workspace folder open');
    return undefined;
  }
  return folders[0].uri.fsPath;
}
