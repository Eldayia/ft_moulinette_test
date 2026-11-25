const vscode = require('vscode');
const { execFile } = require('child_process');
exports.activate = function (context) {
  const diagnostics = vscode.languages.createDiagnosticCollection('ft-moulinette');
  const output = vscode.window.createOutputChannel('Moulinette');
  context.subscriptions.push(diagnostics, output);
  for (const scope of ['project', 'file']) {
    context.subscriptions.push(vscode.commands.registerCommand('ftMoulinette.' + scope, async () => {
      if (!await vscode.workspace.saveAll()) return;
      let target;
      if (scope === 'file') target = vscode.window.activeTextEditor?.document.uri.fsPath;
      else target = (await vscode.window.showWorkspaceFolderPick())?.uri.fsPath;
      if (!target) return;
      const executable = vscode.workspace.getConfiguration('ftMoulinette').get('executable');
      output.show(true);
      output.appendLine('Test : ' + target);
      execFile(executable, [target, '--json'], { maxBuffer: 16 * 1024 * 1024 }, (error, stdout, stderr) => {
        let report;
        try { report = JSON.parse(stdout); } catch (_) { output.appendLine(stderr || String(error)); return; }
        diagnostics.clear();
        const grouped = new Map();
        for (const row of report.results) {
          output.appendLine(`${row.status} [${row.check}] ${row.file}: ${row.message}`);
          if (['pass', 'skip', 'manual', 'reviewed'].includes(row.status)) continue;
          for (const detail of row.diagnostics || [row]) {
            const items = grouped.get(detail.file) || [];
            const line = Math.max(0, detail.line - 1);
            const column = Math.max(0, (detail.column || 1) - 1);
            const severity = ['fail', 'blocked', 'missing'].includes(row.status)
              ? vscode.DiagnosticSeverity.Error : vscode.DiagnosticSeverity.Warning;
            items.push(new vscode.Diagnostic(new vscode.Range(line, column, line, column),
              `[${row.check}] ${detail.message}`, severity));
            grouped.set(detail.file, items);
          }
        }
        for (const [file, items] of grouped) diagnostics.set(vscode.Uri.file(file), items);
      });
    }));
  }
};
