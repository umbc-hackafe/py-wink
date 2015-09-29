if __name__ == "__main__":
    import time
    try:
        import wink
    except ImportError as e:
        import sys
        sys.path.insert(0, "..")
        import wink

    w = wink.init("../config.cfg")

    for bulb in w.light_bulbs():
        bulb.turn_off()

    for bulb in w.light_bulbs():
        bulb.turn_on()
