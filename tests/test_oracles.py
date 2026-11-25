"""Execute libc-compatible harnesses against libc, then deliberate mutants."""
import tempfile
import unittest
from pathlib import Path
from ft_moulinette.engine import execute
from ft_moulinette.cases import CASES, PRELUDE
from test_harnesses import HEADER, PROTOTYPES
from references import REFERENCES

WRAPPERS = {
 'strlen':'size_t ft_strlen(const char *s){return strlen(s);}',
 'memset':'void *ft_memset(void *p,int c,size_t n){return memset(p,c,n);}',
 'bzero':'void ft_bzero(void *p,size_t n){memset(p,0,n);}',
 'memcpy':'void *ft_memcpy(void *p,const void *s,size_t n){return memcpy(p,s,n);}',
 'memmove':'void *ft_memmove(void *p,const void *s,size_t n){return memmove(p,s,n);}',
 'strchr':'char *ft_strchr(const char *s,int c){return (char *)strchr(s,c);}',
 'strrchr':'char *ft_strrchr(const char *s,int c){return (char *)strrchr(s,c);}',
 'strncmp':'int ft_strncmp(const char *a,const char *b,size_t n){return strncmp(a,b,n);}',
 'memcmp':'int ft_memcmp(const void *a,const void *b,size_t n){return memcmp(a,b,n);}',
 'memchr':'void *ft_memchr(const void *p,int c,size_t n){return (void *)memchr(p,c,n);}',
 'atoi':'int ft_atoi(const char *s){return atoi(s);}',
 'strdup':'char *ft_strdup(const char *s){return strdup(s);}',
 'calloc':'void *ft_calloc(size_t n,size_t z){return calloc(n,z);}',
}
for name in ('isalpha','isdigit','isalnum','isascii','isprint','toupper','tolower'):
    boolean = '!!' if name.startswith('is') else ''
    WRAPPERS[name]=f'int ft_{name}(int c){{return {boolean}{name}(c);}}'

WRAPPERS.update({
 'putchar_fd': "void ft_putchar_fd(char c,int fd){write(fd,&c,1);}",
 'putstr_fd': "void ft_putstr_fd(char *s,int fd){write(fd,s,strlen(s));}",
 'putendl_fd': 'void ft_putendl_fd(char *s,int fd){dprintf(fd,"%s\\n",s);}',
 'putnbr_fd': 'void ft_putnbr_fd(int n,int fd){dprintf(fd,"%d",n);}',
 'itoa': 'char *ft_itoa(int n){char b[32];snprintf(b,sizeof(b),"%d",n);return strdup(b);}',
 'strmapi': 'char *ft_strmapi(const char *s,char (*f)(unsigned int,char)){char *p=strdup(s);if(p)for(unsigned i=0;p[i];i++)p[i]=f(i,s[i]);return p;}',
 'striteri': 'void ft_striteri(char *s,void (*f)(unsigned int,char *)){for(unsigned i=0;s[i];i++)f(i,&s[i]);}',
 'strjoin': 'char *ft_strjoin(const char *a,const char *b){size_t n=strlen(a)+strlen(b)+1;char *p=malloc(n);if(p)snprintf(p,n,"%s%s",a,b);return p;}',
 'substr': 'char *ft_substr(const char *s,unsigned int start,size_t n){size_t len=strlen(s);if(start>=len)return strdup("");if(n>len-start)n=len-start;char *p=malloc(n+1);if(p){memcpy(p,s+start,n);p[n]=0;}return p;}',
})

WRAPPERS.update(REFERENCES)

class OracleTests(unittest.TestCase):
    def test_reference_coverage(self):
        self.assertEqual(set(WRAPPERS), set(CASES))

    def check(self, name, source, success):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'libft.h').write_text(HEADER+';\n'.join(PROTOTYPES.values())+';\n')
            (root/'test.c').write_text(PRELUDE.replace('SEED','42')+'\n'+source+'\nint main(void){'+CASES[name].replace('ITERATIONS','50')+'\nreturn 0;}')
            code,out=execute(['cc','-Wall','-Wextra','-Werror',str(root/'test.c'),'-o',str(root/'test')],root)
            self.assertEqual(code,0,out)
            code,out=execute([str(root/'test')],root)
            self.assertEqual(code==0,success,out)
            if not success:
                self.assertTrue(out.strip(), f'{name}: échec sans explication')
                self.assertNotIn('Assertion `',out)
    def test_every_function_explains_failure(self):
        for name, prototype in PROTOTYPES.items():
            with self.subTest(function=name):
                body = '{}' if prototype.startswith('void ft_') else '{return 0;}'
                self.check(name,prototype+body,False)

    def test_reference_oracles(self):
        for name,source in WRAPPERS.items():
            with self.subTest(function=name): self.check(name,source,True)
    def test_mutants_rejected(self):
        mutants={
         'strlen':'size_t ft_strlen(const char *s){return strlen(s)+1;}',
         'isalpha':'int ft_isalpha(int c){return isalpha(c)?2:0;}',
         'strrchr':'char *ft_strrchr(const char *s,int c){return (char *)strchr(s,c);}',
         'memset':'void *ft_memset(void *p,int c,size_t n){memset(p,c,n);return (char*)p+1;}',
         'calloc':'void *ft_calloc(size_t n,size_t z){if(!n || !z)return NULL;return calloc(n,z);}',
        }
        mutants.update({
            'strlcpy': REFERENCES['strlcpy'].replace('return len;', 'return len+1;'),
            'strlcat': REFERENCES['strlcat'].replace('return a+b;', 'return b;'),
            'strnstr': REFERENCES['strnstr'].replace('if(!k)return (char*)s;', 'if(!k)return NULL;'),
            'strtrim': REFERENCES['strtrim'].replace('size_t a=strspn(s,set)', 'size_t a=0'),
            'lstsize': REFERENCES['lstsize'].replace('return n;', 'return n+1;'),
            'lstlast': 't_list *ft_lstlast(t_list *p){return p;}',
            'lstiter': 'void ft_lstiter(t_list *p,void (*f)(void *)){if(p)f(p->content);}',
        })
        for name,source in mutants.items():
            with self.subTest(function=name): self.check(name,source,False)
