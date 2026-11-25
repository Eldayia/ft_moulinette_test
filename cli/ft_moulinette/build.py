"""Observe Makefile postconditions inside the temporary project copy."""


def check_build(project, execute, add, timeout, archive_name='libft.a'):
    archive = project / archive_name
    healthy = True
    for rule in ('fclean', 'all', archive_name, 'clean', 'all', 're', 'fclean', 'all'):
        code, output = execute(['make', rule], project, timeout)
        add('Makefile', 'make:' + rule, 'fail' if code else 'pass', output or 'OK')
        if code:
            healthy = False
            break
        objects = list(project.rglob('*.o'))
        errors = []
        if rule in ('clean', 'fclean') and objects:
            errors.append('Les fichiers objets subsistent')
        if rule == 'fclean' and archive.exists():
            errors.append(archive_name+' subsiste après fclean')
        if rule in ('all', archive_name, 're', 'clean') and not archive.is_file():
            errors.append(archive_name+' absent')
        add('Makefile', 'postcondition:' + rule, 'fail' if errors else 'pass', '; '.join(errors) or 'État des fichiers conforme')
        healthy = healthy and not errors
    return healthy


def check_rebuilds(project, execute, add, timeout, archive_name='libft.a'):
    """Touch inputs and require their object/archive to be rebuilt."""
    import os
    archive=project/archive_name
    for source in [*sorted(project.rglob('*.c')), *sorted(project.rglob('*.h'))]:
        before=archive.stat().st_mtime_ns if archive.exists() else 0
        objects={p:p.stat().st_mtime_ns for p in project.rglob('*.o')}
        newest=max([before,*objects.values(),source.stat().st_mtime_ns])
        os.utime(source,ns=(newest+1,newest+1))
        code,out=execute(['make'],project,timeout)
        changed=archive.exists() and archive.stat().st_mtime_ns!=before
        rebuilt=any(p.exists() and p.stat().st_mtime_ns!=stamp for p,stamp in objects.items())
        add('Makefile','rebuild:'+source.name,'pass' if not code and changed and rebuilt else 'fail',out or 'Recompilation et mise à jour archive requises')
