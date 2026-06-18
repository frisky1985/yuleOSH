import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { PipelineManager } from './pipeline';
import { PipelineTreeDataProvider, ReviewsTreeDataProvider, ActionsTreeDataProvider } from './treeView';
import { StatusBarManager } from './status';

let pipelineManager: PipelineManager;
let statusBarManager: StatusBarManager;
let misraDiagnosticCollection: vscode.DiagnosticCollection;

// ── MISRA Report Diagnostics (G-14) ──────────────────────────────────

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
    // Resolve relative file paths against workspace root
    const absPath = path.isAbsolute(filePath)
      ? filePath
      : path.join(workspaceRoot, filePath);

    const line = Math.max(0, (v.line || 1) - 1); // VS Code uses 0-based
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

    // Add rule details as hover-friendly information
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

// ── Activation ────────────────────────────────────────────────────────

export function activate(context: vscode.ExtensionContext) {
  console.log('yuleOSH extension activating...');

  // Initialize core manager
  pipelineManager = new PipelineManager();

  // Initialize MISRA diagnostics collection
  misraDiagnosticCollection = vscode.languages.createDiagnosticCollection('yuleosh-misra');
  context.subscriptions.push(misraDiagnosticCollection);

  // Register a hover provider for rule details
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

  // Register MISRA load diagnostics command
  const loadMisraDiagCmd = vscode.commands.registerCommand(
    'yuleosh.loadMisraDiagnostics',
    async () => {
      const workspaceFolder = getWorkspaceFolder();
      if (!workspaceFolder) return;

      updateMisraDiagnostics(workspaceFolder);
      vscode.window.showInformationMessage('yuleOSH: MISRA diagnostics refreshed');
    }
  );

  context.subscriptions.push(
    runPipelineCmd,
    viewStatusCmd,
    openDashboardCmd,
    flashDeviceCmd,
    loadMisraDiagCmd
  );

  // --- Initialize Status Bar ---

  statusBarManager = new StatusBarManager(pipelineManager);
  statusBarManager.activate();

  // --- Auto-review on save (if enabled) ---

  if (vscode.workspace.getConfiguration('yuleosh').get<boolean>('autoReview')) {
    const saveHandler = vscode.workspace.onDidSaveTextDocument(async (doc) => {
      if (doc.uri.scheme !== 'file') return;
      const workspaceFolder = vscode.workspace.getWorkspaceFolder(doc.uri);
      if (!workspaceFolder) return;

      // Debounce: only run if the file is part of the current workspace
      vscode.commands.executeCommand('yuleosh.runPipeline');
    });
    context.subscriptions.push(saveHandler);
  }

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
