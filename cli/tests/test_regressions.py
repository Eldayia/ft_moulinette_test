import subprocess
import tempfile
import unittest
from pathlib import Path
from ft_moulinette.engine import run

class RegressionTests(unittest.TestCase):
    def project(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return Path(temp.name)

    def test_static_global(self):
        root = self.project()
        (root/'libft.h').write_text('#include <stddef.h>\nsize_t ft_strlen(const char *);')
        (root/'ft_strlen.c').write_text('#include "libft.h"\nstatic size_t counter;size_t ft_strlen(const char *s){counter=0;while(s[counter])counter++;return counter;}')
        rows = run(root/'ft_strlen.c', False, False, 1, 42, 3, False)
        self.assertTrue(any(r['check']=='symbols' and r['status']=='fail' for r in rows))

    def test_empty_archive_is_not_functional(self):
        root = self.project()
        (root/'libft.h').write_text('#include <stddef.h>\nsize_t ft_strlen(const char *);')
        (root/'ft_strlen.c').write_text('#include "libft.h"\nsize_t ft_strlen(const char *s){size_t n=0;while(s[n])n++;return n;}')
        (root/'Makefile').write_text('all: libft.a\nlibft.a:\n\tar rcs libft.a\nclean:\n\t@true\nfclean:\n\trm -f libft.a\nre: fclean all\n')
        rows = run(root, False, False, 1, 42, 3, True)
        self.assertTrue(any(r['check']=='functional' and r['status']=='pass' for r in rows))
        self.assertTrue(any(r['check']=='archive:link' and r['status']=='blocked' for r in rows))
        self.assertFalse((root/'libft.a').exists())

    def test_lstmap_failure_cleanup(self):
        root = self.project()
        (root/'libft.h').write_text('typedef struct s_list {void *content;struct s_list *next;} t_list;\nt_list *ft_lstmap(t_list *,void *(*)(void *),void (*)(void *));')
        body = '''#include "libft.h"
#include <stdlib.h>
t_list *ft_lstmap(t_list *p,void *(*f)(void *),void (*del)(void *)) {
 t_list *head=NULL,**tail=&head;
 while(p) {
  void *content=f(p->content);
  t_list *n=malloc(sizeof(*n));
  if(!n) {
   del(content);
   while(head){t_list *next=head->next;del(head->content);free(head);head=next;}
   return NULL;
  }
  n->content=content;n->next=NULL;*tail=n;tail=&n->next;p=p->next;
 }
 return head;
}'''
        (root/'ft_lstmap.c').write_text(body)
        rows=run(root/'ft_lstmap.c',False,False,1,42,3,False)
        allocations=[r for r in rows if r['check'].startswith('allocation:')]
        self.assertEqual(len(allocations),3)
        self.assertTrue(all(r['status']=='pass' for r in allocations), allocations)
        (root/'ft_lstmap.c').write_text(body.replace('del(content);','/* intentional leak */'))
        rows=run(root/'ft_lstmap.c',False,False,1,42,3,False)
        self.assertTrue(any(r['check'].startswith('allocation:') and r['status']=='fail' for r in rows))

    def test_clean_noop_rejected(self):
        root = self.project()
        (root/'Makefile').write_text('all: libft.a\nlibft.a:\n\ttouch stray.o\n\tar rcs libft.a\nclean:\n\t@true\nfclean:\n\trm -f *.o libft.a\nre: fclean all\n')
        rows = run(root, False, False, 1, 42, 3, True)
        self.assertTrue(any(r['check']=='postcondition:clean' and r['status']=='fail' for r in rows))

    def test_valgrind_detects_leak(self):
        import shutil
        if not shutil.which('valgrind') or subprocess.run(['valgrind', '--quiet', '/bin/true'], capture_output=True).returncode:
            self.skipTest('Valgrind indisponible')
        root = self.project()
        (root/'libft.h').write_text('#include <stddef.h>\nsize_t ft_strlen(const char *);')
        (root/'ft_strlen.c').write_text('#include "libft.h"\n#include <stdlib.h>\nsize_t ft_strlen(const char *s){size_t n=0;void *p=malloc(16);if(!p)return 0;while(s[n])n++;return n;}')
        rows = run(root/'ft_strlen.c', False, True, 1, 42, 3, False)
        self.assertTrue(any(r['check']=='functional' and r['status']=='pass' for r in rows))
        self.assertTrue(any(r['check']=='memory' and r['status']=='fail' for r in rows))

    def test_valgrind_detects_read_past_bound(self):
        import shutil
        if not shutil.which('valgrind') or subprocess.run(['valgrind', '--quiet', '/bin/true'], capture_output=True).returncode:
            self.skipTest('Valgrind indisponible')
        root = self.project()
        (root/'libft.h').write_text('#include <stddef.h>\nint ft_memcmp(const void *,const void *,size_t);')
        (root/'ft_memcmp.c').write_text('''#include "libft.h"
int ft_memcmp(const void *a,const void *b,size_t n){
 const unsigned char *p=a,*q=b;
 for(size_t i=0;i<n;i++)if(p[i]!=q[i])return p[i]-q[i];
 volatile unsigned char beyond=p[n];(void)beyond;
 return 0;
}''')
        rows = run(root/'ft_memcmp.c', False, True, 1, 42, 3, False)
        self.assertTrue(any(r['check']=='memory' and r['status']=='fail' for r in rows))
