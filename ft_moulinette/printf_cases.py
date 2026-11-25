"""Binary-safe differential tests for the conversions in Printf 1.1."""

GROUPS = ('literal', 'c', 's', 'p', 'd', 'i', 'u', 'x', 'X', 'percent', 'mixed', 'random')

HARNESS = r'''
#define _POSIX_C_SOURCE 200809L
#include "ft_printf.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <limits.h>
#include <unistd.h>
#include <sys/stat.h>

static FILE *capture;
static int saved_stdout;
static unsigned char expected[200000], actual[200000];
static unsigned int state = SEEDu;
static size_t cases;
static int (*oracle)(char *, size_t, const char *, ...) = snprintf;
static unsigned int random_value(void)
{
    state = state * 1664525u + 1013904223u;
    return state;
}
static void die(const char *message)
{
    perror(message);
    exit(2);
}
static void begin_capture(void)
{
    if (fflush(stdout) || ftruncate(fileno(capture), 0) ||
        fseek(capture, 0, SEEK_SET) || dup2(fileno(capture), STDOUT_FILENO) < 0)
        die("capture stdout");
}
static void verify(int reference, int result, const char *call)
{
    if (fflush(stdout) || dup2(saved_stdout, STDOUT_FILENO) < 0)
        die("restore stdout");
    struct stat info;
    if (fstat(fileno(capture), &info) || fseek(capture, 0, SEEK_SET)) die("read capture");
    long size = (long)info.st_size;
    size_t n = fread(actual, 1, sizeof(actual), capture);
    ++cases;
    if (reference < 0 || (size_t)reference >= sizeof(expected)) die("oracle capacity");
    size_t offset = 0;
    while (offset < n && offset < (size_t)reference &&
           actual[offset] == expected[offset]) ++offset;
    if (reference != result || size != reference || offset != (size_t)reference)
    {
        fprintf(stderr, "Cas %zu : %s\nRetour attendu : %d ; obtenu : %d\n"
            "Octets attendus : %d ; obtenus : %ld ; premier écart : %zu\n",
            cases, call, reference, result, reference, size, offset);
        if (offset < (size_t)reference)
            fprintf(stderr, "Octet attendu : 0x%02x\n", expected[offset]);
        if (offset < n)
            fprintf(stderr, "Octet obtenu : 0x%02x\n", actual[offset]);
        exit(1);
    }
}
#define TEST(...) do { \
    int reference = oracle((char *)expected, sizeof(expected), __VA_ARGS__); \
    begin_capture(); \
    int result = ft_printf(__VA_ARGS__); \
    verify(reference, result, #__VA_ARGS__); \
} while (0)

int main(int argc, char **argv)
{
    if (argc != 2) return 2;
    capture = tmpfile();
    saved_stdout = dup(STDOUT_FILENO);
    if (!capture || saved_stdout < 0) die("prepare capture");
    const char *group = argv[1];
    int signed_values[] = {INT_MIN, INT_MIN+1, -1000000000, -65536, -1000,
        -100, -42, -16, -10, -9, -1, 0, 1, 9, 10, 15, 16, 42, 99, 100,
        255, 256, 999, 1000, 65535, 65536, INT_MAX-1, INT_MAX};
    unsigned int unsigned_values[] = {0u, 1u, 9u, 10u, 15u, 16u, 17u,
        42u, 99u, 100u, 255u, 256u, 4095u, 4096u, 65535u, 65536u,
        (unsigned int)INT_MAX, (unsigned int)INT_MAX+1u, UINT_MAX-1u, UINT_MAX};
    if (!strcmp(group, "literal")) {
        TEST(""); TEST("a"); TEST("Hello, world!\n");
        TEST("cspdiuxX sans conversion"); TEST("\t\r\n\v\f");
        TEST("école — UTF-8");
        char long_format[65537];
        memset(long_format, 'a', sizeof(long_format)-1);
        long_format[sizeof(long_format)-1] = 0;
        TEST(long_format);
        char ended[] = {'a', 0, '%', 'd', 0};
        TEST(ended);
    } else if (!strcmp(group, "c")) {
        for (int c = 0; c <= UCHAR_MAX; ++c) {
            TEST("%c", c); TEST("a%cb%c", c, 0);
        }
        TEST("%c%c%c", 0, 0, 0);
        TEST("%c%c%c", -1, 256, INT_MIN);
    } else if (!strcmp(group, "s")) {
        char embedded[] = {'a', 0, 'b', 0};
        char high[] = {(char)0x80, (char)0xff, 0};
        TEST("%s", ""); TEST("<%s>", "bonjour");
        TEST("%s%s%s", "", "abc", ""); TEST("%s", embedded);
        TEST("%s", high); TEST("%s", "%% %d %s\n\t");
        TEST("%s", "école — UTF-8");
        char *long_string = malloc(65537);
        if (!long_string) die("malloc");
        memset(long_string, 'z', 65536); long_string[65536] = 0;
        TEST("%s", long_string); TEST("%s:%s", long_string, "fin");
        free(long_string);
        char *exact = malloc(2);
        if (!exact) die("malloc");
        exact[0] = 'x'; exact[1] = 0; TEST("%s", exact); free(exact);
    } else if (!strcmp(group, "p")) {
        char local[8];
        void *heap = malloc(1);
        if (!heap) die("malloc");
        TEST("%p", (void *)0);
        TEST("%p:%p:%p", (void *)local, heap, (void *)(local+7));
        uintptr_t pointers[] = {1, 15, 16, 255, 256, UINTPTR_MAX,
            UINTPTR_MAX/2, (uintptr_t)UINT_MAX};
        for (size_t j = 0; j < sizeof(pointers)/sizeof(*pointers); ++j)
            TEST("[%p]", (void *)pointers[j]);
        free(heap);
    } else if (!strcmp(group, "d") || !strcmp(group, "i")) {
        const char *fmt = !strcmp(group, "d") ? "%d" : "%i";
        for (size_t j = 0; j < sizeof(signed_values)/sizeof(*signed_values); ++j)
            TEST(fmt, signed_values[j]);
        TEST("%d%i%d%i", INT_MIN, INT_MAX, 0, -1);
    } else if (!strcmp(group, "u") || !strcmp(group, "x") || !strcmp(group, "X")) {
        const char *fmt = !strcmp(group, "u") ? "%u" : (!strcmp(group, "x") ? "%x" : "%X");
        for (size_t j = 0; j < sizeof(unsigned_values)/sizeof(*unsigned_values); ++j)
            TEST(fmt, unsigned_values[j]);
        for (unsigned int j = 0; j < sizeof(unsigned int)*CHAR_BIT; ++j) {
            unsigned int v = 1u << j;
            TEST(fmt, v-1u); TEST(fmt, v); TEST(fmt, v+1u);
        }
        TEST("%x%X%u", 0xabcdefu, 0xabcdefu, UINT_MAX);
    } else if (!strcmp(group, "percent")) {
        TEST("%%"); TEST("%%%%"); TEST("a%%b%%c");
        TEST("%%%d", 42); TEST("%d%%", -1);
        TEST("%%%c%%%s%%%p", 0, "%d", (void *)0);
    } else if (!strcmp(group, "mixed")) {
        int object = 0;
        for (int j = 0; j < 50; ++j)
            TEST("start:%c|%s|%p|%d|%i|%u|%x|%X|%%:end\n",
                j, "abc%d", (void *)&object, INT_MIN, INT_MAX,
                UINT_MAX, 0xabcdefu, 0xabcdefu);
        TEST("%d%d%d%d%d%d%d%d%d%d%d%d%d%d%d%d",
            1, -2, 3, -4, 5, -6, 7, -8, 9, -10, 11, -12, 13, -14, 15, -16);
        TEST("%s%s%s%s%s%s%s%s%s%s", "", "a", "", "b", "", "c", "", "d", "", "e");
    } else if (!strcmp(group, "random")) {
        for (int j = 0; j < ITERATIONS; ++j) {
            unsigned int u = random_value();
            int d = (int)random_value();
            char str[129];
            size_t length = random_value() % 128;
            for (size_t k = 0; k < length; ++k)
                str[k] = (char)(1 + random_value() % 255);
            str[length] = 0;
            TEST("%d|%i|%u|%x|%X", d, d, u, u, u);
            TEST("%c%s%%%p", (int)(u % 256), str, (void *)(uintptr_t)u);
        }
    } else return 2;
    fclose(capture);
    close(saved_stdout);
    printf("%zu cas réussis\n", cases);
    return 0;
}
'''
