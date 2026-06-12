import * as vscode from 'vscode';
import { PipelineManager } from './pipeline';
import { PipelineTreeDataProvider, ReviewsTreeDataProvider, ActionsTreeDataProvider } from './treeView';
import { StatusBarManager } from './status';

let pipelineManager: PipelineManager;
let statusBarManager: StatusBarManager;

export function activate(context: vscode.ExtensionContext) {
  console.log('yuleOSH extension activating...');

  // Initialize core manager
  pipelineManager = new PipelineManager();

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

  context.subscriptions.push(
    runPipelineCmd,
    viewStatusCmd,
    openDashboardCmd,
    flashDeviceCmd
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
