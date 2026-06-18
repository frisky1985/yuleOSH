CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -g -O0
UNITY_DIR = src
TEST_FILES = $(wildcard *.c) $(UNITY_DIR)/unity.c
TARGET = test_runner

all: $(TARGET)
	./$(TARGET)

$(TARGET): $(TEST_FILES)
	$(CC) $(CFLAGS) -I$(UNITY_DIR) -o $@ $^

clean:
	rm -f $(TARGET)

.PHONY: all clean
