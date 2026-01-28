from django.test import TestCase, TransactionTestCase
from django.core.management import call_command
from rest_framework.test import APIClient

# Create your tests here.
class TestViews(TransactionTestCase):
    def setUp(self):
        call_command('import_devices')
        self.client = APIClient()
        
    def test_fetch_config(self):
        response = self.client.post('/api/devices/1/fetch-config/', {'pk': 1})
        print(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['success'], True)

    def test_batch_fetch_config(self):
        response = self.client.post('/api/devices/batch-fetch-config/')
        print(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['success'], True)

    def test_sqlite_wal(self):
        # 检查SQLite数据库的WAL模式是否开启
        response = self.client.get('/check-wal-mode')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['success'], True)
        print(response.json())


from cmdb.serializers import InterfaceSerializer
from cmdb.utils import config_parser

class TestParseConfig(TestCase):
    def setUp(self):
        config_file = r'E:\python\Project\network_ops\cmdb\tests\config.txt'
        self.config_parser = config_parser
        self.config = open(config_file, 'r').read()
    
    def test_parse_config(self):
        result = self.config_parser.parse_config(self.config, 'hp_comware')
        print(result)


class TestSerializer(TestCase):
    def test_interface_serializer(self):
        interface = {
            'device_id': 1,
            'device_name': 'hp_comware-1',
            'interface': 'eth0',
            'description': 'eth0 description',
            'mode': 'access',
            'access_vlan': 100,
            'combo_type': 'port-channel',
            'vrf': 'default',
            'ip_address': '192.168.1.1',
            'subnet_mask': '255.255.255.255',
        }
        serializer = InterfaceSerializer(interface)
        print(serializer.data)
