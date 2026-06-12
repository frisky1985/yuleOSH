# yuleOSH Blinky — ESP-IDF v5.x 顶层 CMakeLists.txt
#
# 用法:
#   idf.py set-target esp32
#   idf.py build flash monitor

cmake_minimum_required(VERSION 3.16)

# 从环境变量 IDF_PATH 引入项目框架
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

# 项目名称 (与构建产物同名)
project(blinky)
