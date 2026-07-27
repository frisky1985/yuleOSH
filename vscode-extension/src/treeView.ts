import * as vscode from 'vscode';
import * as path from 'path';
import { PipelineManager, PipelineStatus, StageStatus } from './pipeline';

// ---------------------------------------------------------------------------
// Pipeline Tree View — VSC-3: Stage status, auto-refresh, click-to-view-log
// ---------------------------------------------------------------------------

export class PipelineTreeDataProvider
  implements vscode.TreeDataProvider<PipelineTreeItem>
{
  private _onDidChangeTreeData = new vscode.EventEmitter<
    void | PipelineTreeItem
  >();
  readonly onDidChangeTreeData: vscode.Event<void | PipelineTreeItem> =
    this._onDidChangeTreeData.event;

  constructor(private pipelineManager: PipelineManager) {
    pipelineManager.onDidChangeStatus(() => this.refresh());
    pipelineManager.onDidChangeStages(() => this.refresh());
    // Start 30s auto-refresh
    pipelineManager.startAutoRefresh(30000);
  }

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: PipelineTreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: PipelineTreeItem): Thenable<PipelineTreeItem[]> {
    if (element) {
      // If element has children (stages), return them
      if (element.children) {
        const stages: StageStatus[] = element.children as StageStatus[];
        return Promise.resolve(stages.map(s => {
          const statusIcon = s.status === 'running' ? '$(sync~spin)' :
            s.status === 'pass' ? '$(pass-filled)' :
            s.status === 'fail' ? '$(error)' :
            s.status === 'skipped' ? '$(circle-slash)' : '$(circle-outline)';

          // Format timing
          let timeInfo = '';
          if (s.startTime) timeInfo += ` started: ${s.startTime.toLocaleTimeString()}`;
          if (s.endTime) timeInfo += ` ended: ${s.endTime.toLocaleTimeString()}`;

          const item = new PipelineTreeItem(
            `${statusIcon} ${s.name}`,
            vscode.TreeItemCollapsibleState.None,
            {
              command: 'yuleosh.viewPipelineLog',
              title: 'View Stage Log',
              arguments: [s.name],
            }
          );
          item.description = s.status.toUpperCase() + timeInfo;
          item.tooltip = `Stage: ${s.name}\nStatus: ${s.status}\n${timeInfo}\nClick to view log`;
          item.contextValue = 'pipelineStage';
          return item;
        }));
      }
      return Promise.resolve([]);
    }

    // Root level
    const status = this.pipelineManager.getStatus();
    const items: PipelineTreeItem[] = [];

    // Overall pipeline status
    const statusIcon = status.running
      ? '$(sync~spin)'
      : status.success
      ? '$(pass-filled)'
      : '$(error)';

    items.push(
      new PipelineTreeItem(
        `${statusIcon} Pipeline: ${status.running ? 'Running...' : status.success ? 'Passed' : 'Failed'}`,
        vscode.TreeItemCollapsibleState.None,
        {
          command: 'yuleosh.viewStatus',
          title: 'View Status',
        }
      )
    );

    // Last run timestamp
    const lastRun = status.lastRun;
    items.push(
      new PipelineTreeItem(
        `Last Run: ${lastRun ? lastRun.toLocaleString() : 'Never'}`,
        vscode.TreeItemCollapsibleState.None
      )
    );

    // Message
    items.push(
      new PipelineTreeItem(
        `Message: ${status.message}`,
        vscode.TreeItemCollapsibleState.None
      )
    );

    // Stages section header
    if (status.stages.length > 0) {
      const stageItems = status.stages.map(s => {
        const stageIcon = s.status === 'running' ? '$(sync~spin)' :
          s.status === 'pass' ? '$(pass-filled)' :
          s.status === 'fail' ? '$(error)' :
          s.status === 'skipped' ? '$(circle-slash)' : '$(circle-outline)';
        return {
          name: s.name,
          status: s.status,
          startTime: s.startTime,
          endTime: s.endTime,
          label: `${stageIcon} ${s.name}`,
        };
      });

      const stagesHeader = new PipelineTreeItem(
        '$(list-tree) Stages',
        vscode.TreeItemCollapsibleState.Expanded
      );
      stagesHeader.description = `${status.stages.filter(s => s.status === 'pass').length}/${status.stages.length} passed`;
      stagesHeader.children = stageItems.map(s => {
        const item = new PipelineTreeItem(
          s.label,
          vscode.TreeItemCollapsibleState.None,
          {
            command: 'yuleosh.viewPipelineLog',
            title: 'View Stage Log',
            arguments: [s.name],
          }
        );
        item.description = s.status.toUpperCase();
        item.tooltip = `Stage: ${s.name}\nStatus: ${s.status}\nClick to view log`;
        item.contextValue = 'pipelineStage';
        return item;
      });
      items.push(stagesHeader);

      // Also add individual stage items for quick access
      // (The collapsible stages header already contains them)
    }

    return Promise.resolve(items);
  }
}

class PipelineTreeItem extends vscode.TreeItem {
  children?: vscode.TreeItem[] | StageStatus[];

  constructor(
    label: string,
    collapsibleState: vscode.TreeItemCollapsibleState,
    command?: vscode.Command
  ) {
    super(label, collapsibleState);
    this.command = command;
  }
}

// ---------------------------------------------------------------------------
// Reviews Tree View
// ---------------------------------------------------------------------------

export class ReviewsTreeDataProvider
  implements vscode.TreeDataProvider<ReviewTreeItem>
{
  private _onDidChangeTreeData = new vscode.EventEmitter<
    void | ReviewTreeItem
  >();
  readonly onDidChangeTreeData: vscode.Event<void | ReviewTreeItem> =
    this._onDidChangeTreeData.event;

  private reviews: ReviewEntry[] = [
    { file: 'main.c', issues: 3, status: 'warning', date: new Date() },
    { file: 'i2c_driver.c', issues: 0, status: 'passed', date: new Date() },
    { file: 'gpio.c', issues: 1, status: 'warning', date: new Date() },
  ];

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: ReviewTreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(_element?: ReviewTreeItem): Thenable<ReviewTreeItem[]> {
    return Promise.resolve(
      this.reviews.map((r) => {
        const icon =
          r.status === 'passed'
            ? '$(pass)'
            : r.status === 'warning'
            ? '$(warning)'
            : '$(error)';
        const label = `${icon} ${r.file}`;
        const item = new ReviewTreeItem(
          label,
          vscode.TreeItemCollapsibleState.None
        );
        item.description = `${r.issues} issue${r.issues !== 1 ? 's' : ''}`;
        item.tooltip = `${r.file}\nIssues: ${r.issues}\nStatus: ${r.status}\nReviewed: ${r.date.toLocaleString()}`;
        return item;
      })
    );
  }
}

interface ReviewEntry {
  file: string;
  issues: number;
  status: 'passed' | 'warning' | 'error';
  date: Date;
}

class ReviewTreeItem extends vscode.TreeItem {
  constructor(
    label: string,
    collapsibleState: vscode.TreeItemCollapsibleState
  ) {
    super(label, collapsibleState);
  }
}

// ---------------------------------------------------------------------------
// Actions Tree View
// ---------------------------------------------------------------------------

export class ActionsTreeDataProvider
  implements vscode.TreeDataProvider<ActionTreeItem>
{
  getTreeItem(element: ActionTreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(_element?: ActionTreeItem): Thenable<ActionTreeItem[]> {
    const actions: ActionTreeItem[] = [
      new ActionTreeItem(
        '$(play) Run Pipeline',
        vscode.TreeItemCollapsibleState.None,
        {
          command: 'yuleosh.runPipeline',
          title: 'Run Pipeline',
        }
      ),
      new ActionTreeItem(
        '$(check) Check MISRA',
        vscode.TreeItemCollapsibleState.None,
        {
          command: 'yuleosh.checkMisra',
          title: 'Check MISRA',
        }
      ),
      new ActionTreeItem(
        '$(tools) Run CI',
        vscode.TreeItemCollapsibleState.None,
        {
          command: 'yuleosh.runCi',
          title: 'Run CI',
        }
      ),
      new ActionTreeItem(
        '$(dashboard) Show Dashboard',
        vscode.TreeItemCollapsibleState.None,
        {
          command: 'yuleosh.showDashboard',
          title: 'Show Dashboard',
        }
      ),
      new ActionTreeItem(
        '$(file) View Evidence',
        vscode.TreeItemCollapsibleState.None,
        {
          command: 'yuleosh.viewEvidence',
          title: 'View Evidence Report',
        }
      ),
      new ActionTreeItem(
        '$(circuit-board) Flash Device',
        vscode.TreeItemCollapsibleState.None,
        {
          command: 'yuleosh.flashDevice',
          title: 'Flash Device',
        }
      ),
      new ActionTreeItem(
        '$(info) View Status',
        vscode.TreeItemCollapsibleState.None,
        {
          command: 'yuleosh.viewStatus',
          title: 'View Status',
        }
      ),
    ];

    return Promise.resolve(actions);
  }
}

class ActionTreeItem extends vscode.TreeItem {
  constructor(
    label: string,
    collapsibleState: vscode.TreeItemCollapsibleState,
    command?: vscode.Command
  ) {
    super(label, collapsibleState);
    this.command = command;
  }
}
