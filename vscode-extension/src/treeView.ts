import * as vscode from 'vscode';
import { PipelineManager, PipelineStatus } from './pipeline';

// ---------------------------------------------------------------------------
// Pipeline Tree View
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
  }

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: PipelineTreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(_element?: PipelineTreeItem): Thenable<PipelineTreeItem[]> {
    const status = this.pipelineManager.getStatus();
    const items: PipelineTreeItem[] = [];

    // Status indicator
    const statusIcon = status.running
      ? '$(sync~spin)'
      : status.success
      ? '$(pass-filled)'
      : '$(error)';
    items.push(
      new PipelineTreeItem(
        `${statusIcon} ${status.running ? 'Running' : status.success ? 'Passed' : 'Failed'}`,
        status.running
          ? vscode.TreeItemCollapsibleState.None
          : vscode.TreeItemCollapsibleState.None,
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

    return Promise.resolve(items);
  }
}

class PipelineTreeItem extends vscode.TreeItem {
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
        '$(dashboard) Open Dashboard',
        vscode.TreeItemCollapsibleState.None,
        {
          command: 'yuleosh.openDashboard',
          title: 'Open Dashboard',
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
