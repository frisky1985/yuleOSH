import * as vscode from 'vscode';
import { PipelineManager, PipelineStatus } from './pipeline';

export class StatusBarManager {
  private statusBarItem: vscode.StatusBarItem;
  private pipelineManager: PipelineManager;
  private _misraTotal: number = 0;
  private _misraErrors: number = 0;

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

    // Click handler opens quick command menu (VSC-5)
    this.statusBarItem.command = 'yuleosh.quickCommand';
    this.statusBarItem.show();
  }

  /** Update MISRA violation count shown in status bar */
  setMisraCount(total: number, errors: number): void {
    this._misraTotal = total;
    this._misraErrors = errors;
    this.updateDisplay(this.pipelineManager.getStatus());
  }

  updateStatus(status: PipelineStatus): void {
    this.updateDisplay(status);
  }

  private updateDisplay(status: PipelineStatus): void {
    const config = vscode.workspace.getConfiguration('yuleosh');
    const target = config.get<string>('defaultTarget', 'esp32');

    // Build MISRA count part
    let misraText = '';
    if (this._misraTotal > 0) {
      const icon = this._misraErrors > 0 ? '$(error)' : '$(warning)';
      misraText = ` ${icon} ${this._misraTotal}`;
    } else {
      misraText = ' $(check) 0';
    }

    if (status.running) {
      this.statusBarItem.text = `$(sync~spin) yuleOSH: Running...${misraText}`;
      this.statusBarItem.backgroundColor = new vscode.ThemeColor(
        'statusBarItem.warningBackground'
      );
      this.statusBarItem.tooltip = `Pipeline is running\nTarget: ${target}\nMISRA: ${this._misraTotal} (${this._misraErrors} errors)`;
    } else if (status.success && this._misraErrors === 0) {
      this.statusBarItem.text = `$(pass) yuleOSH: ✓${misraText}`;
      this.statusBarItem.backgroundColor = new vscode.ThemeColor(
        'statusBarItem.prominentBackground'
      );
      this.statusBarItem.tooltip = `Pipeline passed ✓\nLast run: ${status.lastRun?.toLocaleString()}\nMISRA: ${this._misraTotal} violations\nTarget: ${target}`;
    } else if (status.success && this._misraErrors > 0) {
      // Pipeline passed but there are MISRA errors
      this.statusBarItem.text = `$(warning) yuleOSH: ⚠${misraText}`;
      this.statusBarItem.backgroundColor = new vscode.ThemeColor(
        'statusBarItem.warningBackground'
      );
      this.statusBarItem.tooltip = `Pipeline passed but ${this._misraErrors} MISRA errors\nLast run: ${status.lastRun?.toLocaleString()}\nTotal MISRA: ${this._misraTotal}\nTarget: ${target}`;
    } else {
      this.statusBarItem.text = `$(error) yuleOSH: ✗${misraText}`;
      this.statusBarItem.backgroundColor = new vscode.ThemeColor(
        'statusBarItem.errorBackground'
      );
      this.statusBarItem.tooltip = `Pipeline failed ✗\nMessage: ${status.message}\nLast run: ${status.lastRun?.toLocaleString()}\nMISRA: ${this._misraTotal} violations\nTarget: ${target}`;
    }

    this.statusBarItem.show();
  }

  dispose(): void {
    this.statusBarItem.dispose();
  }
}
