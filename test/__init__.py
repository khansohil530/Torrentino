import logging


class NoLogging:
    """
    Contextual manager that can be used to disable logging.

    with NoLogging():
        call_logging_function()
    """
    def __enter__(self):
        logger = logging.getLogger()
        logger.disabled = True

    def __exit__(self, exc_type, exc_val, exc_tb):
        logger = logging.getLogger()
        logger.disabled = False

no_logging = NoLogging()

if __name__ == '__main__':
    import unittest
    unittest.main()