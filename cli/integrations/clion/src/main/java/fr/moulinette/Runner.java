package fr.moulinette;

import com.intellij.execution.configurations.GeneralCommandLine;
import com.intellij.execution.process.OSProcessHandler;
import com.intellij.execution.ui.ConsoleView;
import com.intellij.execution.filters.TextConsoleBuilderFactory;
import com.intellij.ide.util.PropertiesComponent;
import com.intellij.openapi.fileEditor.FileDocumentManager;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.ui.Messages;
import com.intellij.openapi.wm.ToolWindow;
import com.intellij.openapi.wm.ToolWindowManager;
import com.intellij.ui.content.ContentFactory;

final class Runner {
    static void run(Project project, String target) {
        PropertiesComponent settings = PropertiesComponent.getInstance(project);
        String executable = Messages.showInputDialog(project,
                "Chemin de ft-moulinette", "Moulinette", null,
                settings.getValue("moulinette.executable", "ft-moulinette"), null);
        if (executable == null || executable.isBlank()) return;
        settings.setValue("moulinette.executable", executable);
        FileDocumentManager.getInstance().saveAllDocuments();
        try {
            GeneralCommandLine command = new GeneralCommandLine(executable, target)
                    .withWorkDirectory(project.getBasePath());
            OSProcessHandler process = new OSProcessHandler(command);
            ConsoleView console = TextConsoleBuilderFactory.getInstance().createBuilder(project).getConsole();
            console.attachToProcess(process);
            ToolWindowManager manager = ToolWindowManager.getInstance(project);
            ToolWindow window = manager.getToolWindow("Moulinette");
            if (window == null) window = manager.registerToolWindow("Moulinette", true, com.intellij.openapi.wm.ToolWindowAnchor.BOTTOM);
            var content = ContentFactory.getInstance().createContent(console.getComponent(), target, false);
            content.setDisposer(() -> {
                if (!process.isProcessTerminated()) process.destroyProcess();
                console.dispose();
            });
            window.getContentManager().addContent(content);
            window.show();
            process.startNotify();
        } catch (Exception exception) {
            Messages.showErrorDialog(project, exception.getMessage(), "Moulinette");
        }
    }
}
