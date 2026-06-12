import { exec } from 'child_process';
import { promisify } from 'util';
import * as vscode from 'vscode';

const execAsync = promisify(exec);

export interface PipelineStatus {
  running: boolean;
  success: boolean;
  message: string;
  lastRun?: Date;
  details?: string;
}

export interface PipelineResult {
  success: boolean;
  message: string;
  details?: string;
}

export class PipelineManager {
  private _status: PipelineStatus = {
    running: false,
    success: false,
    message: 'Idle',
  };
  private _onDidChangeStatus = new vscode.EventEmitter<PipelineStatus>();
  readonly onDidChangeStatus: vscode.Event<PipelineStatus> =
    this._onDidChangeStatus.event;

  private currentProcess: import('child_process').ChildProcess | null = null;

  getStatus(): PipelineStatus {
    return { ...this._status };
  }

  cancel(): void {
    if (this.currentProcess) {
      this.currentProcess.kill('SIGINT');
      this.currentProcess = null;
    }
    this._status.running = false;
    this._status.message = 'Cancelled';
    this._onDidChangeStatus.fire(this._status);
  }

  async runPipeline(workspaceFolder: string): Promise<PipelineResult> {
    this._status.running = true;
    this._status.message = 'Running pipeline...';
    this._status.lastRun = new Date();
    this._onDidChangeStatus.fire(this._status);

    try {
      const cmd = `yuleosh pipeline run "${workspaceFolder}"`;
      const { stdout, stderr } = await execAsync(cmd, {
        cwd: workspaceFolder,
        timeout: 300000, // 5 min timeout
      });

      const output = stdout + stderr;
      this._status.success = true;
      this._status.running = false;
      this._status.message = 'Pipeline passed';
      this._status.details = output;
      this._onDidChangeStatus.fire(this._status);

      return { success: true, message: 'Pipeline completed', details: output };
    } catch (err: any) {
      this._status.success = false;
      this._status.running = false;
      this._status.message = err.message || 'Pipeline failed';
      this._status.details = err.stdout || err.stderr || '';
      this._onDidChangeStatus.fire(this._status);

      return {
        success: false,
        message: err.message || 'Pipeline failed',
        details: err.stdout || err.stderr || '',
      };
    }
  }

  async flashDevice(
    workspaceFolder: string,
    target: string
  ): Promise<PipelineResult> {
    try {
      const cmd = `yuleosh flash --target "${target}" "${workspaceFolder}"`;
      const { stdout, stderr } = await execAsync(cmd, {
        cwd: workspaceFolder,
        timeout: 600000, // 10 min timeout for flashing
      });

      const output = (stdout + stderr).trim();
      return { success: true, message: `${target} flashed successfully`, details: output };
    } catch (err: any) {
      return {
        success: false,
        message: err.message || 'Flash failed',
        details: err.stdout || err.stderr || '',
      };
    }
  }

  dispose(): void {
    this.cancel();
    this._onDidChangeStatus.dispose();
  }
}
