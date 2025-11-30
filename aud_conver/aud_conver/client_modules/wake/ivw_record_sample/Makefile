#common makefile header

DIR_INC = ../include
DIR_BIN = ../bin
DIR_LIB = ../libs


TARGET	= wakeup.so  # 修改为共享库的名称，通常共享库以 lib 开头
BIN_TARGET = $(DIR_BIN)/$(TARGET)

CROSS_COMPILE = 
CFLAGS = -g -Wall -I$(DIR_INC) -fPIC  # 添加 -fPIC 选项，用于生成位置无关的代码
CPPFLAGS = -std=c++11 -g -Wall -I$(DIR_INC) -fPIC  # 同样为 C++ 添加 -fPIC 选项

LDFLAGS := -L$(DIR_LIB)


LDFLAGS += -laikit -lrt -ldl -lpthread -lasound 

COBJECTS := $(patsubst %.c,%.o,$(wildcard *.c))
CPPOBJECTS := $(patsubst %.cpp,%.o,$(wildcard *.cpp))

$(BIN_TARGET) : $(COBJECTS) $(CPPOBJECTS)
	$(CROSS_COMPILE)g++ $(CPPFLAGS) -shared $^ -o $@ $(LDFLAGS)  # 使用 -shared 选项生成共享库

%.o : %.c
	$(CROSS_COMPILE)gcc -c $(CFLAGS) $< -o $@  # 编译 C 文件时同样添加 -fPIC 选项

%.o : %.cpp
	$(CROSS_COMPILE)g++ -c $(CPPFLAGS) $< -o $@  # 编译 C++ 文件时同样添加 -fPIC 选项

clean:
	@rm -f *.o $(BIN_TARGET)

.PHONY: clean

#common makefile foot

#common makefile foot
