import os

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    return application
