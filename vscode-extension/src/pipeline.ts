import { exec } from 'child_process';
import { promisify } from 'util';
import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

const execAsync = promisify(exec);

export interface StageStatus {
  name: string;
  status: 'pending' | 'running' | 'pass' | 'fail' | 'skipped';
  startTime?: Date;
  endTime?: Date;
  log?: string;
}

export interface PipelineStatus {
  running: boolean;
  success: boolean;
  message: string;
  lastRun?: Date;
  details?: string;
  stages: StageStatus[];
}

export interface PipelineResult {
  success: boolean;
  message: string;
  details?: string;
}

// Parse pipeline YAML/config to extract stage names
function getPipelineStages(workspaceFolder: string): string[] {
  const ciConfigPath = path.join(workspaceFolder, '.yuleosh', 'ci-config.yaml');
  const dotOshConfig = path.join(workspaceFolder, '.yuleosh', 'config.yml');

  // Default stages
  const defaultStages = ['lint', 'build', 'test', 'review', 'deploy'];

  try {
    if (fs.existsSync(ciConfigPath)) {
      const content = fs.readFileSync(ciConfigPath, 'utf-8');
      const stageMatch = content.match(/stages:\s*\n((?:\s+- .+\n?)+)/);
      if (stageMatch) {
        return stageMatch[1]
          .split('\n')
          .map(l => l.replace(/^\s*-\s*/, '').trim())
          .filter(Boolean);
      }
    }
  } catch (e) {
    // ignore
  }

  return defaultStages;
}

export class PipelineManager {
  private _status: PipelineStatus = {
    running: false,
    success: false,
    message: 'Idle',
    stages: getPipelineStages('').map(name => ({ name, status: 'pending' })),
  };
  private _onDidChangeStatus = new vscode.EventEmitter<PipelineStatus>();
  readonly onDidChangeStatus: vscode.Event<PipelineStatus> =
    this._onDidChangeStatus.event;

  private _onDidChangeStages = new vscode.EventEmitter<StageStatus[]>();
  readonly onDidChangeStages: vscode.Event<StageStatus[]> =
    this._onDidChangeStages.event;

  private currentProcess: import('child_process').ChildProcess | null = null;
  private refreshTimer: NodeJS.Timeout | null = null;

  getStatus(): PipelineStatus {
    return { ...this._status, stages: [...this._status.stages] };
  }

  /** Start 30s auto-refresh (VSC-3) */
  startAutoRefresh(intervalMs: number = 30000): void {
    this.stopAutoRefresh();
    this.refreshTimer = setInterval(() => {
      // Reload pipeline status from disk if available
      this._onDidChangeStatus.fire(this._status);
      this._onDidChangeStages.fire(this._status.stages);
    }, intervalMs);
  }

  stopAutoRefresh(): void {
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }
  }

  cancel(): void {
    if (this.currentProcess) {
      this.currentProcess.kill('SIGINT');
      this.currentProcess = null;
    }
    this._status.running = false;
    this._status.message = 'Cancelled';
    this._status.stages = this._status.stages.map(s => ({
      ...s,
      status: s.status === 'running' ? 'skipped' as const : s.status,
    }));
    this._onDidChangeStatus.fire(this._status);
    this._onDidChangeStages.fire(this._status.stages);
  }

  async runPipeline(workspaceFolder: string): Promise<PipelineResult> {
    this._status.running = true;
    this._status.message = 'Running pipeline...';
    this._status.lastRun = new Date();

    // Initialize stages
    const stageNames = getPipelineStages(workspaceFolder);
    this._status.stages = stageNames.map(name => ({
      name,
      status: 'pending' as const,
    }));
    this._onDidChangeStatus.fire(this._status);
    this._onDidChangeStages.fire(this._status.stages);

    try {
      const cmd = `yuleosh pipeline run "${workspaceFolder}"`;
      const { stdout, stderr } = await execAsync(cmd, {
        cwd: workspaceFolder,
        timeout: 300000, // 5 min timeout
      });

      const output = stdout + stderr;

      // Try to parse stage status from output
      this._status.stages = this._status.stages.map(s => {
        const lower = s.name.toLowerCase();
        if (output.includes(`${lower}: pass`) || output.includes(`${lower} passed`) || output.includes(`${lower}: ✓`)) {
          return { ...s, status: 'pass' as const, endTime: new Date() };
        }
        if (output.includes(`${lower}: fail`) || output.includes(`${lower} failed`) || output.includes(`${lower}: ✗`)) {
          return { ...s, status: 'fail' as const, endTime: new Date() };
        }
        // Default: assume passed if no explicit failure
        return { ...s, status: 'pass' as const, endTime: new Date() };
      });

      // If all stages passed, it's a success
      const allPassed = this._status.stages.every(s => s.status === 'pass');

      this._status.success = allPassed;
      this._status.running = false;
      this._status.message = allPassed ? 'Pipeline passed' : 'Pipeline completed with warnings';
      this._status.details = output;
      this._onDidChangeStatus.fire(this._status);
      this._onDidChangeStages.fire(this._status.stages);

      return { success: allPassed, message: 'Pipeline completed', details: output };
    } catch (err: any) {
      const errorOutput = (err.stdout || '') + (err.stderr || '') + (err.message || '');

      // Mark running stages as failed
      this._status.stages = this._status.stages.map(s => ({
        ...s,
        status: s.status === 'running' ? 'fail' as const : s.status,
        log: s.status === 'running' ? errorOutput.substring(0, 500) : s.log,
        endTime: s.status === 'running' ? new Date() : s.endTime,
      }));

      this._status.success = false;
      this._status.running = false;
      this._status.message = err.message || 'Pipeline failed';
      this._status.details = errorOutput;
      this._onDidChangeStatus.fire(this._status);
      this._onDidChangeStages.fire(this._status.stages);

      return {
        success: false,
        message: err.message || 'Pipeline failed',
        details: errorOutput,
      };
    }
  }

  /** Load pipeline log from .yuleosh/reports/ */
  getStageLog(stageName: string, workspaceFolder: string): string | undefined {
    const logPaths = [
      path.join(workspaceFolder, '.yuleosh', 'reports', `${stageName}.log`),
      path.join(workspaceFolder, '.yuleosh', 'reports', `${stageName}-report.md`),
      path.join(workspaceFolder, '.yuleosh', 'reports', `${stageName}-report.json`),
    ];

    for (const logPath of logPaths) {
      try {
        if (fs.existsSync(logPath)) {
          return fs.readFileSync(logPath, 'utf-8');
        }
      } catch (e) {
        // continue
      }
    }

    // Fall back to details stored in memory
    return this._status.details;
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
    this.stopAutoRefresh();
    this._onDidChangeStatus.dispose();
    this._onDidChangeStages.dispose();
  }
}
