"""Sample ESP32 target plugin entry point."""


def run(args: dict) -> dict:
    """Flash and blink an LED on ESP32."""
    port = args.get("port", "/dev/ttyUSB0")
    baud = args.get("baud", 115200)
    return {
        "status": "ok",
        "port": port,
        "baud": baud,
        "message": f"Connected to {port} at {baud} baud",
    }
