"""Public signatures from supplied Libft 1.3 subject."""
PROTOTYPES = {
'strlen':'size_t ft_strlen(const char *)',
'memset':'void *ft_memset(void *,int,size_t)', 'bzero':'void ft_bzero(void *,size_t)',
'memcpy':'void *ft_memcpy(void *,const void *,size_t)', 'memmove':'void *ft_memmove(void *,const void *,size_t)',
'strlcpy':'size_t ft_strlcpy(char *,const char *,size_t)', 'strlcat':'size_t ft_strlcat(char *,const char *,size_t)',
'strchr':'char *ft_strchr(const char *,int)', 'strrchr':'char *ft_strrchr(const char *,int)',
'strncmp':'int ft_strncmp(const char *,const char *,size_t)', 'memcmp':'int ft_memcmp(const void *,const void *,size_t)',
'memchr':'void *ft_memchr(const void *,int,size_t)', 'strnstr':'char *ft_strnstr(const char *,const char *,size_t)',
'atoi':'int ft_atoi(const char *)', 'calloc':'void *ft_calloc(size_t,size_t)', 'strdup':'char *ft_strdup(const char *)',
'substr':'char *ft_substr(const char *,unsigned int,size_t)', 'strjoin':'char *ft_strjoin(const char *,const char *)',
'strtrim':'char *ft_strtrim(const char *,const char *)','split':'char **ft_split(const char *,char)',
'itoa':'char *ft_itoa(int)','strmapi':'char *ft_strmapi(const char *,char (*)(unsigned int,char))',
'striteri':'void ft_striteri(char *,void (*)(unsigned int,char *))',
'putchar_fd':'void ft_putchar_fd(char,int)','putstr_fd':'void ft_putstr_fd(char *,int)',
'putendl_fd':'void ft_putendl_fd(char *,int)','putnbr_fd':'void ft_putnbr_fd(int,int)',
'lstnew':'t_list *ft_lstnew(void *)','lstadd_front':'void ft_lstadd_front(t_list **,t_list *)',
'lstadd_back':'void ft_lstadd_back(t_list **,t_list *)','lstsize':'unsigned int ft_lstsize(t_list *)',
'lstlast':'t_list *ft_lstlast(t_list *)','lstdelone':'void ft_lstdelone(t_list *,void (*)(void *))',
'lstclear':'void ft_lstclear(t_list **,void (*)(void *))','lstiter':'void ft_lstiter(t_list *,void (*)(void *))',
'lstmap':'t_list *ft_lstmap(t_list *,void *(*)(void *),void (*)(void *))',
}
for name in ('isalpha','isdigit','isalnum','isascii','isprint','toupper','tolower'):
    PROTOTYPES[name]='int ft_'+name+'(int)'
