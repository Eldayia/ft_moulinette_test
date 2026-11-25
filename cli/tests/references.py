"""Independent test-only implementations; not submitted student solutions."""
REFERENCES = {
'strlcpy': r'''size_t ft_strlcpy(char *d,const char *s,size_t n){size_t len=strlen(s);if(n){size_t k=len<n-1?len:n-1;memcpy(d,s,k);d[k]=0;}return len;}''',
'strlcat': r'''size_t ft_strlcat(char *d,const char *s,size_t n){size_t a=strnlen(d,n),b=strlen(s);if(a<n){size_t k=b<n-a-1?b:n-a-1;memcpy(d+a,s,k);d[a+k]=0;}return a+b;}''',
'strnstr': r'''char *ft_strnstr(const char *s,const char *needle,size_t n){size_t k=strlen(needle);if(!k)return (char*)s;size_t len=strnlen(s,n);for(size_t i=0;i<=len && k<=len-i;i++)if(!memcmp(s+i,needle,k))return (char*)s+i;return NULL;}''',
'strtrim': r'''char *ft_strtrim(const char *s,const char *set){size_t a=strspn(s,set),b=strlen(s);while(b>a && strchr(set,s[b-1]))b--;char *p=malloc(b-a+1);if(p){memcpy(p,s+a,b-a);p[b-a]=0;}return p;}''',
'split': r'''char **ft_split(const char *s,char c){size_t len=strlen(s),count=0;char **p=calloc(len+1,sizeof(*p));if(!p)return NULL;for(size_t i=0;i<len;){if(s[i]==c){i++;continue;}size_t start=i;while(i<len && s[i]!=c)i++;p[count]=malloc(i-start+1);if(!p[count]){while(count)free(p[--count]);free(p);return NULL;}memcpy(p[count],s+start,i-start);p[count++][i-start]=0;}return p;}''',
'lstnew': r'''t_list *ft_lstnew(void *content){t_list *p=malloc(sizeof(*p));if(p){p->content=content;p->next=NULL;}return p;}''',
'lstadd_front': r'''void ft_lstadd_front(t_list **head,t_list *node){node->next=*head;*head=node;}''',
'lstadd_back': r'''void ft_lstadd_back(t_list **head,t_list *node){while(*head)head=&(*head)->next;*head=node;}''',
'lstsize': r'''unsigned int ft_lstsize(t_list *p){unsigned int n=0;for(;p;p=p->next)n++;return n;}''',
'lstlast': r'''t_list *ft_lstlast(t_list *p){if(p)while(p->next)p=p->next;return p;}''',
'lstdelone': r'''void ft_lstdelone(t_list *p,void (*del)(void *)){del(p->content);free(p);}''',
'lstclear': r'''void ft_lstclear(t_list **head,void (*del)(void *)){while(*head){t_list *p=*head;*head=p->next;del(p->content);free(p);}}''',
'lstiter': r'''void ft_lstiter(t_list *p,void (*f)(void *)){for(;p;p=p->next)f(p->content);}''',
'lstmap': r'''t_list *ft_lstmap(t_list *p,void *(*f)(void *),void (*del)(void *)){t_list *head=NULL,**tail=&head;for(;p;p=p->next){void *value=f(p->content);t_list *node=malloc(sizeof(*node));if(!node){del(value);while(head){node=head;head=head->next;del(node->content);free(node);}return NULL;}node->content=value;node->next=NULL;*tail=node;tail=&node->next;}return head;}''',
}
