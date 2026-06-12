# yuleOSH Blinky — 主组件 CMakeLists.txt
#
# idf_component_register 注册该组件的源文件和依赖

idf_component_register(
    SRCS  "main.c"
    INCLUDE_DIRS "."
    REQUIRES  driver esp_wifi esp_event esp_netif nvs_flash
)
