CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -g -O0
COVFLAGS = --coverage
UNITY_DIR = src
INCLUDES = -I$(UNITY_DIR) \
	-I../../src/yuleosh/cross \
	-I../../src/yuleosh/cross/hal_mock

# Test executables
HAL_MOCK_TARGET = test_hal_mock
HELLO_TARGET = test_hello

# Source files
HAL_MOCK_SRC = test_hal_mock_unity.c $(UNITY_DIR)/unity.c \
	../../src/yuleosh/cross/hal_mock/hal_mock_impl.c
HELLO_SRC = test_hello_unity.c $(UNITY_DIR)/unity.c

.PHONY: all coverage clean

all: $(HAL_MOCK_TARGET) $(HELLO_TARGET)
	./$(HAL_MOCK_TARGET)
	./$(HELLO_TARGET)

# Coverage build: recompile all with --coverage, run, then gcov
coverage: clean
	$(MAKE) CFLAGS="$(CFLAGS) $(COVFLAGS)" all
	@echo "=== Running gcov on source files ==="
	# Copy .gcno files from build dir
	cd ../../src/yuleosh/cross/hal_mock && gcov hal_mock_impl.c 2>/dev/null || true
	cd ../../src/yuleosh/cross && gcov hello.c 2>/dev/null || true
	@echo "=== Coverage data generated ==="
	@ls -la ../../src/yuleosh/cross/hal_mock/*.gcov 2>/dev/null || true
	@ls -la ../../src/yuleosh/cross/*.gcov 2>/dev/null || true

$(HAL_MOCK_TARGET): $(HAL_MOCK_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^

$(HELLO_TARGET): $(HELLO_SRC)
	$(CC) $(CFLAGS) $(INCLUDES) -o $@ $^

clean:
	rm -f $(HAL_MOCK_TARGET) $(HELLO_TARGET)
	rm -f *.gcda *.gcno *.gcov
	rm -f ../../src/yuleosh/cross/*.gcda ../../src/yuleosh/cross/*.gcno
	rm -f ../../src/yuleosh/cross/*.gcov
	rm -f ../../src/yuleosh/cross/hal_mock/*.gcda ../../src/yuleosh/cross/hal_mock/*.gcno
	rm -f ../../src/yuleosh/cross/hal_mock/*.gcov
