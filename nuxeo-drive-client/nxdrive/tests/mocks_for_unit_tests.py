__author__ = 'jowensla'

class MockDeviceConfig(object):

    def __init__(self):
        self.device_id = '0270a087-ca91-4ec9-8c8c-18975282722e'


class MockController(object):

    def __init__(self):
        self.mock_device_config = MockDeviceConfig()

    def get_device_config(self):
        return self.mock_device_config


