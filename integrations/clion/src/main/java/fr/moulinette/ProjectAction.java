package fr.moulinette;
import com.intellij.openapi.actionSystem.AnAction;
import com.intellij.openapi.actionSystem.AnActionEvent;
public final class ProjectAction extends AnAction {
    @Override public void actionPerformed(AnActionEvent event) {
        var project = event.getProject();
        if (project != null && project.getBasePath() != null) Runner.run(project, project.getBasePath());
    }
}
