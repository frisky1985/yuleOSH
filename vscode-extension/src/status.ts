import * as vscode from 'vscode';
import { PipelineManager, PipelineStatus } from './pipeline';

export class StatusBarManager {
  private statusBarItem: vscode.StatusBarItem;
  private pipelineManager: PipelineManager;

  constructor(pipelineManager: PipelineManager) {
    this.pipelineManager = pipelineManager;
    this.statusBarItem = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Left,
      100
    );
  }

  activate(): void {
    // Set initial state
    this.updateDisplay(this.pipelineManager.getStatus());

    // Listen for status changes
    this.pipelineManager.onDidChangeStatus((status) => {
      this.updateDisplay(status);
    });

    // Click handler
    this.statusBarItem.command = 'yuleosh.viewStatus';
    this.statusBarItem.show();
  }

  updateStatus(status: PipelineStatus): void {
    this.updateDisplay(status);
  }

  private updateDisplay(status: PipelineStatus): void {
    const config = vscode.workspace.getConfiguration('yuleosh');
    const target = config.get<string>('defaultTarget', 'esp32');
    const backendUrl = config.get<string>('backendUrl', 'http://localhost:8080');

    if (status.running) {
      this.statusBarItem.text = `$(sync~spin) yuleOSH: Running...`;
      this.statusBarItem.backgroundColor = new vscode.ThemeColor(
        'statusBarItem.warningBackground'
      );
      this.statusBarItem.tooltip = `Pipeline is running\nTarget: ${target}\nBackend: ${backendUrl}`;
    } else if (status.success) {
      this.statusBarItem.text = `$(pass) yuleOSH: Passed`;
      this.statusBarItem.backgroundColor = new vscode.ThemeColor(
        'statusBarItem.prominentBackground'
      );
      this.statusBarItem.tooltip = `Pipeline passed ✓\nLast run: ${status.lastRun?.toLocaleString()}\nTarget: ${target}\nBackend: ${backendUrl}`;
    } else {
      this.statusBarItem.text = `$(error) yuleOSH: Failed`;
      this.statusBarItem.backgroundColor = new vscode.ThemeColor(
        'statusBarItem.errorBackground'
      );
      this.statusBarItem.tooltip = `Pipeline failed ✗\nMessage: ${status.message}\nLast run: ${status.lastRun?.toLocaleString()}\nTarget: ${target}\nBackend: ${backendUrl}`;
    }

    this.statusBarItem.show();
  }

  dispose(): void {
    this.statusBarItem.dispose();
  }
}
