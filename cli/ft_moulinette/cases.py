"""Independent C assertions; only defined inputs are tested."""
FUNCTIONS = ('isalpha isdigit isalnum isascii isprint strlen memset bzero memcpy memmove strlcpy strlcat toupper tolower strchr strrchr strncmp memchr memcmp strnstr atoi calloc strdup substr strjoin strtrim split itoa strmapi striteri putchar_fd putstr_fd putendl_fd putnbr_fd lstnew lstadd_front lstsize lstlast lstadd_back lstdelone lstclear lstiter lstmap').split()
PRELUDE = r'''
#include "libft.h"
#include <assert.h>
#include <string.h>
#include <stdlib.h>
#include <stdint.h>
#include <limits.h>
#include <stdio.h>
#include <ctype.h>
#include <unistd.h>
static unsigned rng = SEED;
unsigned random_value(void) { rng = rng * 1664525u + 1013904223u; return rng; }
int signum(int n) { return (n > 0) - (n < 0); }
char mapper(unsigned i, char c) { return c + i % 3; }
void iterator(unsigned i, char *c) { *c = mapper(i, *c); }
void increment(void *p) { ++*(int *)p; }
void *duplicate(void *p) { int *q = malloc(sizeof(int)); if(q) *q = *(int *)p + 1; return q; }
void nothing(void *p) { (void)p; }

/* Keep each expression single-evaluation: some checks allocate or mutate memory. */
#define VERIFY(condition, ...) do { if (!(condition)) { fprintf(stderr, __VA_ARGS__); fputc('\n', stderr); exit(1); } } while (0)
#define NUMBER(call, expected, input) do { long long got_=(call), want_=(expected); VERIFY(got_==want_, "Essai : %s (paramètre %lld).\nAttendu : %lld.\nObtenu : %lld.", #call,(long long)(input),want_,got_); } while (0)
void compare_bytes(const void *actual,const void *expected,size_t count,size_t n) {
    const unsigned char *a=actual,*b=expected;
    for(size_t i=0;i<count;i++)
        VERIFY(a[i]==b[i],"Essai : taille demandée %zu. Premier écart à l’indice %zu.\nAttendu : octet %u.\nObtenu : octet %u.",n,i,(unsigned)b[i],(unsigned)a[i]);
}
void compare_text(const char *actual,const char *expected,const char *call) {
    VERIFY(actual,"Essai : %s.\nAttendu : chaîne « %s ».\nObtenu : NULL.",call,expected);
    if (!expected[0]) {
        VERIFY(actual[0]==0,"Essai : %s.\nAttendu : chaîne vide, un octet zéro à l’indice 0.\nObtenu : octet %u.\nPiste : alloue une place pour le zéro final et initialise-la, même pour une sous-chaîne vide.",call,(unsigned char)actual[0]);
        return;
    }
    for(size_t i=0;;i++) {
        VERIFY(actual[i]==expected[i],"Essai : %s.\nAttendu : chaîne « %s ».\nObtenu : à l’indice %zu, octet %u au lieu de %u.",call,expected,i,(unsigned char)actual[i],(unsigned char)expected[i]);
        if(!expected[i])return;
    }
}
#define eq(call,expected) do { char *value_=(call); compare_text(value_,expected,#call); free(value_); } while (0)

'''
PRELUDE += r"""
/* Describe an address relative to the tested buffer, including foreign pointers. */
void position(char *text, size_t size, void *ptr, void *buffer, size_t length) {
    if (!ptr) { snprintf(text, size, "NULL"); return; }
    for (size_t i = 0; i < length; ++i)
        if (ptr == (unsigned char *)buffer + i) {
            snprintf(text, size, "adresse de l’octet d’indice %zu", i);
            return;
        }
    snprintf(text, size, "adresse hors du tampon");
}
"""
CASES = {}
for name, expr in {'isalpha':"((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'))", 'isdigit':"(c >= '0' && c <= '9')", 'isalnum':"((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9'))", 'isascii':'(c >= 0 && c <= 127)', 'isprint':'(c >= 32 && c <= 126)'}.items():
    CASES[name] = f'for(int c=-1;c<=255;c++) NUMBER(ft_{name}(c),{expr},c);'
for name in ['toupper','tolower']:
    CASES[name] = f'for(int c=-1;c<=255;c++) NUMBER(ft_{name}(c),{name}(c),c);'
CASES.update({
'strlen': 'char s[1025]; for(int n=0;n<1025;n++){memset(s,65,n);s[n]=0;NUMBER(ft_strlen(s),n,n);}',
'memset': 'for(int n=0;n<128;n++){unsigned char a[130],b[130];memset(a,42,130);memset(b,42,130);VERIFY(ft_memset(a+1,511,n)==a+1,"Le pointeur renvoyé doit être l’adresse de début de la destination.");memset(b+1,511,n);compare_bytes(a,b,130,n);}',
'bzero': 'for(int n=0;n<128;n++){char a[130],b[130];memset(a,42,130);memset(b,42,130);ft_bzero(a+1,n);memset(b+1,0,n);compare_bytes(a,b,130,n);}',
'memcpy': 'for(int n=0;n<128;n++){char a[130],b[130],s[128];for(int i=0;i<128;i++)s[i]=random_value();memset(a,42,130);memset(b,42,130);VERIFY(ft_memcpy(a+1,s,n)==a+1,"Le pointeur renvoyé doit être l’adresse de début de la destination.");memcpy(b+1,s,n);compare_bytes(a,b,130,n);}',
 'memmove': r"""
for (int dst=0; dst<32; ++dst) for (int src=0; src<32; ++src) for (int n=0; n<32; ++n) {
    unsigned char actual[64], expected[64];
    for (int i=0; i<64; ++i) actual[i]=expected[i]=(unsigned char)i;
    void *result=ft_memmove(actual+dst, actual+src, n);
    memmove(expected+dst, expected+src, n);
    if (result != actual+dst) {
        char got[80];
        position(got, sizeof(got), result, actual, sizeof(actual));
        fprintf(stderr,"Essai : destination à l’indice %d, source à l’indice %d, longueur %d.\n"
                "Attendu : adresse de destination (indice %d).\nObtenu : %s.\n",dst,src,n,dst,got);
        return 1;
    }
    for (int i=0; i<64; ++i) if (actual[i] != expected[i]) {
        fprintf(stderr,"Essai : ft_memmove(buf + %d, buf + %d, %d), avec buf = {0, 1, 2, …}.\n"
                "Attendu : buf[%d] = %u.\nObtenu : buf[%d] = %u.\nPiste : %s\n",
                dst,src,n,i,(unsigned)expected[i],i,(unsigned)actual[i],
                i<dst || i>=dst+n ? "Cet octet est hors de la destination et doit rester intact." :
                dst>src && dst<src+n ? "Les zones se chevauchent : copie depuis la fin pour préserver les octets source." :
                "Copie les indices 0 à n − 1 de la source vers la destination.");
        return 1;
    }
}
""",
 'strlcat': r"""
for (size_t n = 0; n < 32; ++n) {
    char dst[40], expected[40];
    memset(expected, 'X', sizeof(expected));
    memcpy(expected, "abc", 4);
    memcpy(dst, expected, sizeof(dst));
    size_t wanted = (n < 3 ? n : 3) + 5;
    if (n > 3) {
        size_t copied = n - 4 < 5 ? n - 4 : 5;
        memcpy(expected + 3, "defgh", copied);
        expected[3 + copied] = 0;
    }
    size_t actual = ft_strlcat(dst, "defgh", n);
    if (actual != wanted) {
        fprintf(stderr, "Essai : destination « abc », source « defgh », taille totale %zu.\n"
                "Attendu : retour %zu (%zu octets de destination comptés + 5 de source).\n"
                "Obtenu : retour %zu.\n"
                "Piste : compte la destination dans la limite de la taille fournie, puis ajoute toute la longueur de la source.\n",
                n, wanted, wanted - 5, actual);
        return 1;
    }
    for (size_t i = 0; i < sizeof(dst); ++i) {
        if (dst[i] == expected[i]) continue;
        fprintf(stderr, "Essai : destination « abc », source « defgh », taille totale %zu.\n"
                "Attendu : octet %u à l’indice %zu.\nObtenu : octet %u.\n"
                "Piste : si la destination occupe déjà toute la taille, ne modifie rien. Sinon réserve une place pour le zéro final.\n",
                n, (unsigned char)expected[i], i, (unsigned char)dst[i]);
        return 1;
    }
}
""",
'strncmp': 'for(int j=0;j<ITERATIONS;j++){char a[65],b[65];for(int i=0;i<64;i++)a[i]=b[i]=1+random_value()%255;a[64]=b[64]=0;b[random_value()%64]=random_value();for(int n=0;n<66;n++){int got=ft_strncmp(a,b,n), want=strncmp(a,b,n);VERIFY(signum(got)==signum(want),"Comparaison limitée à %d caractères. Attendu : %s. Obtenu : %d. Compare les octets non signés et arrête-toi au zéro final.",n,want<0?"un résultat négatif":want>0?"un résultat positif":"zéro",got);}}',
 'memcmp': r"""
for (int trial = -2; trial < ITERATIONS; ++trial) {
    unsigned char a[64] = {0}, b[64] = {0};
    size_t length = 2;
    if (trial == -2) {
        a[1] = 1; b[1] = 2;
    } else if (trial == -1) {
        a[0] = 255; b[0] = 1;
    } else {
        length = sizeof(a);
        for (size_t i=0; i<length; ++i) a[i]=b[i]=random_value();
        size_t index = random_value()%length;
        b[index] = random_value();
    }
    for (size_t n=0; n<=length; ++n) {
        int want=memcmp(a,b,n), got=ft_memcmp(a,b,n);
        if (signum(want)==signum(got)) continue;
        size_t i=0;
        while (i<n && a[i]==b[i]) ++i;
        fprintf(stderr,"Essai : comparaison de %zu octet(s). ",n);
        if (i<n) fprintf(stderr,"Première différence à l’indice %zu : %u contre %u.\n",
                         i,(unsigned)a[i],(unsigned)b[i]);
        else fprintf(stderr,"Aucune différence dans la zone comparée.\n");
        fprintf(stderr,"Attendu : %s.\nObtenu : %d.\nPiste : %s\n",
                want<0?"un nombre négatif":want>0?"un nombre positif":"zéro",got,
                trial==-2?"Les deux premiers octets valent zéro. Continue la comparaison après ce zéro commun.":
                "Compare les octets comme des unsigned char jusqu’à la première différence ou la limite n.");
        return 1;
    }
}
""",
 'strnstr': r"""
const char *haystack = "abababc";
for (int trial = 0; trial < 13; ++trial) {
    const char *s = trial == 12 ? "" : haystack;
    const char *needle = trial == 0 ? "" : trial == 11 ? "abcd" : trial == 12 ? "a" : "abc";
    size_t n = trial == 0 ? 0 : trial == 11 ? 20 : trial == 12 ? 1 : (size_t)(trial - 1);
    const char *want = trial == 0 ? s : trial <= 10 && n >= 7 ? s + 4 : NULL;
    char *got = ft_strnstr(s, needle, n);
    if (got != want) {
        char expected[80], actual[80];
        position(expected, sizeof(expected), (void *)want, (void *)s, strlen(s)+1);
        position(actual, sizeof(actual), got, (void *)s, strlen(s)+1);
        fprintf(stderr, "Essai : ft_strnstr(\"%s\", \"%s\", %zu). Zone à examiner : « %.*s ».\n"
                "Attendu : %s.\nObtenu : %s.\nPiste : %s\n", s, needle, n, (int)n, s,
                expected, actual, *needle ? "Le motif entier doit tenir dans la zone à examiner." :
                "Un motif vide correspond au début de la chaîne, même avec une limite de zéro.");
        return 1;
    }
}
""",
'atoi': 'const char *s[]={"", "0", "-0", "2147483647", "-2147483648", " \\t\\n\\v\\f\\r-42x", "+123", "--1", "  + 1", "42abc"};for(unsigned i=0;i<sizeof(s)/sizeof(*s);i++){int got=ft_atoi(s[i]);VERIFY(got==atoi(s[i]),"Entrée « %s », entier attendu %d, obtenu %d.",s[i],atoi(s[i]),got);};for(int i=0;i<ITERATIONS;i++){char b[32];int n=(int)(random_value()%INT_MAX);sprintf(b,"%d",n);NUMBER(ft_atoi(b),n,n);}',
 'calloc': r"""
for (size_t trial=0; trial<130; ++trial) {
    size_t n=trial<128 ? trial : trial==128 ? 3 : 0;
    size_t size=trial<128 ? 3 : 0;
    unsigned char *p=ft_calloc(n,size);
    if (!p) {
        fprintf(stderr,"Essai : ft_calloc(%zu, %zu).\nAttendu : un pointeur que free peut libérer.\n"
                "Obtenu : NULL.\nPiste : %s\n", n,size,
                n==0 || size==0 ? "Le sujet Libft demande une allocation libérable même quand la taille totale vaut zéro." :
                "Cette petite allocation doit réussir dans le test normal.");
        return 1;
    }
    for (size_t i=0; i<n*size; ++i) if (p[i]!=0) {
        fprintf(stderr,"Essai : ft_calloc(%zu, %zu).\nAttendu : zéro à l’indice %zu.\n"
                "Obtenu : %u.\nPiste : initialise exactement %zu octets.\n",
                n,size,i,(unsigned)p[i],n*size);
        free(p); return 1;
    }
    free(p);
}
void *overflow=ft_calloc(SIZE_MAX/2+1,2);
if (overflow) {
    fprintf(stderr,"Essai : ft_calloc(SIZE_MAX / 2 + 1, 2).\nAttendu : NULL.\n"
            "Obtenu : un pointeur.\nPiste : vérifie le dépassement avant de multiplier.\n");
    free(overflow); return 1;
}
""",
'strdup': 'eq(ft_strdup(""),"");eq(ft_strdup("hello"),"hello");char s[]="abc";char *p=ft_strdup(s);VERIFY(p && p!=s,"La duplication doit renvoyer une nouvelle zone allouée, distincte de la source.");s[0]=88;eq(p,"abc");',
'substr': 'eq(ft_substr("hello",1,3),"ell");eq(ft_substr("hello",99,3),"");eq(ft_substr("hello",2,SIZE_MAX),"llo");eq(ft_substr("",0,2),"");eq(ft_substr("hello",0,0),"");',
 'strjoin': r"""
const char *left[] = {"abc", "", "x", ""};
const char *right[] = {"def", "x", "", ""};
for (int trial=0; trial<ITERATIONS+4; ++trial) {
    char a[65], b[65], expected[129];
    if (trial<4) {
        strcpy(a,left[trial]);
        strcpy(b,right[trial]);
    } else {
        size_t x=random_value()%65, y=random_value()%65;
        for (size_t i=0;i<x;++i) a[i]='a'+random_value()%26;
        for (size_t i=0;i<y;++i) b[i]='a'+random_value()%26;
        a[x]=b[y]=0;
    }
    snprintf(expected,sizeof(expected),"%s%s",a,b);
    char *result=ft_strjoin(a,b);
    size_t end=strlen(expected), i=0;
    if (result) while (i<end && result[i]==expected[i]) ++i;
    if (!result || result[i]!=expected[i]) {
        fprintf(stderr,"Essai : ft_strjoin(\"%s\", \"%s\").\nAttendu : \"%s\", puis le zéro final.\n",a,b,expected);
        if (!result) fprintf(stderr,"Obtenu : NULL.\n");
        else fprintf(stderr,"Obtenu : octet %u à l’indice %zu au lieu de %u.\n",
                     (unsigned char)result[i],i,(unsigned char)expected[i]);
        fprintf(stderr,"Piste : réserve la longueur des deux chaînes plus une place pour le zéro final.\n");
        free(result);
        return 1;
    }
    free(result);
}
""",
'strtrim': 'eq(ft_strtrim("abbahelloaba","ab"),"hello");eq(ft_strtrim("aaa","a"),"");eq(ft_strtrim("abc",""),"abc");eq(ft_strtrim("","x"),"");eq(ft_strtrim("a b a","a")," b ");',
'split': 'const char *s[]={"",",,,",",a,,bb,c,","abc"};const char *expected[][4]={{NULL},{NULL},{"a","bb","c",NULL},{"abc",NULL}};for(int i=0;i<4;i++){char **p=ft_split(s[i],44);VERIFY(p,"Pour « %s », split a renvoyé NULL au lieu du tableau de mots.",s[i]);int j=0;while(expected[i][j]){VERIFY(p[j],"Le tableau se termine trop tôt : le mot %d (« %s ») manque pour « %s ».",j+1,expected[i][j],s[i]);compare_text(p[j],expected[i][j],"mot découpé par ft_split");free(p[j]);j++;}VERIFY(!p[j],"Après le dernier mot de « %s », le pointeur suivant doit être NULL.",s[i]);free(p);}char **p=ft_split("abc",0);VERIFY(p && p[0] && !p[1],"Avec « abc » et un séparateur nul, le tableau doit contenir un seul mot, suivi de NULL.");eq(p[0],"abc");free(p);',
'itoa': 'int v[]={0,1,-1,INT_MIN,INT_MAX};for(int i=0;i<ITERATIONS+5;i++){int n=i<5?v[i]:(int)(random_value()%INT_MAX);char b[32];sprintf(b,"%d",n);eq(ft_itoa(n),b);}',
'strmapi': 'eq(ft_strmapi("abcdef",mapper),"acedfh");eq(ft_strmapi("",mapper),"");',
'striteri': 'char s[]="abcdef";ft_striteri(s,iterator);compare_text(s,"acedfh","transformation de abcdef avec son indice");char e[]="";ft_striteri(e,iterator);VERIFY(!*e,"Sur une chaîne vide, le premier caractère doit rester le zéro final.");',
'lstnew': 'int n=42;t_list *p=ft_lstnew(&n);VERIFY(p && p->content==&n && !p->next,"Le nouveau maillon doit contenir le pointeur fourni et avoir next égal à NULL.");free(p);p=ft_lstnew(NULL);VERIFY(p && !p->content && !p->next,"Avec un contenu NULL, lstnew doit créer un maillon dont content et next valent NULL.");free(p);',
'lstadd_front': 't_list a={0,0},b={0,0},*p=NULL;ft_lstadd_front(&p,&a);VERIFY(p==&a && !a.next,"Après insertion dans la liste vide, la tête doit être le nouveau maillon et son suivant doit être NULL.");ft_lstadd_front(&p,&b);VERIFY(p==&b && b.next==&a,"Après ajout en tête, le nouveau maillon doit pointer vers l’ancienne tête.");',
'lstsize': 't_list a={0,0},b={0,&a};unsigned int (*f)(t_list *)=ft_lstsize;NUMBER(f(NULL),0,0);NUMBER(f(&a),1,1);NUMBER(f(&b),2,2);',
'lstlast': 't_list a={0,0},b={0,&a};VERIFY(!ft_lstlast(NULL),"Sur une liste vide, lstlast doit renvoyer NULL.");VERIFY(ft_lstlast(&a)==&a,"Sur une liste à un maillon, lstlast doit renvoyer ce maillon.");VERIFY(ft_lstlast(&b)==&a,"Sur la liste B → A, lstlast doit renvoyer A.");',
'lstadd_back': 't_list a={0,0},b={0,0},*p=NULL;ft_lstadd_back(&p,&a);VERIFY(p==&a,"Après ajout en fin de liste vide, la tête doit pointer vers le maillon ajouté.");ft_lstadd_back(&p,&b);VERIFY(p==&a && a.next==&b && !b.next,"Après ajout en fin, la tête doit rester A et les liens doivent être A → B → NULL.");',
'lstdelone': 't_list tail={0,0};t_list *p=malloc(sizeof(*p));int n=0;p->content=&n;p->next=&tail;ft_lstdelone(p,increment);VERIFY(n==1 && !tail.next,"delone doit appeler del une seule fois et préserver le maillon suivant. Appels observés : %d.",n);',
'lstclear': 't_list *p=NULL;ft_lstclear(&p,nothing);int n=0;for(int i=0;i<5;i++){t_list *q=malloc(sizeof(*q));q->content=&n;q->next=p;p=q;}ft_lstclear(&p,increment);VERIFY(!p && n==5,"Après lstclear sur 5 maillons, tête attendue NULL et 5 appels à del. Obtenu : tête %s et %d appels.",p?"non vide":"vide",n);',
'lstiter': 'int n=0;t_list a={&n,0},b={&n,&a};ft_lstiter(NULL,increment);ft_lstiter(&b,increment);VERIFY(n==2,"Deux maillons parcourus : 2 appels attendus, %d observés.",n);',
'lstmap': 'int n=7;t_list a={&n,0},b={&n,&a};VERIFY(!ft_lstmap(NULL,duplicate,free),"Sur une liste vide, lstmap doit renvoyer NULL.");t_list *p=ft_lstmap(&b,duplicate,free);VERIFY(p && p!=&b && p->next && p->next!=&a && !p->next->next,"La liste transformée doit contenir deux nouveaux maillons distincts des originaux et se terminer par NULL.");VERIFY(p->content && p->next->content,"Le callback a produit deux contenus alloués, mais le contenu de l’un des maillons est NULL.");VERIFY(*(int*)p->content==8 && *(int*)p->next->content==8 && n==7,"Les deux contenus transformés doivent valoir 8 et le contenu original doit rester 7.");free(p->next->content);free(p->next);free(p->content);free(p);',
})
CASES['memchr'] = r"""
unsigned char a[256];
for (int i=0; i<256; ++i) a[i]=i;
for (int c=0; c<512; ++c) for (int n=0; n<=256; ++n) {
    void *want=memchr(a,c,n), *got=ft_memchr(a,c,n);
    if (want!=got) {
        char expected[80], actual[80];
        position(expected,sizeof(expected),want,a,sizeof(a));
        position(actual,sizeof(actual),got,a,sizeof(a));
        fprintf(stderr,"Essai : ft_memchr(tampon, %d, %d), avec tampon = {0, 1, 2, …}.\n"
                "Attendu : %s.\nObtenu : %s.\nPiste : %s\n",c,n,expected,actual,
                (unsigned char)c==0 && n>0 ? "Compare aussi le premier octet quand il vaut zéro. La longueur limite la recherche." :
                "La recherche porte sur exactement n octets, même si le tampon contient un zéro.");
        return 1;
    }
}
"""
for search in ('strchr', 'strrchr'):
    CASES[search] = r"""
char s[] = {'A', (char)200, 'A', 0};
for (int c = 0; c < 512; ++c) {
    char *expected = SEARCH(s, c), *actual = ft_SEARCH(s, c);
    if (actual != expected) {
        char want[80], got[80];
        position(want, sizeof(want), expected, s, sizeof(s));
        position(got, sizeof(got), actual, s, sizeof(s));
        fprintf(stderr, "Essai : ft_SEARCH(chaîne, %d), avec trois caractères suivis du zéro final. Octets : [65, 200, 65, 0].\n"
                "Attendu : %s.\nObtenu : %s.\nPiste : %s\n", c, want, got,
                (unsigned char)c == 0 ? "Compare aussi le caractère de fin, à l’indice 3. Une boucle qui s’arrête dès qu’elle le rencontre saute cette comparaison." :
                "Vérifie la conversion du caractère et l’occurrence renvoyée.");
        return 1;
    }
}
""".replace('SEARCH', search)

CASES['strlcpy'] = r"""
for (size_t n = 0; n < 32; ++n) {
    unsigned char dst[40], expected[40];
    memset(dst, 'X', sizeof(dst));
    memset(expected, 'X', sizeof(expected));
    if (n) {
        size_t copied = n-1 < 5 ? n-1 : 5;
        memcpy(expected, "hello", copied);
        expected[copied] = 0;
    }
    size_t result = ft_strlcpy((char *)dst, "hello", n);
    if (result != 5) {
        fprintf(stderr, "Source « hello », taille %zu. Longueur attendue : 5. Obtenu : %zu.\n", n, result);
        return 1;
    }
    for (size_t i = 0; i < sizeof(dst); ++i) if (dst[i] != expected[i]) {
        if (n == 1 && i == 0 && dst[i] == 'h') {
            fprintf(stderr, "Essai : ft_strlcpy(dst, \"hello\", 1).\n"
                    "Attendu : dst[0] contient le zéro final (chaîne vide).\n"
                    "Obtenu : dst[0] contient 'h', le premier caractère de la source.\n"
                    "Piste : avec une seule place, réserve-la au zéro final. Aucun caractère de hello ne tient.\n");
            return 1;
        }
        fprintf(stderr, "Source « hello », taille autorisée : %zu.\n"
                "À l’indice %zu, valeur attendue : %u. Valeur obtenue : %u.\n%s\n",
                n, i, (unsigned)expected[i], (unsigned)dst[i],
                !n ? "Avec une taille de 0, aucun octet ne doit changer, même pour écrire le zéro final." :
                "Copie au plus taille − 1 caractères, puis termine la chaîne dans la zone autorisée.");
        return 1;
    }
}
"""

for name, call, expected in [('putchar_fd',"ft_putchar_fd('x',fd)",'x'),('putstr_fd','ft_putstr_fd("hello",fd)','hello'),('putendl_fd','ft_putendl_fd("hello",fd)','hello\\n'),('putnbr_fd','ft_putnbr_fd(INT_MIN,fd)','-2147483648')]:
    CASES[name] = f'FILE *f=tmpfile();VERIFY(f,"Le banc de test n’a pas pu ouvrir le fichier temporaire qui recueille la sortie.");int fd=fileno(f);{call};rewind(f);char b[128]={{0}};size_t n=fread(b,1,127,f);VERIFY(n==strlen("{expected}"),"Sur le descripteur %d, %zu octets attendus, %zu reçus. Vérifie le descripteur et la longueur écrite.",fd,strlen("{expected}"),n);compare_text(b,"{expected}","écriture sur le descripteur fourni");fclose(f);'
ALLOCATIONS = {
'calloc': 'ft_calloc(8,4)', 'strdup': 'ft_strdup("hello")',
'substr': 'ft_substr("hello",1,3)', 'strjoin': 'ft_strjoin("ab","cd")',
'strtrim': 'ft_strtrim(" aa "," ")', 'split': 'ft_split("a,bb,ccc",44)',
'itoa': 'ft_itoa(-42)', 'strmapi': 'ft_strmapi("abc",mapper)',
'lstnew': 'ft_lstnew(NULL)',
}
WRAP = r'''
void *__real_malloc(size_t);
static long allocation_index;
static long failure_index;
void *__wrap_malloc(size_t n) {
    allocation_index++;
    if (failure_index && allocation_index == failure_index) return NULL;
    return __real_malloc(n);
}
'''

# The callback allocates through the real allocator so injected failures target
# list nodes, not the independently allocated mapped content.
LSTMAP_FAILURE = r'''
static int live_contents;
void *tracked_map(void *p) {
    int *q = __real_malloc(sizeof(int));
    VERIFY(q,"Le banc de test n’a pas pu allouer le contenu de référence.");
    *q = *(int *)p;
    live_contents++;
    return q;
}
void tracked_delete(void *p) { live_contents--; free(p); }
int main(void) {
    int value = 42;
    t_list c = {&value, NULL}, b = {&value, &c}, a = {&value, &b};
    failure_index = FAILURE;
    t_list *result = ft_lstmap(&a, tracked_map, tracked_delete);
    VERIFY(allocation_index >= failure_index,"L’échec malloc prévu au rang %ld n’a pas été atteint.",failure_index);
    VERIFY(result == NULL,"Quand la création d’un maillon échoue, lstmap doit renvoyer NULL.");
    VERIFY(live_contents == 0,"Après l’échec malloc, %d contenus transformés restent à libérer.",live_contents);
    VERIFY(a.next == &b && b.next == &c && !c.next && value == 42,"Après l’échec malloc, les liens et le contenu de la liste source doivent rester intacts.");
    return 0;
}
'''

# Exact heap extents expose reads beyond the contract under Valgrind.
BOUNDS = {
    'strlen': r'''for(size_t z=1;z<65;z++){char *p=malloc(z);VERIFY(p,"Le banc de test n’a pas pu allouer son tampon.");memset(p,'a',z);p[z-1]=0;NUMBER(ft_strlen(p),z-1,z);free(p);}''',
    'memchr': r'''for(size_t z=1;z<65;z++){char *p=malloc(z);VERIFY(p,"Le banc de test n’a pas pu allouer son tampon.");memset(p,'a',z);VERIFY(!ft_memchr(p,'b',z),"Recherche de b dans %zu octets contenant seulement a : attendu NULL.",z);free(p);}''',
    'memcmp': r'''for(size_t z=1;z<65;z++){char *p=malloc(z),*q=malloc(z);VERIFY(p&&q,"Le banc de test n’a pas pu allouer ses deux tampons.");memset(p,42,z);memset(q,42,z);NUMBER(ft_memcmp(p,q,z),0,z);free(p);free(q);}''',
    'strncmp': r'''for(size_t z=1;z<65;z++){char *p=malloc(z),*q=malloc(z);VERIFY(p&&q,"Le banc de test n’a pas pu allouer ses deux tampons.");memset(p,'a',z);memset(q,'a',z);NUMBER(ft_strncmp(p,q,z),0,z);free(p);free(q);}''',
    'memcpy': r'''for(size_t z=1;z<65;z++){char *p=malloc(z),*q=malloc(z);VERIFY(p&&q,"Le banc de test n’a pas pu allouer ses deux tampons.");memset(p,42,z);VERIFY(ft_memcpy(q,p,z)==q,"Le pointeur renvoyé doit être l’adresse de début de la destination.");compare_bytes(p,q,z,z);free(p);free(q);}''',
    'strlcpy': r'''for(size_t z=1;z<65;z++){char *p=malloc(z);VERIFY(p,"Le banc de test n’a pas pu allouer son tampon.");NUMBER(ft_strlcpy(p,"abc",z),3,z);VERIFY(p[z<4?z-1:3]==0,"Copie de « abc » dans %zu octets : le zéro final manque à la position attendue.",z);free(p);}''',
}
for _name, _body in BOUNDS.items():
    CASES[_name] += '\n{' + _body + '}\n'

CASES['substr'] += r'''{for(int trial=0;trial<ITERATIONS;trial++){char s[65],expected[65];size_t len=random_value()%65,start=random_value()%80,n=random_value()%80;memset(s,'a',len);s[len]=0;size_t wanted=start>=len?0:(n<len-start?n:len-start);memset(expected,'a',wanted);expected[wanted]=0;char context[256];snprintf(context,sizeof(context),"ft_substr(\"%s\", %zu, %zu), longueur source %zu",s,start,n,len);char *result=ft_substr(s,start,n);compare_text(result,expected,context);free(result);}}'''
CASES['lstsize'] += r'''{t_list nodes[128];for(unsigned n=0;n<128;n++){for(unsigned i=0;i<n;i++){nodes[i].content=NULL;nodes[i].next=i+1<n?&nodes[i+1]:NULL;}NUMBER(ft_lstsize(n?nodes:NULL),n,n);}}'''
CASES['lstlast'] += r'''{t_list nodes[128];for(unsigned n=0;n<128;n++){for(unsigned i=0;i<n;i++){nodes[i].content=NULL;nodes[i].next=i+1<n?&nodes[i+1]:NULL;}VERIFY(ft_lstlast(n?nodes:NULL)==(n?&nodes[n-1]:NULL),"Liste de %u maillons : adresse du dernier maillon incorrecte (NULL si vide).",n);}}'''
CASES['putnbr_fd'] += r'''{int values[]={0,1,-1,INT_MAX,INT_MIN,12345,-54321};for(unsigned i=0;i<sizeof(values)/sizeof(*values);i++){FILE *f=tmpfile();VERIFY(f,"Le banc de test n’a pas pu ouvrir le fichier temporaire qui recueille la sortie.");ft_putnbr_fd(values[i],fileno(f));rewind(f);char actual[64]={0},expected[64];sprintf(expected,"%d",values[i]);NUMBER(fread(actual,1,63,f),strlen(expected),values[i]);compare_text(actual,expected,"écriture du nombre sur le descripteur fourni");fclose(f);}}'''
