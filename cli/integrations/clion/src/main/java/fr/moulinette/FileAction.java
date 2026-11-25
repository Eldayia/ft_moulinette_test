package fr.moulinette;
import com.intellij.openapi.actionSystem.AnAction;
import com.intellij.openapi.actionSystem.AnActionEvent;
import com.intellij.openapi.actionSystem.CommonDataKeys;
public final class FileAction extends AnAction {
    @Override public void actionPerformed(AnActionEvent event) {
        var project = event.getProject();
        var file = event.getData(CommonDataKeys.VIRTUAL_FILE);
        if (project != null && file != null && !file.isDirectory()) Runner.run(project, file.getPath());
    }
}
