// Copyright (c) 2025 frisky1985
// SPDX-License-Identifier: MIT

/**
 * yuleOSH VS Code Extension — MISRA Real-Time Violation Provider
 *
 * Provides inline MISRA violation decorations and a tree view for
 * the active editor's MISRA violations.
 *
 * Integration:
 * - Parses .yuleosh/reports/misra-report.json from the workspace
 * - Decorates violating lines with red/yellow squiggles
 * - Hover provider shows rule details
 * - Tree view shows all violations grouped by severity
 */

import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";

// ── Types ──────────────────────────────────────────────────────────────────

interface MisraViolation {
    file: string;
    line: number;
    column: number;
    severity: string;
    message: string;
    rule_id: string;
}

interface MisraReport {
    generated_at: string;
    violations_raw: MisraViolation[];
    groups: Record<string, {
        rule_id: string;
        title: string;
        severity_category: string;
        count: number;
        violations: MisraViolation[];
    }>;
}

// ── MISRA Report Loader ─────────────────────────────────────────────────────

class MisraReportLoader {
    private report: MisraReport | null = null;
    private watcher: vscode.FileSystemWatcher | null = null;

    /**
     * Load the MISRA report from the workspace.
     * Searches for .yuleosh/reports/misra-report.json
     */
    load(): MisraReport | null {
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders) return null;

        for (const folder of workspaceFolders) {
            // Try multiple possible locations
            const candidates = [
                path.join(folder.uri.fsPath, ".yuleosh", "reports", "misra-report.json"),
                path.join(folder.uri.fsPath, "reports", "misra-report.json"),
                path.join(folder.uri.fsPath, "build", "reports", "misra-report.json"),
            ];

            for (const candidate of candidates) {
                if (fs.existsSync(candidate)) {
                    try {
                        const content = fs.readFileSync(candidate, "utf-8");
                        this.report = JSON.parse(content);
                        return this.report;
                    } catch (e) {
                        console.error(`Failed to parse MISRA report: ${candidate}`, e);
                    }
                }
            }
        }

        return null;
    }

    /**
     * Get violations for a specific file.
     */
    getViolationsForFile(filePath: string): MisraViolation[] {
        if (!this.report) return [];

        const normalized = filePath.replace(/\\/g, "/");
        const violations: MisraViolation[] = [];

        for (const v of this.report.violations_raw || []) {
            const vFile = v.file.replace(/\\/g, "/");
            if (normalized.endsWith(vFile) || normalized === vFile) {
                violations.push(v);
            }
        }

        return violations;
    }

    /**
     * Get all unique rule IDs in the report.
     */
    getAffectedRules(): string[] {
        if (!this.report) return [];
        return Object.keys(this.report.groups || {}).sort();
    }

    /**
     * Watch for report file changes to auto-reload.
     */
    startWatching(onChange: () => void): void {
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders) return;

        for (const folder of workspaceFolders) {
            const pattern = new vscode.RelativePattern(
                folder,
                ".yuleosh/reports/misra-report.json"
            );
            this.watcher = vscode.workspace.createFileSystemWatcher(pattern);
            this.watcher.onDidChange(() => {
                this.report = null; // Invalidate cache
                onChange();
            });
            this.watcher.onDidCreate(() => {
                this.report = null;
                onChange();
            });
        }
    }

    dispose(): void {
        if (this.watcher) {
            this.watcher.dispose();
            this.watcher = null;
        }
    }
}

// ── Hover Provider ─────────────────────────────────────────────────────────

class MisraHoverProvider implements vscode.HoverProvider {
    private loader: MisraReportLoader;

    constructor(loader: MisraReportLoader) {
        this.loader = loader;
    }

    provideHover(
        document: vscode.TextDocument,
        position: vscode.Position,
        _token: vscode.CancellationToken
    ): vscode.ProviderResult<vscode.Hover> {
        const violations = this.loader.getViolationsForFile(document.fileName);
        const line = position.line + 1; // 1-indexed

        const violating = violations.filter((v) => v.line === line);
        if (violating.length === 0) return null;

        const markdown = violating
            .map((v) => {
                const ruleId = v.rule_id || "unknown";
                const sev = v.severity;
                const emoji =
                    sev === "error" ? "❌" :
                    sev === "warning" ? "⚠️" :
                    sev === "style" ? "🎨" : "ℹ️";
                return `**${emoji} MISRA ${ruleId}** (${sev})\n\n${v.message}`;
            })
            .join("\n\n---\n\n");

        return new vscode.Hover(
            new vscode.MarkdownString(markdown)
        );
    }
}

// ── Code Lens Provider ─────────────────────────────────────────────────────

class MisraCodeLensProvider implements vscode.CodeLensProvider {
    private loader: MisraReportLoader;
    private _onDidChangeCodeLenses = new vscode.EventEmitter<void>();

    get onDidChangeCodeLenses(): vscode.Event<void> {
        return this._onDidChangeCodeLenses.event;
    }

    constructor(loader: MisraReportLoader) {
        this.loader = loader;
    }

    provideCodeLenses(
        document: vscode.TextDocument,
        _token: vscode.CancellationToken
    ): vscode.ProviderResult<vscode.CodeLens[]> {
        const violations = this.loader.getViolationsForFile(document.fileName);
        if (violations.length === 0) return [];

        const lenses: vscode.CodeLens[] = [];

        // Count total violations for this file
        const errorCount = violations.filter((v) => v.severity === "error").length;
        const warningCount = violations.filter((v) => v.severity === "warning").length;
        const styleCount = violations.filter((v) => v.severity === "style").length;

        // Add a summary line at the top
        const summaryLine = new vscode.CodeLens(
            new vscode.Range(0, 0, 0, 0),
            {
                title: `MISRA: ${violations.length} violation(s) — ❌${errorCount} ⚠️${warningCount} 🎨${styleCount}`,
                command: "yuleosh.showMisraProblems",
                arguments: [],
                tooltip: "Click to open MISRA problems panel",
            }
        );
        lenses.push(summaryLine);

        return lenses;
    }
}

// ── Tree Data Provider ─────────────────────────────────────────────────────

class MisraTreeItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState,
        public readonly violation?: MisraViolation,
        public readonly children?: MisraTreeItem[]
    ) {
        super(label, collapsibleState);

        if (violation) {
            this.tooltip = `${violation.rule_id}: ${violation.message}`;
            this.description = `Line ${violation.line}`;

            if (violation.severity === "error") {
                this.iconPath = new vscode.ThemeIcon("error", new vscode.ThemeColor("errorForeground"));
            } else if (violation.severity === "warning") {
                this.iconPath = new vscode.ThemeIcon("warning", new vscode.ThemeColor("warningForeground"));
            } else {
                this.iconPath = new vscode.ThemeIcon("info");
            }

            this.command = {
                command: "vscode.open",
                title: "Open file",
                arguments: [
                    vscode.Uri.file(violation.file),
                    { selection: new vscode.Range(violation.line - 1, 0, violation.line - 1, 0) },
                ],
            };
        }
    }
}

class MisraTreeDataProvider implements vscode.TreeDataProvider<MisraTreeItem> {
    private loader: MisraReportLoader;
    private _onDidChangeTreeData = new vscode.EventEmitter<MisraTreeItem | undefined>();

    readonly onDidChangeTreeData: vscode.Event<MisraTreeItem | undefined> =
        this._onDidChangeTreeData.event;

    constructor(loader: MisraReportLoader) {
        this.loader = loader;
    }

    refresh(): void {
        this._onDidChangeTreeData.fire(undefined);
    }

    getTreeItem(element: MisraTreeItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: MisraTreeItem): MisraTreeItem[] {
        if (!element) {
            // Root level: group by file
            const report = this.loader.load();
            if (!report) {
                return [
                    new MisraTreeItem(
                        "No MISRA report found. Run `yuleosh misra` first.",
                        vscode.TreeItemCollapsibleState.None
                    ),
                ];
            }

            const fileGroup: Record<string, MisraViolation[]> = {};
            for (const v of report.violations_raw || []) {
                if (!fileGroup[v.file]) fileGroup[v.file] = [];
                fileGroup[v.file].push(v);
            }

            return Object.entries(fileGroup)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([file, violations]) => {
                    const errorCount = violations.filter(v => v.severity === "error").length;
                    const warningCount = violations.filter(v => v.severity === "warning").length;
                    const shortFile = file.split("/").pop() || file;
                    return new MisraTreeItem(
                        `${shortFile}  (${violations.length})`,
                        vscode.TreeItemCollapsibleState.Collapsed,
                        undefined,
                        violations.map(v => new MisraTreeItem(
                            `${v.rule_id || "unknown"}: ${v.message.substring(0, 60)}`,
                            vscode.TreeItemCollapsibleState.None,
                            v
                        ))
                    );
                });
        }

        return element.children || [];
    }
}

// ── Activation ─────────────────────────────────────────────────────────────

export function activate(context: vscode.ExtensionContext) {
    console.log("yuleOSH MISRA Provider activated");

    const loader = new MisraReportLoader();

    // Register hover provider
    const hoverProvider = vscode.languages.registerHoverProvider(
        { scheme: "file", language: "c" },
        new MisraHoverProvider(loader)
    );
    context.subscriptions.push(hoverProvider);

    // Register hover provider for C++
    const hoverProviderCpp = vscode.languages.registerHoverProvider(
        { scheme: "file", language: "cpp" },
        new MisraHoverProvider(loader)
    );
    context.subscriptions.push(hoverProviderCpp);

    // Register code lens provider
    const codeLensProvider = vscode.languages.registerCodeLensProvider(
        [{ scheme: "file", language: "c" }, { scheme: "file", language: "cpp" }],
        new MisraCodeLensProvider(loader)
    );
    context.subscriptions.push(codeLensProvider);

    // Register tree data provider
    const treeDataProvider = new MisraTreeDataProvider(loader);
    const treeView = vscode.window.createTreeView("yuleosh-misra-violations", {
        treeDataProvider,
        showCollapseAll: true,
    });
    context.subscriptions.push(treeView);

    // Register command to reload MISRA report
    const reloadCommand = vscode.commands.registerCommand("yuleosh.reloadMisraReport", () => {
        loader.load();
        treeDataProvider.refresh();
        vscode.window.showInformationMessage("MISRA report reloaded");
    });
    context.subscriptions.push(reloadCommand);

    // Register command to show MISRA problems
    const showProblemsCommand = vscode.commands.registerCommand(
        "yuleosh.showMisraProblems",
        () => {
            vscode.commands.executeCommand("workbench.view.extension.yuleosh-misra");
        }
    );
    context.subscriptions.push(showProblemsCommand);

    // Watch for report changes
    loader.startWatching(() => {
        treeDataProvider.refresh();
    });

    // Initial load
    loader.load();

    // Register decoration provider for inline squiggles
    const decorationType = vscode.window.createTextEditorDecorationType({
        isWholeLine: true,
        overviewRulerColor: new vscode.ThemeColor("editorOverviewRuler.warningForeground"),
        overviewRulerLane: vscode.OverviewRulerLane.Right,
        light: {
            backgroundColor: "rgba(255, 200, 0, 0.07)",
        },
        dark: {
            backgroundColor: "rgba(255, 200, 0, 0.07)",
        },
    });

    const errorDecorationType = vscode.window.createTextEditorDecorationType({
        isWholeLine: true,
        overviewRulerColor: new vscode.ThemeColor("editorOverviewRuler.errorForeground"),
        overviewRulerLane: vscode.OverviewRulerLane.Right,
        light: {
            backgroundColor: "rgba(255, 0, 0, 0.05)",
        },
        dark: {
            backgroundColor: "rgba(255, 50, 50, 0.08)",
        },
    });

    function updateDecorations() {
        const editor = vscode.window.activeTextEditor;
        if (!editor) return;

        const violations = loader.getViolationsForFile(editor.document.fileName);

        const warningDecorations: vscode.DecorationOptions[] = [];
        const errorDecorations: vscode.DecorationOptions[] = [];

        for (const v of violations) {
            const line = v.line - 1; // 0-indexed
            if (line < 0 || line >= editor.document.lineCount) continue;

            const range = editor.document.lineAt(line).range;
            const decoration: vscode.DecorationOptions = {
                range,
                hoverMessage: new vscode.MarkdownString(
                    `**MISRA ${v.rule_id || "unknown"}** (${v.severity})\n\n${v.message}`
                ),
            };

            if (v.severity === "error") {
                errorDecorations.push(decoration);
            } else {
                warningDecorations.push(decoration);
            }
        }

        editor.setDecorations(decorationType, warningDecorations);
        editor.setDecorations(errorDecorationType, errorDecorations);
    }

    context.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor(updateDecorations)
    );
    context.subscriptions.push(
        vscode.workspace.onDidChangeTextDocument(() => {
            // Debounce: re-decorate after a short delay
            setTimeout(updateDecorations, 500);
        })
    );

    // Initial decoration
    setTimeout(updateDecorations, 1000);
}

export function deactivate() {
    console.log("yuleOSH MISRA Provider deactivated");
}
