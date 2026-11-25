import shutil
from .cases import CASES, PRELUDE, ALLOCATIONS, WRAP, LSTMAP_FAILURE


def test_function(name,file,links,work,project,execute,add,memory,iterations,seed,timeout,prefix=''):
    harness=work/'test.c'
    binary=work/'test'
    prelude=PRELUDE.replace('SEED',str(seed))
    def compile_body(body,wrapped=False):
        harness.write_text(prelude+body)
        command=['cc','-Wall','-Wextra','-Werror','-g','-O0','-I',str(project),str(harness),*map(str,links),'-o',str(binary)]
        if wrapped: command.append('-Wl,--wrap=malloc')
        return execute(command,work,timeout)
    def memory_run():
        return execute(['valgrind','--quiet','--leak-check=full','--show-leak-kinds=all','--errors-for-leak-kinds=all','--error-exitcode=99',str(binary)],work,max(timeout,30))
    code,out=compile_body('\nint main(void){'+CASES[name].replace('ITERATIONS',str(iterations))+'\nreturn 0;}')
    if code:
        add(file,prefix+'link','blocked',out); return
    code,out=execute([str(binary)],work,timeout)
    add(file,prefix+'functional','fail' if code else 'pass',out or f'Assertions réussies (seed={seed})')
    if memory and not code:
        if shutil.which('valgrind'):
            code,out=memory_run()
            add(file,prefix+'memory','fail' if code else 'pass',out or 'Aucune erreur mémoire détectée')
        else: add(file,prefix+'memory','unavailable','Valgrind absent')
    if name not in ALLOCATIONS and name!='lstmap': return
    count=3
    if name in ALLOCATIONS:
        cleanup='char **words=p;for(size_t i=0;words[i];i++)free(words[i]);free(words);' if name=='split' else 'free(p);'
        baseline=WRAP+'\nint main(void){void *p='+ALLOCATIONS[name]+';VERIFY(p,"L’appel témoin a renvoyé NULL avant toute simulation de panne malloc.");'+cleanup+'printf("%ld",allocation_index);return 0;}'
        code,out=compile_body(baseline,True)
        if not code: code,out=execute([str(binary)],work,timeout)
        if code or not out.strip().isdigit():
            add(file,prefix+'allocation:baseline','blocked',out or 'Le test témoin n’a fourni aucun décompte des allocations.'); return
        count=int(out.strip())
        if not count:
            add(file,prefix+'allocation:baseline','fail','Aucun malloc observé'); return
        if count>10000:
            add(file,prefix+'allocation:baseline','blocked','Plus de 10000 allocations sur une entrée courte'); return
    for failure in range(1,count+1):
        body=LSTMAP_FAILURE.replace('FAILURE',str(failure)) if name=='lstmap' else '\nint main(void){failure_index='+str(failure)+';void *p='+ALLOCATIONS[name]+';VERIFY(allocation_index >= failure_index,"Le malloc numéro %ld à tester n’a pas été atteint.",failure_index);VERIFY(p==NULL,"Essai : échec simulé du malloc numéro %ld. Attendu : NULL. Obtenu : un pointeur.",failure_index);return 0;}'
        code,out=compile_body(WRAP+body,True)
        if code:
            add(file,prefix+'allocation','unavailable',out); break
        code,out=memory_run() if memory and shutil.which('valgrind') else execute([str(binary)],work,timeout)
        add(file,prefix+'allocation:'+str(failure),'fail' if code else 'pass',out or 'Échec malloc correctement traité')
