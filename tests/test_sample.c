// 测试程序
#include <stdio.h>

int add(int a, int b) {
    return a + b;
}

int main(int argc, char *argv[]) {
    printf("Magic Debug Test Program\n");
    
    int x = 10;
    int y = 20;
    int result = add(x, y);
    
    printf("Result: %d\n", result);
    
    for (int i = 0; i < 5; i++) {
        printf("Loop iteration: %d\n", i);
    }
    
    return 0;
}
