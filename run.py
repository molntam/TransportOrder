import sys

if sys.version_info < (3, 10):
    raise SystemExit("TransportOrder needs Python 3.10 or later.")

from transport_order.server import main

if __name__ == "__main__":
    main()
